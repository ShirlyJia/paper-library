"""Persistent, ranked review queue across runs. Ranking orders work; it never drops candidates.

  python3 scripts/review_queue.py add REPORT [REPORT ...]   merge collector / Consensus reports
  python3 scripts/review_queue.py top [-n 40]              list open items, highest priority first
  python3 scripts/review_queue.py screen ID --verdict not-relevant|needs-fulltext --reason TEXT

Screening is an abstract-level triage note kept in work/ (not a public decision). A later
revision of the candidate reopens it, like deferred decisions in research/decisions.json.
"""
import argparse
import json
import re
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parent))
from collect import ROOT, apply_decisions, family_queries, keys, merge_candidates  # noqa: E402

QUEUE = ROOT / "work/collection/queue.json"
SCREENING = ROOT / "work/collection/screening.json"
VERDICTS = {"not-relevant", "needs-fulltext"}


def today():
    return datetime.now(ZoneInfo("Asia/Shanghai")).date().isoformat()


def read(path, default):
    return json.loads(path.read_text()) if path.exists() else default


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")
    temporary.replace(path)


def relevance_pattern():
    config = json.loads((ROOT / "research/sources.json").read_text())
    _, names = family_queries(json.loads((ROOT / "research/model-families.json").read_text())["families"])
    return re.compile(config["relevancePattern"] + "|" + "|".join(r"\b" + re.escape(n) + r"\b" for n in names), re.I)


def score(item, pattern):
    """Higher first: topical title, independent channels, recent, has an abstract to screen."""
    lanes = {"official" if via.startswith("http") else ":".join(via.split(":")[:2]) if ":" in via else "arxiv"
             for via in item.get("discoveredVia", [])}
    value = 3 * bool(pattern.search(item.get("title") or "")) + bool(pattern.search(item.get("abstract") or ""))
    value += 2 * min(len(lanes) - 1, 3) + (item.get("timeClass") == "new")
    return value - (not item.get("abstract"))


def needs_update_check(item, papers):
    """Existing papers only reopen when the source shows a newer revision or a venue record."""
    paper = papers.get(item["existingIds"][0]) if item.get("existingIds") else None
    if not paper:
        return False
    newer = (item.get("updated") or "") > paper.get("updated", "")
    venue = paper.get("status") == "preprint" and bool(item.get("officialDecision") or item.get("venue"))
    return newer or venue


def refresh(items, screening):
    catalogue = json.loads((ROOT / "data/papers.json").read_text())
    papers = {p["id"]: p for p in catalogue["papers"]}
    merged = merge_candidates(items, catalogue["papers"])
    apply_decisions(merged, json.loads((ROOT / "research/decisions.json").read_text()))
    notes = {key: note for note in screening for key in keys(note)}
    pattern, result = relevance_pattern(), []
    for item in merged:
        note = next((notes[k] for k in keys(item) if k in notes), None)
        if note and (item.get("updated") or item.get("date") or "") <= note.get("sourceUpdated", ""):
            item["screen"] = note
        else:
            item.pop("screen", None)
        state = item["reviewState"]
        if state == "existing-check-update":
            item["open"] = needs_update_check(item, papers)
        else:
            item["open"] = state == "needs-review" and (item.get("screen") or {}).get("verdict") != "not-relevant"
        if not item["open"] and state != "needs-review" and not item.get("screen"):
            continue  # decided or unchanged: the next collection re-adds it if a revision appears
        item["score"] = score(item, pattern)
        result.append(item)
    result.sort(key=lambda x: x.get("date") or "", reverse=True)
    return sorted(result, key=lambda x: (not x["open"], -x["score"]))


def add(reports):
    queue = read(QUEUE, {"items": []})
    day, incoming = today(), []
    for path in reports:
        for item in json.loads(Path(path).read_text()).get("candidates", []):
            incoming.append({**item, "lastSeen": day})
    # New records first so fresher abstracts and lastSeen win; old firstSeen fills in when merged.
    items = refresh(incoming + queue["items"], read(SCREENING, []))
    for item in items:
        item.setdefault("firstSeen", day)
    write(QUEUE, {"updatedAt": day, "items": items})
    print(f"队列 {len(items)} 条，其中待处理 {sum(i['open'] for i in items)} 条。")


