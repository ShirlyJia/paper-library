"""Deliver published briefings to the locally configured Feishu topic group via lark-cli.

Private destination and receipts stay under ignored work/notifications/. A completed
research run is independent of delivery: failed deliveries are retried, not recollected.
"""
import argparse
import fcntl
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "work/notifications/feishu.json"
SITE = "https://shirlyjia.github.io/paper-library/"


def read_json(path):
    return json.loads(path.read_text())


def save_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(".tmp")
    temp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n")
    temp.chmod(0o600)
    os.replace(temp, path)


class DeliveryError(RuntimeError):
    def __init__(self, message, uncertain=False):
        super().__init__(message)
        self.uncertain = uncertain


def cli(args, identity):
    executable = shutil.which("lark-cli") or str(Path.home() / ".local/bin/lark-cli")
    env = {**os.environ, "LARKSUITE_CLI_NO_UPDATE_NOTIFIER": "1", "LARKSUITE_CLI_NO_SKILLS_NOTIFIER": "1"}
    try:
        result = subprocess.run([executable, *args, "--as", identity, "--format", "json"],
                                cwd=ROOT, env=env, text=True, capture_output=True, timeout=55)
    except subprocess.TimeoutExpired as error:
        raise DeliveryError("飞书请求超时，发送结果需回查", uncertain=True) from error
    try:
        envelope = json.loads(result.stdout if result.returncode == 0 else result.stderr)
    except ValueError as error:
        raise DeliveryError("飞书 CLI 返回格式异常，发送结果需回查", uncertain=True) from error
    if envelope.get("ok") is not True:
        info = envelope.get("error", {})
        definite = info.get("type") in {"authentication", "authorization", "validation", "confirmation"}
        raise DeliveryError(f"飞书 CLI：{info.get('type', 'unknown')} / {info.get('message', '请求失败')}", uncertain=not definite)
    return envelope["data"]


def resolve_chat(config, config_path):
    if config.get("identity") not in {"user", "bot"}:
        raise ValueError("飞书配置 identity 必须为 user 或 bot")
    if not config.get("chatId"):
        data = cli(["im", "+chat-search", "--query", config["chatName"], "--chat-modes", "topic",
                    "--disable-search-by-user", "--page-size", "100"], config["identity"])
        matches = [c for c in (data.get("chats") or []) if c.get("name") == config["chatName"]]
        if len(matches) != 1 or data.get("has_more"):
            raise ValueError("未找到唯一匹配的话题群；请核对登录身份、群成员资格或在本机配置已核实的 chatId")
        config["chatId"] = matches[0]["chat_id"]
    chat = cli(["im", "chats", "get", "--params", json.dumps({"chat_id": config["chatId"]})], config["identity"])
    if chat.get("name") != config["chatName"] or chat.get("chat_mode") != "topic" or chat.get("chat_status") != "normal":
        raise ValueError("群名称、话题模式或状态与授权目标不符，停止发送")
    save_json(config_path, config)
    return config["chatId"]


def prepare(run_dir, root=ROOT):
    review = read_json(run_dir / "review.json")
    changed = sorted(set(review["decisions"]["included"] + review["decisions"]["corrected"]))
    if not changed:
        return None
    if review.get("publication", {}).get("published") is not True:
        raise ValueError("尚未完成上线核验，不发送群小报")
    path = (root / review["briefing"]).resolve()
    if path.parent != run_dir.resolve() or path.name != "briefing.md":
        raise ValueError("只允许发送本次运行目录的 briefing.md")
    body = path.read_text().strip()
    title = f"结构化数据研究小报｜{review['date']}"
    if not body.startswith(f"# {title}\n"):
        raise ValueError("小报标题日期与运行记录不一致")
    if re.search(r"file://|/Users/|work/collection/|<at\b|!\[", body):
        raise ValueError("小报含本机路径、提及或图片，须先整理为公开文字和链接")
    papers = {p["id"]: p for p in read_json(root / "data/papers.json")["papers"]}
    for paper_id in changed:
        if paper_id not in papers or papers[paper_id]["url"] not in body:
            raise ValueError(f"小报未覆盖已发布论文：{paper_id}")
    body += f"\n\n访问站点：{SITE}"
    if len(body.encode()) > 28000:
        raise ValueError("小报超过单条消息预算，请缩短文字后重试")
    return {"date": review["date"], "title": title, "body": body, "ids": changed,
            "papers": {key: papers[key] for key in changed}}


def verify_live(prepared):
    request = Request(SITE + "data/papers.json", headers={"Cache-Control": "no-cache", "User-Agent": "paper-library-briefing/1.0"})
    with urlopen(request, timeout=40) as response:
        live = {p["id"]: p for p in json.load(response)["papers"]}
    if any(live.get(key) != paper for key, paper in prepared["papers"].items()):
        raise ValueError("本次论文的线上数据尚未与本地一致，暂不发送")


def normalized(content):
    # The CLI renders rich posts as Markdown; heading levels/whitespace can change.
    return re.sub(r"[\s#*`]+", "", content)


def matches(message, prepared):
    content = message.get("content", "")
    return (not message.get("deleted") and isinstance(content, str)
            and normalized(prepared["body"]) in normalized(content))


