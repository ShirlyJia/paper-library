"""Apply one run's reviewed decisions to the catalogue, decision log and family registry.

Input (JSON), each list optional:
  {"date": "YYYY-MM-DD",
   "included":  [{"paper": {...}, "qualityReview": {...}, "family": "Name"}],
   "corrected": [{"paper": {...}, "qualityReview": {...}, "reason": "..."}],
   "deferred":  [{"id", "title", "url", "sourceUpdated", "reason", "qualityReview"?}],
   "excluded":  [{"id", "title", "url", "sourceUpdated", "reason"}]}

Afterwards run `npm run record:updates` and `npm run check` as before. With --briefing PATH the
mechanical "完整清单" section of the run briefing is written from the same data.
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
STATUS = {"published": "已核实正式录用", "workshop": "Workshop", "preprint": "预印本；未核实正式录用", "report": "技术报告"}


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


def briefing_list(bundle, catalogue):
    """The mechanical 完整清单; the narrative summary above it is still written by the reviewer."""
    names = {c["id"]: c["name"] for c in catalogue["categories"]}
    entries = [(kind, e) for kind in ("included", "corrected") for e in bundle.get(kind, [])]
    lines = ["## 本次完整清单", ""]
    for category in sorted({e["paper"]["category"] for _, e in entries}):
        lines += [f"### {names.get(category, category)}", ""]
        rows = sorted((x for x in entries if x[1]["paper"]["category"] == category), key=lambda x: x[1]["paper"]["date"], reverse=True)
        for kind, entry in rows:
            p, q = entry["paper"], entry["qualityReview"]
            links = [f"[原文]({p['url']})"] + ([f"[PDF]({p['pdf']})"] if p.get("pdf") else []) + ([f"[代码]({p['code']})"] if p.get("code") else [])
            lines += [f"#### [{p['title']}]({p['url']})", "",
                      f"{'新增' if kind == 'included' else '更正'} · 首发 {p['date']} · 修订 {p['updated']} · {p['venue']}（{STATUS.get(p['status'], p['status'])}）", "",
                      p["summary"], "", f"审核依据：{q['evidence']}", "", f"关键限制：{q['limitations']}", "",
                      f"价值：{q['value']}", "", " · ".join(links), ""]
    deferred = bundle.get("deferred", [])
    if deferred:
        lines += ["## 暂缓", ""] + [f"- [{d['title']}]({d['url']})：{d['reason']}" for d in deferred] + [""]
    return "\n".join(lines)


def main():
    cli = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    cli.add_argument("input", type=Path)
    cli.add_argument("--briefing", type=Path, help="Write the 完整清单 markdown here")
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
        if args.briefing:
            args.briefing.write_text(briefing_list(bundle, data["catalogue"]))
    counts = {k: len(bundle.get(k, [])) for k in ("included", "corrected", "deferred", "excluded")}
    print(f"{'预检通过' if args.dry_run else '已写入'}：{counts}，决定记录 {len(records)} 条。下一步：npm run record:updates && npm run check")
    return 0


if __name__ == "__main__":
    sys.exit(main())