def top(limit):
    items = [i for i in read(QUEUE, {"items": []})["items"] if i["open"]]
    for item in items[:limit]:
        kind = "更新核对" if item.get("existingIds") else (item.get("screen") or {}).get("verdict", "待初筛")
        print(f'{item["score"]:>3}  {item.get("date") or "????":<10} {kind:<14} {item.get("id") or item.get("url")}  {item.get("title", "")[:90]}')
    print(f"共 {len(items)} 条待处理。")


def review_packet(items, limit=20, backlog=5):
    """Bound model input, not recall. Reserve slots for old, possibly low-score leads."""
    opened = [i for i in items if i.get("open")]
    head = opened[:limit]
    older = sorted(opened[limit:], key=lambda i: (i.get("firstSeen", ""), i.get("id", "")))[:backlog]
    fields = ("id", "title", "url", "date", "updated", "firstSeen", "score", "discoveredVia", "reviewState")
    return {"openTotal": len(opened), "selected": len(head + older), "items": [
        {**{k: item[k] for k in fields if k in item}, "abstract": (item.get("abstract") or "")[:1600],
         "abstractTruncated": len(item.get("abstract") or "") > 1600,
         "selection": "backlog" if index >= len(head) else "ranked"}
        for index, item in enumerate(head + older)]}


def screen(identifier, verdict, reason):
    queue = read(QUEUE, {"items": []})
    item = next((i for i in queue["items"] if identifier in (i.get("id"), i.get("url"))), None)
    if not item:
        raise SystemExit(f"队列中没有 {identifier}")
    screening = [n for n in read(SCREENING, []) if not keys(n) & keys(item)]
    screening.append({"id": item.get("id"), "url": item.get("url"), "title": item.get("title"), "doi": item.get("doi"),
                      "verdict": verdict, "reason": reason, "screenedAt": today(),
                      "sourceUpdated": item.get("updated") or item.get("date") or ""})
    write(SCREENING, screening)
    queue["items"] = refresh(queue["items"], screening)
    write(QUEUE, queue)
    print(f"已记录初筛：{identifier} → {verdict}")


def screen_batch(path):
    queue = read(QUEUE, {"items": []})
    by_id = {value: i for i in queue["items"] for value in (i.get("id"), i.get("url")) if value}
    notes = read(SCREENING, [])
    for row in json.loads(path.read_text()):
        item = by_id.get(row.get("id"))
        if not item or row.get("verdict") not in VERDICTS or not row.get("reason", "").strip():
            raise ValueError("批量初筛包含未知 ID、无效结论或空理由；未写入")
        notes = [n for n in notes if not keys(n) & keys(item)]
        notes.append({**{k: item.get(k) for k in ("id", "url", "title", "doi")},
                      "verdict": row["verdict"], "reason": row["reason"], "screenedAt": today(),
                      "sourceUpdated": item.get("updated") or item.get("date") or ""})
    refreshed = refresh(queue["items"], notes)
    write(SCREENING, notes)
    write(QUEUE, {**queue, "items": refreshed})
    print("批量初筛已记录；未公开收录任何论文。")


def main():
    cli = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = cli.add_subparsers(dest="command", required=True)
    sub.add_parser("add").add_argument("reports", nargs="+")
    sub.add_parser("screen-batch").add_argument("input", type=Path)
    sub.add_parser("top").add_argument("-n", type=int, default=40)
    p = sub.add_parser("packet", help="Write a bounded abstract triage packet; never removes candidates")
    p.add_argument("--limit", type=int, default=20)
    p.add_argument("--backlog", type=int, default=5)
    p.add_argument("--output", type=Path, required=True)
    s = sub.add_parser("screen")
    s.add_argument("identifier")
    s.add_argument("--verdict", required=True, choices=sorted(VERDICTS))
    s.add_argument("--reason", required=True)
    args = cli.parse_args()
    if args.command == "add":
        add(args.reports)
    elif args.command == "screen-batch":
        screen_batch(args.input)
    elif args.command == "top":
        top(args.n)
    elif args.command == "packet":
        if args.limit < 0 or args.backlog < 0 or args.limit + args.backlog < 1:
            cli.error("packet sizes must be nonnegative with a positive total")
        packet = review_packet(read(QUEUE, {"items": []})["items"], args.limit, args.backlog)
        write(args.output, packet)
        print(f"初筛包 {packet['selected']} / 待审 {packet['openTotal']} 条：{args.output}")
    else:
        screen(args.identifier, args.verdict, args.reason)


if __name__ == "__main__":
    main()
