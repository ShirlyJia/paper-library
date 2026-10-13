"""Collect review candidates from independent sources; never publish automatically."""
import argparse
import calendar
import gzip
import hashlib
import json
import re
import sys
import time
import unicodedata
import urllib.parse
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from datetime import date
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
NS = {"a": "http://www.w3.org/2005/Atom", "x": "http://arxiv.org/schemas/atom", "o": "http://a9.com/-/spec/opensearch/1.1/"}


def normalize(value):
    return re.sub(r"[^\w]", "", unicodedata.normalize("NFKC", value).casefold())


def arxiv_id(value):
    match = re.search(r"(?:arxiv[-:/]|arxiv\.org/(?:abs|pdf|html)/)(\d{4}\.\d{4,5})(?:v\d+)?", value, re.I)
    return match.group(1) if match else None


def keys(record):
    values = [record.get("id", ""), record.get("url", ""), *record.get("sources", [])]
    found = {"arxiv:" + aid for value in values if (aid := arxiv_id(value))}
    if record.get("consensusId"):
        found.add("consensus:" + record["consensusId"])
    found.update("url:" + value.rstrip("/") for value in values if value.startswith("https://"))
    for value in values:
        url = urllib.parse.urlparse(value)
        if url.netloc == "openreview.net" and (identifier := urllib.parse.parse_qs(url.query).get("id")):
            found.add("openreview:" + identifier[0])
        if url.netloc == "doi.org":
            found.add("doi:" + url.path.lstrip("/").casefold())
    if record.get("doi"):
        found.add("doi:" + record["doi"].casefold().removeprefix("https://doi.org/"))
    if record.get("title"):
        found.add("title:" + normalize(record["title"]))
    return found


