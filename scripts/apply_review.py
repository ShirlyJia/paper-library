"""Apply one run's reviewed decisions to the catalogue, decision log and family registry.

Input (JSON), each list optional:
  {"date": "YYYY-MM-DD",
   "included":  [{"paper": {...}, "qualityReview": {...}, "valueAssessment": {"decision": "include", "comparison": "相对前作/已有条目的增量", "reason": "得到证据支持的独立收录价值"}, "brief": "一句话：它是什么", "name": "简称（可选）", "family": "Name"}],
   "corrected": [{"paper": {...}, "qualityReview": {...}, "brief": "一句话：改了什么", "reason": "..."}],
   "deferred":  [{"id", "title", "url", "sourceUpdated", "reason", "qualityReview"?}],
   "excluded":  [{"id", "title", "url", "sourceUpdated", "reason"}],
   "withdrawn": [{"id", "decision": "deferred|excluded", "reason", "restoreWhen", "qualityReview": {...}, "valueAssessment": {...}}]}

Afterwards run `npm run record:updates` and `npm run check`. `npm run collect:finish` later builds the
run briefing from the same file.
"""
import argparse
import copy
import json
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REVIEW_FIELDS = ["claim", "contribution", "evidence", "limitations", "value", "reproducibility",
                 "conclusion", "sources", "readScope"]
CONCLUSIONS = {"证据已支持", "有迹象但证据不足", "现有证据不支持"}
PAPER_FIELDS = ["id", "title", "date", "updated", "category", "section", "topicId", "status", "venue", "summary", "url"]


def check_review(review, paper_id):
    """New inclusions and method/result corrections need a completed full-text review (COLLECTION.md)."""
    if (review or {}).get("reviewStatus") != "completed":
        raise ValueError(f"{paper_id} 缺少 reviewStatus=completed 的质量审核；只读摘要请改为 deferred")
    missing = [field for field in REVIEW_FIELDS if not review.get(field)]
    if missing:
        raise ValueError(f"{paper_id} 质量审核缺少字段：{', '.join(missing)}")
    if review["conclusion"] not in CONCLUSIONS:
        raise ValueError(f"{paper_id} conclusion 必须是：{' / '.join(sorted(CONCLUSIONS))}")


def check_value(assessment, paper_id, expected):
    """Evidence support alone is not an inclusion decision; require an explicit value comparison."""
    if not isinstance(assessment, dict) or assessment.get("decision") != expected:
        raise ValueError(f"{paper_id} 缺少 valueAssessment.decision={expected} 的价值筛选")
    for field in ("comparison", "reason"):
        if not isinstance(assessment.get(field), str) or not assessment[field].strip():
            raise ValueError(f"{paper_id} 价值筛选缺少 {field}")


def decision(entry, kind, date, reason):
    paper = entry.get("paper", entry)
    record = {"id": paper["id"], "title": paper["title"], "url": paper["url"],
              "sourceUpdated": entry.get("sourceUpdated") or paper.get("updated") or paper.get("date"),
              "decision": kind, "reviewedAt": date, "reason": reason}
    if not record["reason"]:
        raise ValueError(f"{record['id']} 缺少决定理由")
    if entry.get("qualityReview"):
        record["qualityReview"] = entry["qualityReview"]
    if entry.get("valueAssessment"):
        record["valueAssessment"] = entry["valueAssessment"]
    if entry.get("restoreWhen"):
        record["restoreWhen"] = entry["restoreWhen"]
    return record


