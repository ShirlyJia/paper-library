"""Plan and run the daily intake per channel; record the run once review and publication are done.

Each channel keeps its own checkpoint, so one failing source no longer forces every
channel back into a six-month backfill. Candidates go to the persistent review
queue (scripts/review_queue.py); retrieval checkpoints never certify review or publication.
"""
import argparse
import calendar
import json
import os
import subprocess
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
STATE_PATH = ROOT / "work/collection/daily-state.json"
TIMEZONE = ZoneInfo("Asia/Shanghai")
# cadence in days; "incremental" re-reads the last 7 days (plus 3 days of overlap since the
# checkpoint), "six-months" re-reads half a year because index dates lag publication dates.
CHANNELS = {
    "arxiv": (1, "incremental"),
    "fulltext": (7, "six-months"),
    "semantic": (7, "six-months"),
    "citations": (7, "six-months"),
    "formal": (7, "six-months"),
    "references": (7, "six-months"),
    # Run by the reviewer, not collect.py: ranked connector results and official family pages change slowly.
    "consensus": (7, "six-months"),
    "families": (7, "six-months"),
}
MANUAL = {
    "consensus": "按 research/connector-sources.json 执行 Consensus search/fetch，导出 本次目录/consensus.json 后运行 "
                 "npm run collect:consensus -- --input 本次目录/consensus.json --output 本次目录/consensus-candidates.json "
                 "&& npm run queue -- add 本次目录/consensus-candidates.json",
    "families": "npm run fetch:sources -- --families --out 本次目录/families，逐项核对版本动态",
}
SITE = "https://shirlyjia.github.io/paper-library/"
REVIEW_KEYS = {"schemaVersion", "date", "runDirectory", "baseCommit", "plan", "channels", "decisions",
               "qualityReviewedIds", "queue", "briefing", "publication", "checkpoint", "notes"}


def six_months_before(today):
    month_index = today.year * 12 + today.month - 1 - 6
    year, month = divmod(month_index, 12)
    month += 1
    return date(year, month, min(today.day, calendar.monthrange(year, month)[1]))


def read_state(state):
    channels = {}
    for name, value in (state.get("channels") or {}).items():
        if name not in CHANNELS:
            raise ValueError(f"未知检索渠道：{name}")
        channels[name] = date.fromisoformat(value)
    return channels


def plan_window(today, state, only=None):
    checkpoints = read_state(state)
    groups, skipped = {}, []
    for name, (cadence, window) in CHANNELS.items():
        if only and name not in only:
            continue
        last = checkpoints.get(name)
        if last and last > today:
            raise ValueError(f"{name} 检查点晚于今天，请核对")
        if last and (today - last).days < cadence:
            skipped.append({"channel": name, "lastCompleted": last.isoformat(), "nextDue": (last + timedelta(days=cadence)).isoformat()})
            continue
        if not last:
            since = six_months_before(today)
        elif window == "incremental":
            since = min(today - timedelta(days=7), last - timedelta(days=3))
        else:
            # Catch up a long interruption even if it started outside six months.
            since = min(six_months_before(today), last - timedelta(days=3))
        groups.setdefault(since, []).append(name)
    return {
        "timezone": "Asia/Shanghai",
        "until": today.isoformat(),
        "groups": [{"since": since.isoformat(), "channels": names} for since, names in sorted(groups.items())],
        "manual": [{"channel": name, "todo": MANUAL[name]} for names in groups.values() for name in names if name in MANUAL],
        "skipped": skipped,
        "previousCheckpoint": state,
    }


def channel_status(plan, reports):
    """A channel counts as complete only when every one of its runs in this run directory completed."""
    planned = {name for group in plan["groups"] for name in group["channels"]}
    runs = [run for report in reports for run in report.get("runs", [])]
    result = {}
    for name in sorted(planned):
        own = [run for run in runs if run.get("channel") == name]
        failures = [{k: run.get(k) for k in ("source", "status", "error") if run.get(k)} for run in own if run.get("status") != "complete"]
        result[name] = {"status": "complete" if own and not failures else "incomplete", "runs": len(own), "failures": failures}
    for item in plan.get("skipped", []):
        result[item["channel"]] = {"status": "not-due", "nextDue": item["nextDue"]}
    return result


def validate_review(review):
    missing, extra = REVIEW_KEYS - review.keys(), review.keys() - REVIEW_KEYS
    if missing or extra:
        raise ValueError(f"review.json 字段不符：缺少 {sorted(missing)}，多出 {sorted(extra)}")
    if review["schemaVersion"] != 2:
        raise ValueError("review.json schemaVersion 必须为 2")
    for key in ("included", "corrected", "deferred", "excluded"):
        if not isinstance(review["decisions"].get(key), list):
            raise ValueError(f"decisions.{key} 必须是论文 ID 列表")
    if not set(review["qualityReviewedIds"]) <= set(review["decisions"]["included"] + review["decisions"]["corrected"]):
        raise ValueError("qualityReviewedIds 只能来自本次新增或更正")
    if set(review["checkpoint"]["advanced"]) - {n for n, c in review["channels"].items() if c["status"] == "complete"}:
        raise ValueError("只能推进本次完整完成的渠道")
    return review


