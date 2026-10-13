"""Merge Consensus search/fetch exports into the local review queue, not the site."""
import argparse
import json
import re
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

from collect import ROOT, apply_decisions, merge_candidates


def canonical_url(value):
    url = urlsplit(value or "")
    if url.scheme != "https" or url.hostname not in ("consensus.app", "www.consensus.app"):
        raise ValueError("Expected a canonical HTTPS Consensus paper URL")
    return urlunsplit((url.scheme, url.netloc, url.path, "", ""))


def normalize_export(bundle):
    fetched = {paper["id"]: paper for paper in bundle.get("papers", [])}
    candidates, runs = [], []
    for search in bundle["searches"]:
        lane = "consensus:" + search["id"]
        if search["status"] != "complete":
            runs.append({"source": lane, "status": "failed", "query": search["query"],
                         "error": search.get("error", "Connector search failed")})
            continue
        hits = search["results"]
        pending = []
        for hit in hits:
            paper = fetched.get(hit["id"])
            metadata = paper.get("metadata", {}) if paper else {}
            url = canonical_url((paper or hit)["url"])
            candidate = {
                "consensusId": hit["id"], "title": (paper or hit)["title"],
                "url": url, "sources": [url], "discoveredVia": [lane],
                "retrievalEvidence": ["consensus:full-record" if paper else "consensus:search-snippet"],
                "fetchState": "complete" if paper else "pending", "needsPrimaryVerification": True,
            }
            if paper:
                candidate["abstract"] = paper.get("text", "")
                candidate["providerMetadata"] = metadata
                year = str(metadata.get("publish_year", ""))
                if re.fullmatch(r"\d{4}", year):
                    candidate["date"] = year
                    candidate["dateSource"] = "Consensus year only; verify earliest release on primary source"
                if metadata.get("doi"):
                    candidate["doi"] = metadata["doi"]
            else:
                candidate["discoverySnippet"] = hit.get("text", "")
                pending.append(hit["id"])
            candidates.append(candidate)
        runs.append({"source": lane, "status": "complete", "query": search["query"],
                     "count": len(hits), "fullRecords": len(hits) - len(pending),
                     "pendingFetchIds": pending, "coverage": "ranked-results; not an exhaustive index"})
    return candidates, runs


def main():
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--input", required=True, type=Path)
    cli.add_argument("--base", type=Path, help="Existing collector report to augment")
    cli.add_argument("--output", required=True, type=Path)
    args = cli.parse_args()
    if args.output.resolve() == (ROOT / "data/papers.json").resolve():
        cli.error("Unreviewed candidates cannot overwrite the public catalog")
    bundle = json.loads(args.input.read_text())
    base = json.loads(args.base.read_text()) if args.base else {}
    records, runs = normalize_export(bundle)
    papers = json.loads((ROOT / "data/papers.json").read_text())["papers"]
    candidates = merge_candidates([*base.get("candidates", []), *records], papers)
    apply_decisions(candidates, json.loads((ROOT / "research/decisions.json").read_text()))
    new_sources = {run["source"] for run in runs}
    combined_runs = [r for r in base.get("runs", []) if r["source"] not in new_sources] + runs
    report = {**base, "generatedAt": bundle["generatedAt"], "since": base.get("since", bundle["since"]),
              "until": base.get("until", bundle["until"]), "runs": combined_runs, "candidates": candidates,
              "channels": sorted(set(base.get("channels", [])) | {"consensus"}),
              "incomplete": any(r["status"] != "complete" for r in combined_runs)}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(f"Consensus 命中 {len(records)} 条；合并候选 {len(candidates)} 条；公开目录未修改。")
    return 2 if report["incomplete"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