class Links(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links = []

    def handle_starttag(self, tag, attrs):
        if tag == "a" and (href := dict(attrs).get("href")):
            self.links.append(href)


class Proceedings(HTMLParser):
    def __init__(self):
        super().__init__()
        self.records, self.current, self.in_title = [], None, False

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "div" and attrs.get("class") == "paper":
            self.current = {"title": "", "sources": []}
        if self.current is not None:
            if tag == "p" and attrs.get("class") == "title":
                self.in_title = True
            if tag == "a" and (href := attrs.get("href")):
                self.current["sources"].append(href)

    def handle_data(self, value):
        if self.in_title and self.current is not None:
            self.current["title"] += value

    def handle_endtag(self, tag):
        if tag == "p":
            self.in_title = False
        if tag == "div" and self.current is not None:
            self.current["title"] = " ".join(self.current["title"].split())
            self.records.append(self.current)
            self.current = None


def parse_atom(raw):
    tree = ET.fromstring(raw)
    total = tree.findtext("o:totalResults", namespaces=NS)
    entries = []
    for entry in tree.findall("a:entry", NS):
        def text(key):
            return " ".join(entry.findtext(key, default="", namespaces=NS).split())
        identifier = arxiv_id(text("a:id"))
        if not identifier:
            raise ValueError("arXiv returned an entry without a valid paper ID")
        entries.append({"id": "arxiv-" + identifier, "title": text("a:title"),
                        "date": text("a:published")[:10], "updated": text("a:updated")[:10],
                        "abstract": text("a:summary"), "comment": text("x:comment"),
                        "journal": text("x:journal_ref"), "doi": text("x:doi"), "url": "https://arxiv.org/abs/" + identifier})
    return entries, int(total) if total is not None else len(entries)


def merge_candidates(records, papers):
    merged, lookup = [], {}
    for record in records:
        record_keys = keys(record)
        strong = set().union(*(lookup.get(key, set()) for key in record_keys if not key.startswith("title:")))
        title_matches = set().union(*(lookup.get(key, set()) for key in record_keys if key.startswith("title:")))
        # A shared title alone cannot disambiguate multiple works.
        matches = strong or (title_matches if len(title_matches) == 1 else set())
        for index in list(matches):
            old_keys = keys(merged[index])
            for namespace in ["arxiv:", "doi:"]:
                left = {k for k in record_keys if k.startswith(namespace)}
                right = {k for k in old_keys if k.startswith(namespace)}
                if left and right and not left & right:
                    matches.discard(index)
        if matches:
            index = min(matches)
            target = merged[index]
            for other in matches - {index}:
                absorbed = merged[other]
                for field in ["sources", "discoveredVia", "retrievalEvidence"]:
                    target[field] = list(dict.fromkeys(target.get(field, []) + absorbed.get(field, [])))
                for field, value in absorbed.items():
                    if value and not target.get(field):
                        target[field] = value
                for key, values in lookup.items():
                    if other in values:
                        values.discard(other)
                        values.add(index)
                merged[other] = None
            for field, value in record.items():
                if field in ["sources", "discoveredVia", "retrievalEvidence"]:
                    target[field] = list(dict.fromkeys(target.get(field, []) + value))
                elif value and not target.get(field):
                    target[field] = value
        else:
            index = len(merged)
            merged.append(dict(record))
        for key in record_keys:
            lookup.setdefault(key, set()).add(index)
    existing = {}
    for paper in papers:
        for key in keys(paper):
            existing[key] = paper["id"]
    result = []
    for record in filter(None, merged):
        record["existingIds"] = sorted({existing[k] for k in keys(record) if k in existing})
        record["reviewState"] = "existing-check-update" if record["existingIds"] else "needs-review"
        result.append(record)
    return sorted(result, key=lambda p: (p.get("date", ""), p.get("title", "")), reverse=True)


def apply_decisions(candidates, decisions):
    by_key = {key: decision for decision in decisions for key in keys(decision)}
    for candidate in candidates:
        previous = next((by_key[k] for k in keys(candidate) if k in by_key), None)
        if not previous:
            continue
        candidate["previousDecision"] = previous
        if candidate["existingIds"]:
            continue
        revised = candidate.get("updated", "") > previous.get("sourceUpdated", "")
        candidate["reviewState"] = "needs-review" if revised or previous["decision"] == "included" else previous["decision"]


def main():
    from discovery import discover
    today = date.today()
    month = today.month - 6
    year = today.year - (month <= 0)
    month = month if month > 0 else month + 12
    since = date(year, month, min(today.day, calendar.monthrange(year, month)[1]))
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--since", type=date.fromisoformat)
    cli.add_argument("--until", type=date.fromisoformat)
    cli.add_argument("--output", type=Path, default=ROOT / "work/collection/latest.json")
    cli.add_argument("--max-pages", type=int, default=10)
    cli.add_argument("--refresh", action="store_true", help="Ignore the one-day HTTP cache")
    cli.add_argument("--channels", default="arxiv,formal,fulltext,semantic,citations,references",
                     help="Comma-separated discovery channels; default runs all")
    cli.add_argument("--resume", type=Path, help="Continue OpenAlex cursors and preserve candidates from a previous report")
    args = cli.parse_args()
    previous = json.loads(args.resume.read_text()) if args.resume else {}
    args.since = args.since or date.fromisoformat(previous.get("since", since.isoformat()))
    args.until = args.until or date.fromisoformat(previous.get("until", today.isoformat()))
    if args.since > args.until or args.max_pages < 1:
        cli.error("Invalid date range or page limit")
    channels = set(args.channels.split(","))
    if not channels or channels - {"arxiv", "formal", "fulltext", "semantic", "citations", "references"}:
        cli.error("Unknown discovery channel")
    config = json.loads((ROOT / "research/sources.json").read_text())
    config["_resumeRuns"] = previous.get("runs", [])
    config["_resumeCandidates"] = previous.get("candidates", [])
    families = json.loads((ROOT / "research/model-families.json").read_text())["families"]
    names = sorted({family["name"] for family in families})
    config["relevancePattern"] += "|" + "|".join(r"\b" + re.escape(name) + r"\b" for name in names)
    for index in range(0, len(names), 12):
        config["arxivQueries"].append({"id": f"registered-families-{index // 12 + 1}",
                                       "query": " OR ".join('all:"' + name.replace('"', '') + '"' for name in names[index:index + 12])})
    papers = json.loads((ROOT / "data/papers.json").read_text())["papers"]
    cache = ROOT / "work/collection/cache"
    cache.mkdir(parents=True, exist_ok=True)
    last_arxiv, last_openalex, openalex_requests = 0.0, 0.0, 0
    unavailable_hosts = {}

    def fetch(url):
        nonlocal last_arxiv, last_openalex, openalex_requests
        path = cache / (hashlib.sha256(url.encode()).hexdigest() + ".txt")
        if not args.refresh and path.exists() and time.time() - path.stat().st_mtime < 86400:
            return path.read_text()
        host = urllib.parse.urlparse(url).hostname
        if host in unavailable_hosts:
            raise RuntimeError(f"Source temporarily unavailable in this run ({unavailable_hosts[host]}); retry later")
        if "export.arxiv.org" in url:
            time.sleep(max(0, 3.1 - (time.monotonic() - last_arxiv)))
            last_arxiv = time.monotonic()
        if urllib.parse.urlparse(url).hostname == "api.openalex.org":
            if openalex_requests >= config.get("openalexRequestLimit", 75):
                raise RuntimeError("Keyless OpenAlex request budget reached; resume missing lanes in a later run")
            time.sleep(max(0, 1.1 - (time.monotonic() - last_openalex)))
            last_openalex = time.monotonic()
            openalex_requests += 1
        request = urllib.request.Request(url, headers={"User-Agent": "StructuredDataPaperLibrary/2.0 (shared research index)",
                                                       "Accept-Encoding": "gzip"})
        try:
            with urllib.request.urlopen(request, timeout=90) as response:
                body = response.read()
                if response.headers.get("Content-Encoding") == "gzip":
                    body = gzip.decompress(body)
                raw = body.decode("utf-8")
        except urllib.error.HTTPError as error:
            if error.code in (429, 503):
                unavailable_hosts[host] = f"HTTP {error.code}"
            raise
        path.write_text(raw)
        return raw

    records, runs = [], []
    stamp = lambda d, end=False: d.strftime("%Y%m%d") + ("2359" if end else "0000")
    window = f"[{stamp(args.since)} TO {stamp(args.until, True)}]"
    for lane in config["arxivQueries"] if "arxiv" in channels else []:
        count, total = 0, None
        query = f'({lane["query"]}) AND (submittedDate:{window} OR lastUpdatedDate:{window})'
        try:
            for page in range(args.max_pages):
                url = "https://export.arxiv.org/api/query?" + urllib.parse.urlencode({"search_query": query, "start": page * 100, "max_results": 100, "sortBy": "submittedDate", "sortOrder": "descending"})
                entries, total = parse_atom(fetch(url))
                for p in entries:
                    p["sources"], p["discoveredVia"] = [p["url"]], [lane["id"]]
                    p["timeClass"] = "new" if p["date"] >= args.since.isoformat() else "revision-or-background"
                records.extend(entries)
                count += len(entries)
                if count >= total or not entries:
                    break
            runs.append({"source": lane["id"], "query": query, "count": count, "total": total, "status": "complete" if count >= total else "truncated"})
        except Exception as error:
            runs.append({"source": lane["id"], "count": count, "status": "failed", "error": str(error)})
        print(json.dumps(runs[-1], ensure_ascii=False), flush=True)

    new_records, new_runs = discover(config, fetch, args.since, args.until, args.max_pages, papers,
                                    lambda run: print(json.dumps(run, ensure_ascii=False), flush=True), channels)
    records.extend(new_records)
    runs.extend(new_runs)

    for source in config["referenceSources"] if "references" in channels else []:
        try:
            raw = fetch(source["url"])
            parser = Links()
            parser.feed(raw)
            links = list(dict.fromkeys(parser.links + re.findall(r'https?://[^\s<>"\)]+', raw)))
            found = []
            for link in links:
                link = urllib.parse.urljoin(source["url"], link)
                identifier = arxiv_id(link)
                if identifier:
                    found.append({"id": "arxiv-" + identifier, "url": "https://arxiv.org/abs/" + identifier, "sources": [link], "discoveredVia": [source["url"]]})
                else:
                    parsed = urllib.parse.urlparse(link)
                    review = urllib.parse.parse_qs(parsed.query).get("id")
                    if parsed.netloc == "openreview.net" and parsed.path in ("/forum", "/pdf") and review:
                        found.append({"url": "https://openreview.net/forum?id=" + review[0], "sources": [link], "discoveredVia": [source["url"]]})
                    elif parsed.netloc == "proceedings.mlr.press" and parsed.path.endswith(".html"):
                        found.append({"url": link, "sources": [link], "discoveredVia": [source["url"]]})
            records.extend(found)
            runs.append({"source": source["url"], "status": "complete", "linkedCandidates": len(found)})
        except Exception as error:
            runs.append({"source": source["url"], "status": "failed", "error": str(error)})
        print(json.dumps(runs[-1], ensure_ascii=False), flush=True)

    candidates = merge_candidates(records, papers)
    if previous:
        # Keep failures from channels that were not retried. A narrow resume must
        # not turn an incomplete all-source run into a claim of complete coverage.
        new_sources = {r["source"] for r in runs}
        retained = [r for r in previous.get("runs", []) if r.get("query") or r["source"] not in new_sources]
        run_key = lambda r: (r["source"], json.dumps(r.get("query"), sort_keys=True))
        combined = {run_key(r): r for r in retained + runs}
        runs = list(combined.values())
    decisions_path = ROOT / "research/decisions.json"
    if decisions_path.exists():
        apply_decisions(candidates, json.loads(decisions_path.read_text()))
    incomplete = any(run["status"] != "complete" for run in runs)
    report = {"generatedAt": today.isoformat(), "since": str(args.since), "until": str(args.until),
              "incomplete": incomplete, "channels": sorted(channels | set(previous.get("channels", []))), "runs": runs,
              "manualSources": config["manualSources"], "candidates": candidates}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(f"候选 {len(candidates)} 条；来源失败或截断 {sum(r['status'] != 'complete' for r in runs)} 项；输出 {args.output}")
    return 2 if incomplete else 0


if __name__ == "__main__":
    sys.exit(main())