CHANNEL_NAMES = {"arxiv": "arXiv", "fulltext": "OpenAlex 全文", "semantic": "语义近邻", "citations": "引用网络",
                 "formal": "正式会议", "references": "参考文献", "consensus": "Consensus", "families": "模型家族"}


def write_briefing(run_dir, plan, applied):
    """小报只写结论：一句速览 → 今天的看点（briefing-highlights.md，按 research/BRIEFING_PROMPT.md 撰写的叙述）→ 各方向一句话。

    暂缓、检索失败、发布状态等过程信息写进 run-notes.md，不混入小报。无新增或更正时不生成。
    """
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from apply_review import SHORT_DIRECTIONS, direction_digest
    included, corrected = applied.get("included", []), applied.get("corrected", [])
    if not included and not corrected:
        return None
    catalogue = json.loads((ROOT / "data/papers.json").read_text())
    counts = {}
    for entry in included + corrected:
        counts[entry["paper"]["category"]] = counts.get(entry["paper"]["category"], 0) + 1
    directions = "、".join(SHORT_DIRECTIONS.get(c, str(c)) for c, _ in sorted(counts.items(), key=lambda x: -x[1]))
    recent = (date.fromisoformat(plan["until"]) - timedelta(days=30)).isoformat()
    fresh = sum(1 for e in included if e["paper"]["date"] >= recent)
    highlights = run_dir / "briefing-highlights.md"
    if not highlights.exists():
        print("提示：缺少 briefing-highlights.md（今天的看点），小报只含自动部分。", file=sys.stderr)
    age_counts = []
    if fresh:
        age_counts.append(f"近一个月的新论文 {fresh} 篇")
    if len(included) > fresh:
        age_counts.append(f"补录旧作 {len(included) - fresh} 篇")
    split = f"（{'，'.join(age_counts)}）" if age_counts else ""
    coverage = f"归入{directions}方向" if len(counts) == 1 else f"覆盖{directions} {len(counts)} 个方向"
    overview = (f"今天收录 {len(included)} 篇{split}" + (f"，更正 {len(corrected)} 篇" if corrected else "")
                + f"，{coverage}。目录现有 {len(catalogue['papers'])} 篇，"
                + f"可在[论文库]({SITE}?sort=added)按收录时间查看。")
    parts = [f"# 结构化数据研究小报｜{plan['until']}", "", overview, "",
             highlights.read_text().strip() if highlights.exists() else "", "",
             direction_digest(applied, catalogue).strip(), ""]
    path = run_dir / "briefing.md"
    path.write_text("\n".join(parts))
    return path


def write_run_notes(run_dir, plan, channels, applied, queue, published, notes):
    """过程记录：需要你知道或处理的问题。与小报分开输出。"""
    failed = [f"- {CHANNEL_NAMES.get(n, n)}：{len(info['failures'])} 项未完成（{sorted({(f.get('error') or f['status'])[:60] for f in info['failures']})[0]}），次日自动重试"
              for n, info in channels.items() if info["status"] == "incomplete"]
    done = [CHANNEL_NAMES.get(n, n) for n, info in channels.items() if info["status"] == "complete"]
    open_items = [i for i in queue["items"] if i.get("open")]
    changed = applied.get("included") or applied.get("corrected")
    parts = [f"# 运行记录｜{plan['until']}", "",
             "## 需要处理", "",
             *(failed or ["- 无检索失败"]),
             *([] if published or not changed else ["- 本次修改尚未上线或线上核对未完成"]),
             *[f"- {note}" for note in notes], "",
             "## 暂缓", "",
             *([f"- [{d['title']}]({d['url']})：{d['reason']}" for d in applied.get("deferred", [])] or ["- 无"]), "",
             "## 状态", "",
             f"- 已完成渠道：{'、'.join(done) or '无'}",
             f"- 待审队列：{len(open_items)} 条，其中高相关 {sum(1 for i in open_items if i.get('score', 0) >= 5)} 条",
             f"- 发布：{'已上线并核对' if published else ('未上线' if changed else '本次无内容变化')}", ""]
    path = run_dir / "run-notes.md"
    path.write_text("\n".join(parts))
    return path