def apply(bundle, catalogue, decisions, registry, archive=None):
    date = bundle["date"]
    papers = {p["id"]: p for p in catalogue["papers"]}
    families = {f["name"]: f for f in registry["families"]}
    records = []
    entry_ids = [e.get("paper", e)["id"] for kind in ("included", "corrected", "deferred", "excluded", "withdrawn")
                 for e in bundle.get(kind, [])]
    if len(entry_ids) != len(set(entry_ids)):
        raise ValueError("同一批次的论文不能同时出现在多个决定中")
    for kind in ("included", "corrected"):
        for entry in bundle.get(kind, []):
            paper = dict(entry["paper"])
            missing = [field for field in PAPER_FIELDS if paper.get(field) in (None, "")]
            if missing:
                raise ValueError(f"{paper.get('id')} 缺少论文字段：{', '.join(missing)}")
            check_review(entry.get("qualityReview"), paper["id"])
            if kind == "included":
                check_value(entry.get("valueAssessment"), paper["id"], "include")
            if not 0 < len(entry.get("brief") or "") <= 80:
                raise ValueError(f"{paper['id']} 需要 brief：一句话（不超过 80 字）说明它是什么；更正写明改了什么")
            if kind == "included" and paper["id"] in papers:
                raise ValueError(f"{paper['id']} 已在目录中；请放入 corrected")
            if kind == "corrected":
                if paper["id"] not in papers:
                    raise ValueError(f"{paper['id']} 不在目录中，无法更正")
                paper["addedAt"] = papers[paper["id"]].get("addedAt")
            paper = {k: v for k, v in paper.items() if v is not None or k in ("pdf", "code")}
            papers[paper["id"]] = paper
            reason = entry.get("reason") or ("阅读相关方法与实验正文后收录；概览保留贡献、证据及使用限制。" if kind == "included"
                                             else "核对正文后更正方法或实验相关内容。")
            records.append(decision(entry, "included" if kind == "included" else "existing", date, reason))
            name = entry.get("family")
            if name:
                family = families.setdefault(name, {"name": name, "paperIds": [], "sources": []})
                if family not in registry["families"]:
                    registry["families"].append(family)
                family["paperIds"] = list(dict.fromkeys(family["paperIds"] + [paper["id"]]))
                family["sources"] = list(dict.fromkeys(family["sources"] + [paper["url"]]))
    for kind in ("deferred", "excluded"):
        for entry in bundle.get(kind, []):
            if entry["id"] in papers:
                raise ValueError(f"{entry['id']} 仍在公开目录；撤下请用 withdrawn 并保留恢复条件")
            records.append(decision(entry, kind, date, entry.get("reason")))
    for entry in bundle.get("withdrawn", []):
        paper_id = entry["id"]
        if archive is None or paper_id not in papers:
            raise ValueError(f"{paper_id} 撤下须提供归档且论文仍在公开目录")
        kind = entry.get("decision")
        if kind not in {"deferred", "excluded"} or not str(entry.get("restoreWhen") or "").strip():
            raise ValueError(f"{paper_id} 撤下须说明 deferred/excluded 和 restoreWhen")
        check_value(entry.get("valueAssessment"), paper_id, "defer" if kind == "deferred" else "exclude")
        review = entry.get("qualityReview") or {}
        if not review.get("sources") or not review.get("readScope"):
            raise ValueError(f"{paper_id} 撤下须保留实际审核来源和范围")
        paper = papers.pop(paper_id)
        records.append(decision({**entry, "paper": paper}, kind, date, entry.get("reason")))
        old = next((x for x in archive["papers"] if x["paper"]["id"] == paper_id), None)
        history = (old or {}).get("collectionHistory", []) + [
            {"date": day["date"], "kind": event} for day in catalogue.get("collectionUpdates", [])
            for event in ("added", "updated") if paper_id in day[event]]
        history = [dict(date=d, kind=k) for d, k in sorted({(h["date"], h["kind"]) for h in history})]
        archived = {"paper": copy.deepcopy(paper), "withheldAt": date, "reason": entry["reason"],
                    "restoreWhen": entry["restoreWhen"], "collectionHistory": history,
                    "qualityReview": copy.deepcopy(review), "valueAssessment": copy.deepcopy(entry["valueAssessment"])}
        if old:
            archived["previousWithdrawals"] = old.get("previousWithdrawals", []) + [
                {k: v for k, v in old.items() if k not in {"paper", "collectionHistory", "previousWithdrawals"}}]
        archive["papers"] = [x for x in archive["papers"] if x["paper"]["id"] != paper_id] + [archived]
        archive["updatedAt"] = date
    if bundle.get("withdrawn"):
        catalogue["collectionUpdates"] = [
            {"date": day["date"], **{kind: [i for i in day[kind] if i in papers] for kind in ("added", "updated")}}
            for day in catalogue.get("collectionUpdates", [])]
        catalogue["collectionUpdates"] = [day for day in catalogue["collectionUpdates"] if day["added"] or day["updated"]]
        catalogue["updatedAt"] = max(catalogue.get("updatedAt", date), date)
    order = [p["id"] for p in catalogue["papers"]]
    catalogue["papers"] = [papers[i] for i in order if i in papers] + [p for i, p in papers.items() if i not in order]
    # A later withdrawal must not erase the original inclusion decision on the same day.
    seen = {(r["id"], r["reviewedAt"], r["decision"]) for r in records}
    decisions[:] = [d for d in decisions if (d["id"], d.get("reviewedAt"), d.get("decision")) not in seen] + records
    return records


