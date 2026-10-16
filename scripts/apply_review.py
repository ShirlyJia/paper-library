"""Apply one run's reviewed decisions to the catalogue, decision log and family registry.

Input (JSON), each list optional:
  {"date": "YYYY-MM-DD",
   "included":  [{"paper": {...}, "qualityReview": {...}, "brief": "一句话：它是什么", "name": "简称（可选）", "family": "Name"}],
   "corrected": [{"paper": {...}, "qualityReview": {...}, "brief": "一句话：改了什么", "reason": "..."}],
   "deferred":  [{"id", "title", "url", "sourceUpdated", "reason", "qualityReview"?}],
   "excluded":  [{"id", "title", "url", "sourceUpdated", "reason"}]}

Afterwards run `npm run record:updates` and `npm run check`. `npm run collect:finish` later builds the
run briefing from the same file.
"""
import argparse
import json
import sys
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


def decision(entry, kind, date, reason):
    paper = entry.get("paper", entry)
    record = {"id": paper["id"], "title": paper["title"], "url": paper["url"],
              "sourceUpdated": entry.get("sourceUpdated") or paper.get("updated") or paper.get("date"),
              "decision": kind, "reviewedAt": date, "reason": reason}
    if not record["reason"]:
        raise ValueError(f"{record['id']} 缺少决定理由")
    if entry.get("qualityReview"):
        record["qualityReview"] = entry["qualityReview"]
    return record


def apply(bundle, catalogue, decisions, registry):
    date = bundle["date"]
    papers = {p["id"]: p for p in catalogue["papers"]}
    families = {f["name"]: f for f in registry["families"]}
    records = []
    for kind in ("included", "corrected"):
        for entry in bundle.get(kind, []):
            paper = dict(entry["paper"])
            missing = [field for field in PAPER_FIELDS if paper.get(field) in (None, "")]
            if missing:
                raise ValueError(f"{paper.get('id')} 缺少论文字段：{', '.join(missing)}")
            check_review(entry.get("qualityReview"), paper["id"])
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
            records.append(decision(entry, kind, date, entry.get("reason")))
    order = [p["id"] for p in catalogue["papers"]]
    catalogue["papers"] = [papers[i] for i in order] + [p for i, p in papers.items() if i not in order]
    seen = {(r["id"], r["reviewedAt"]) for r in records}
    decisions[:] = [d for d in decisions if (d["id"], d.get("reviewedAt")) not in seen] + records
    return records


# Short direction names used in the briefing; the catalogue keeps the full titles.
SHORT_DIRECTIONS = {1: "业界进展", 2: "预测与决策", 3: "因果分析", 4: "语义结构化", 5: "上下文与推理", 6: "微调与蒸馏"}


def display_name(paper):
    """Short label for the briefing: the first short alias (model name) when there is one."""
    alias = next((a for a in paper.get("aliases") or [] if len(a) <= 32), None)
    return alias or paper["title"]


def direction_digest(bundle, catalogue):
    """各方向上新：每个方向列出篇数，每篇一句话说明是什么。细节留在站内卡片和 decisions.json。"""
    names = {c["id"]: SHORT_DIRECTIONS.get(c["id"], c["name"]) for c in catalogue["categories"]}
    entries = [(kind, e) for kind in ("included", "corrected") for e in bundle.get(kind, [])]
    lines = ["## 各方向上新", ""]
    for category in sorted({e["paper"]["category"] for _, e in entries}):
        rows = sorted((x for x in entries if x[1]["paper"]["category"] == category), key=lambda x: x[1]["paper"]["date"], reverse=True)
        lines += [f"### {names.get(category, category)}（{len(rows)} 篇）", ""]
        for kind, entry in rows:
            p = entry["paper"]
            tag = "" if kind == "included" else "（更正）"
            venue = "" if p["status"] == "preprint" else f"（{p['venue']}）"
            lines.append(f"- **[{entry.get('name') or display_name(p)}]({p['url']})**{tag}：{entry['brief']}{venue}")
        lines.append("")
    return "\n".join(lines)


def main():
    cli = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    cli.add_argument("input", type=Path)
    cli.add_argument("--dry-run", action="store_true")
    args = cli.parse_args()
    paths = {name: ROOT / path for name, path in [("catalogue", "data/papers.json"), ("decisions", "research/decisions.json"),
                                                  ("registry", "research/model-families.json")]}
    data = {name: json.loads(path.read_text()) for name, path in paths.items()}
    bundle = json.loads(args.input.read_text())
    try:
        records = apply(bundle, data["catalogue"], data["decisions"], data["registry"])
    except (KeyError, ValueError) as error:
        print(f"未写入任何文件：{error}", file=sys.stderr)
        return 1
    if not args.dry_run:
        for name, path in paths.items():
            path.write_text(json.dumps(data[name], ensure_ascii=False, indent=2) + "\n")
    counts = {k: len(bundle.get(k, [])) for k in ("included", "corrected", "deferred", "excluded")}
    print(f"{'预检通过' if args.dry_run else '已写入'}：{counts}，决定记录 {len(records)} 条。下一步：npm run record:updates && npm run check")
    return 0


if __name__ == "__main__":
    sys.exit(main())