def finish(run_dir, review_input, published, notes):
    plan = json.loads((run_dir / "plan.json").read_text())
    reports = [json.loads(p.read_text()) for p in sorted(run_dir.glob("candidates*.json"))]
    for extra in ("consensus-candidates.json", "families-report.json"):
        if (run_dir / extra).exists():
            reports.append(json.loads((run_dir / extra).read_text()))
    channels = channel_status(plan, reports)
    applied = json.loads(review_input.read_text()) if review_input else {}
    ids = lambda key: [item["paper"]["id"] if "paper" in item else item["id"] for item in applied.get(key, [])]
    decisions = {key: ids(key) for key in ("included", "corrected", "deferred", "excluded")}
    reviewed = [item["paper"]["id"] for key in ("included", "corrected") for item in applied.get(key, [])
                if (item.get("qualityReview") or {}).get("reviewStatus") == "completed"]
    queue_path = ROOT / "work/collection/queue.json"
    queue = json.loads(queue_path.read_text()) if queue_path.exists() else {"items": []}
    state = json.loads(STATE_PATH.read_text()) if STATE_PATH.exists() else {}
    advanced = [name for name, info in channels.items() if info["status"] == "complete"]
    briefing = write_briefing(run_dir, plan, applied)
    write_run_notes(run_dir, plan, channels, applied, queue, published, notes)
    review = validate_review({
        "schemaVersion": 2, "date": plan["until"], "runDirectory": str(run_dir.relative_to(ROOT)),
        "baseCommit": subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True).stdout.strip(),
        "plan": plan, "channels": channels, "decisions": decisions, "qualityReviewedIds": reviewed,
        "queue": {"open": sum(1 for item in queue["items"] if item.get("open")), "total": len(queue["items"])},
        "briefing": str(briefing.relative_to(ROOT)) if briefing else None,
        "publication": {"published": published}, "checkpoint": {"advanced": advanced,
                        "kept": sorted(set(channels) - set(advanced))}, "notes": notes,
    })
    (run_dir / "review.json").write_text(json.dumps(review, ensure_ascii=False, indent=2) + "\n")
    state.setdefault("channels", {}).update({name: plan["until"] for name in advanced})
    temporary = STATE_PATH.with_suffix(".tmp")
    temporary.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n")
    os.replace(temporary, STATE_PATH)
    print(f"已记录 {run_dir.relative_to(ROOT)}/review.json；推进渠道：{', '.join(advanced) or '无'}；"
          f"保留：{', '.join(review['checkpoint']['kept']) or '无'}。")
    # Delivery has its own receipts; a failure never rolls back research checkpoints.
    from send_briefing import CONFIG, send_pending
    if CONFIG.exists():
        try:
            result = send_pending()
            print("飞书小报：" + json.dumps(result, ensure_ascii=False))
        except (RuntimeError, ValueError, OSError, KeyError) as error:
            print(f"研究记录已保存；飞书小报待重试：{error}", file=sys.stderr)
            return 1


def main():
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--dry-run", action="store_true", help="Preview without fetching or writing")
    cli.add_argument("--channels", help="Comma-separated subset of channels to plan, e.g. arxiv")
    cli.add_argument("--finish", type=Path, metavar="RUN_DIR", help="Write review.json and advance completed channels")
    cli.add_argument("--review-input", type=Path, help="File passed to apply_review.py for this run")
    cli.add_argument("--published", action="store_true", help="Public changes were pushed and checked online")
    cli.add_argument("--note", action="append", default=[], help="Gap or follow-up to keep in review.json")
    args = cli.parse_args()
    try:
        state = json.loads(STATE_PATH.read_text()) if STATE_PATH.exists() else {}
        if args.finish:
            return finish(args.finish.resolve(), args.review_input, args.published, args.note) or 0
        only = set(args.channels.split(",")) if args.channels else None
        if only and only - CHANNELS.keys():
            cli.error("未知检索渠道")
        plan = plan_window(datetime.now(TIMEZONE).date(), state, only)
    except (ValueError, TypeError, AttributeError) as error:
        cli.error(f"每日检索检查点或记录无效：{error}")
    if args.dry_run:
        print(json.dumps(plan, ensure_ascii=False, indent=2))
        return 0

    stamp = datetime.now(TIMEZONE).strftime("%Y-%m-%d/%H%M%S-%f")
    run_dir = ROOT / "work/collection/daily" / stamp
    run_dir.mkdir(parents=True, exist_ok=True)
    plan["runDirectory"] = str(run_dir.relative_to(ROOT))
    (run_dir / "plan.json").write_text(json.dumps(plan, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(plan, ensure_ascii=False, indent=2), flush=True)
    status = 0
    for index, group in enumerate(plan["groups"], 1):
        automatic = [name for name in group["channels"] if name not in MANUAL]
        if not automatic:
            continue
        output = run_dir / f"candidates-{index}.json"
        # No --refresh: a same-day retry reuses the one-day cache instead of downloading everything again.
        result = subprocess.run([sys.executable, str(ROOT / "scripts/collect.py"), "--since", group["since"],
                                 "--until", plan["until"], "--channels", ",".join(automatic), "--output", str(output)], cwd=ROOT)
        status = status or result.returncode
        if output.exists():
            subprocess.run([sys.executable, str(ROOT / "scripts/review_queue.py"), "add", str(output)], cwd=ROOT, check=True)
    if not plan["groups"]:
        print("今天没有到期的检索渠道。")
    elif status:
        print("部分来源失败或截断；对应渠道的检查点不会推进，下次继续。", file=sys.stderr)
    for item in plan["manual"]:
        print(f"今日到期的手动渠道 {item['channel']}：{item['todo']}")
    print("候选已并入 work/collection/queue.json；用 npm run queue -- top 查看待审。")
    return status


if __name__ == "__main__":
    sys.exit(main())