def verify_message(message_id, prepared, identity):
    data = cli(["im", "+messages-mget", "--message-ids", message_id, "--no-reactions"], identity)
    if not any(m.get("message_id") == message_id and matches(m, prepared) for m in data.get("messages", [])):
        raise DeliveryError("已取得消息 ID，但回读内容尚未核对通过；保留回执，重试只读回消息")


def recover_uncertain(receipt, prepared, config):
    args = ["im", "+chat-messages-list", "--chat-id", config["chatId"], "--start", receipt["attemptedAt"],
            "--page-size", "50", "--no-reactions"]
    for _ in range(20):
        page = cli(args, config["identity"])
        found = [m for m in page.get("messages", []) if matches(m, prepared)]
        if found:
            return found[0]["message_id"]
        if not page.get("has_more"):
            return None
        args = args[:args.index("--page-token")] if "--page-token" in args else args
        args += ["--page-token", page["page_token"]]
    raise DeliveryError("发送记录回查未翻完，保留不确定状态，避免重复发送")


def deliver(run_dir, config, config_path=CONFIG, root=ROOT, dry_run=False):
    prepared = prepare(run_dir, root)
    if not prepared:
        return {"status": "no-changes"}
    if dry_run:
        return {"status": "preview", "target": config["chatName"], "identity": config["identity"], "body": prepared["body"]}
    resolved = not config.get("chatId")
    chat_id = resolve_chat(config, config_path) if resolved else config["chatId"]
    key = str(uuid.uuid5(uuid.NAMESPACE_URL, json.dumps([chat_id, prepared["date"], prepared["ids"]], ensure_ascii=False)))
    path = root / "work/notifications/receipts" / f"{key}.json"
    digest = hashlib.sha256(prepared["body"].encode()).hexdigest()
    receipt = read_json(path) if path.exists() else {"status": "pending", "idempotencyKey": key, "bodySha256": digest}
    if receipt["bodySha256"] != digest:
        raise ValueError("同一日期和论文清单的小报正文已变化，请核对已发消息；不会另发重复话题")
    if receipt["status"] == "verified":
        return {"status": "already-sent", "messageId": receipt["messageId"]}
    if not resolved:
        resolve_chat(config, config_path)
    verify_live(prepared)
    receipt.update(runDirectory=str(run_dir.relative_to(root)), date=prepared["date"], paperIds=prepared["ids"], chatId=chat_id)
    if receipt["status"] in {"sending", "uncertain"} and not receipt.get("messageId"):
        found = recover_uncertain(receipt, prepared, config)
        if found:
            receipt.update(messageId=found, status="sent")
            save_json(path, receipt)
        elif (datetime.now(timezone.utc) - datetime.fromisoformat(receipt["attemptedAt"])).total_seconds() >= 3000:
            raise DeliveryError("旧发送结果仍不确定，已超过安全重试窗口；需人工核对群历史，禁止盲目补发")
    if not receipt.get("messageId"):
        if receipt["status"] not in {"sending", "uncertain"}:
            receipt["attemptedAt"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
        receipt["status"] = "sending"
        save_json(path, receipt)
        try:
            result = cli(["im", "+messages-send", "--chat-id", chat_id, "--markdown", prepared["body"],
                          "--idempotency-key", key], config["identity"])
            if not result.get("message_id"):
                raise DeliveryError("发送响应缺少消息 ID，需回查", uncertain=True)
            receipt.update(status="sent", messageId=result["message_id"])
        except DeliveryError as error:
            receipt.update(status="uncertain" if error.uncertain else "failed")
            save_json(path, receipt)
            raise
        save_json(path, receipt)
    verify_message(receipt["messageId"], prepared, config["identity"])
    receipt.update(status="verified", verifiedAt=datetime.now(timezone.utc).isoformat(timespec="seconds"))
    save_json(path, receipt)
    save_json(run_dir / "feishu-delivery.json", receipt)
    return {"status": "sent-and-verified", "messageId": receipt["messageId"]}


def send_pending(config_path=CONFIG, root=ROOT, run_dir=None, dry_run=False):
    if not config_path.exists():
        return [{"status": "not-configured"}]
    config = read_json(config_path)
    if not config.get("enabled"):
        return [{"status": "disabled"}]
    # Explicit activation date prevents an initial setup from flooding a group with history.
    since = config["notBefore"]
    datetime.strptime(since, "%Y-%m-%d")
    paths = [run_dir / "review.json"] if run_dir else sorted((root / "work/collection/daily").glob("*/*/review.json"))
    lock = config_path.parent / "delivery.lock"
    lock.parent.mkdir(parents=True, exist_ok=True)
    results = []
    with lock.open("a") as handle:
        fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        for path in paths:
            review = read_json(path)
            if review["date"] < since:
                continue
            if not run_dir and review.get("publication", {}).get("published") is not True:
                continue
            results.append(deliver(path.parent, config, config_path, root, dry_run))
    return results


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", type=Path, help="One completed run; omit to retry pending published runs")
    parser.add_argument("--dry-run", action="store_true", help="Preview without accessing Feishu or sending")
    args = parser.parse_args()
    try:
        print(json.dumps(send_pending(run_dir=args.run.resolve() if args.run else None, dry_run=args.dry_run), ensure_ascii=False, indent=2))
        return 0
    except (DeliveryError, ValueError, OSError, KeyError) as error:
        print(f"飞书小报待发送：{error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