def display_name(paper):
    """Short label for the briefing: the first short alias (model name) when there is one."""
    alias = next((a for a in paper.get("aliases") or [] if len(a) <= 32), None)
    return alias or paper["title"]


def direction_digest(bundle, catalogue, site, overview):
    """Group additions by their catalogue direction and keep bibliographic corrections together."""
    topics = defaultdict(list)
    for kind in ("included", "corrected"):
        for entry in bundle.get(kind, []):
            p = entry["paper"]
            topics[p["category"], p["section"], p["topicId"]].append((kind, entry))

    directions, corrections = [], []
    for category in catalogue["categories"]:
        additions = []
        for section in category["children"]:
            for topic in section["children"]:
                rows = topics.pop((category["id"], section["id"], topic["id"]), [])
                for kind, entry in sorted(rows, key=lambda row: row[1]["paper"]["date"], reverse=True):
                    p = entry["paper"]
                    link = f"[{entry.get('name') or display_name(p)}]({p['url']})"
                    if kind == "corrected":
                        corrections.append(f"- {link} {entry['brief']}")
                    else:
                        venue = "" if p["status"] == "preprint" or p["venue"] in entry["brief"] else f"（{p['venue']}）"
                        additions.append(f"- {entry['brief']} {link}{venue}")
        if additions:
            heading = f"### [{category['name']}]({site}?category={category['id']}&sort=added)"
            directions.extend([heading, "", *additions, ""])
    if topics:
        raise ValueError(f"小报论文的主路径与站内目录不符：{list(topics)}")

    lines = []
    if directions:
        lines.extend(["## 按方向浏览", "", overview, "", *directions])
    if corrections:
        lines.extend(["## 论文更正", ""])
        if not directions:
            lines.extend([overview, ""])
        lines.extend(corrections)
    return "\n".join(lines).rstrip()


def main():
    cli = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    cli.add_argument("input", type=Path)
    cli.add_argument("--dry-run", action="store_true")
    args = cli.parse_args()
    paths = {name: ROOT / path for name, path in [("catalogue", "data/papers.json"), ("decisions", "research/decisions.json"),
                                                  ("registry", "research/model-families.json"),
                                                  ("archive", "research/withheld-papers.json")]}
    data = {name: json.loads(path.read_text()) for name, path in paths.items()}
    bundle = json.loads(args.input.read_text())
    try:
        records = apply(bundle, data["catalogue"], data["decisions"], data["registry"], data["archive"])
    except (KeyError, ValueError) as error:
        print(f"未写入任何文件：{error}", file=sys.stderr)
        return 1
    if not args.dry_run:
        for name, path in paths.items():
            path.write_text(json.dumps(data[name], ensure_ascii=False, indent=2) + "\n")
    counts = {k: len(bundle.get(k, [])) for k in ("included", "corrected", "deferred", "excluded", "withdrawn")}
    print(f"{'预检通过' if args.dry_run else '已写入'}：{counts}，决定记录 {len(records)} 条。下一步：npm run record:updates && npm run check")
    return 0


if __name__ == "__main__":
    sys.exit(main())
