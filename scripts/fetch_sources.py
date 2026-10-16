"""Download primary sources as readable text for full-text review, or audit registered model families.

  python3 scripts/fetch_sources.py jobs.json --out RUN/primary     jobs: [{"name": "...", "url": "..."}]
  python3 scripts/fetch_sources.py --families --out RUN/families   official source of every family (weekly)

Only text and a SHA-256 are kept; raw HTML/PDF is discarded unless --keep-raw. For arXiv,
prefer https://arxiv.org/html/ID (no PDF parser needed). PDFs need the optional `pypdf` package.
"""
import argparse
import concurrent.futures
import hashlib
import io
import json
import re
import sys
import urllib.request
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BLOCKS = {"p", "h1", "h2", "h3", "h4", "h5", "li", "figcaption", "tr", "div"}


class Reader(HTMLParser):
    """Paragraph-preserving text; MathML becomes its alttext; links are kept for reference follow-up."""

    def __init__(self):
        super().__init__()
        self.out, self.links, self.skip, self.math = [], [], 0, 0

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag in ("script", "style", "nav"):
            self.skip += 1
        if tag == "math":
            if not self.skip and not self.math:
                self.out.append(attrs.get("alttext", "[math]"))
            self.math += 1
        if tag == "a" and attrs.get("href", "").startswith(("http://", "https://")):
            self.links.append(attrs["href"])

    def handle_endtag(self, tag):
        if tag in ("script", "style", "nav"):
            self.skip = max(0, self.skip - 1)
        if tag == "math":
            self.math = max(0, self.math - 1)
        if tag in BLOCKS:
            self.out.append("\n\n")

    def handle_data(self, data):
        if not self.skip and not self.math:
            self.out.append(data)

    def text(self):
        return "\n\n".join(" ".join(part.split()) for part in "".join(self.out).split("\n\n") if part.strip())


def to_text(body):
    if body.startswith(b"%PDF"):
        try:
            from pypdf import PdfReader
        except ImportError:
            raise RuntimeError("PDF needs `pip install pypdf`; or fetch the arXiv/publisher HTML version") from None
        pages = PdfReader(io.BytesIO(body)).pages
        return "\n".join(f"\nPAGE {i + 1}\n" + (page.extract_text() or "") for i, page in enumerate(pages)), []
    reader = Reader()
    reader.feed(body.decode("utf-8", "replace"))
    return reader.text(), list(dict.fromkeys(reader.links))


def fetch(job, out, keep_raw):
    try:
        request = urllib.request.Request(job["url"], headers={"User-Agent": "StructuredDataPaperLibrary/2.0 (shared research index)"})
        with urllib.request.urlopen(request, timeout=45) as response:
            body, final = response.read(), response.url
        text, links = to_text(body)
        (out / f"{job['name']}.txt").write_text(text)
        if keep_raw:
            (out / (job["name"] + (".pdf" if body.startswith(b"%PDF") else ".html"))).write_bytes(body)
        return {**job, "finalUrl": final, "status": "fetched", "characters": len(text),
                "sha256": hashlib.sha256(body).hexdigest(), "file": str(out / f"{job['name']}.txt"), "links": links}
    except Exception as error:
        return {**job, "status": "failed", "error": str(error)}


def family_jobs():
    """One official (non-arXiv) source per family, falling back to its latest arXiv abstract."""
    jobs = []
    for index, family in enumerate(json.loads((ROOT / "research/model-families.json").read_text())["families"]):
        official = [u for u in family["sources"] if "arxiv.org" not in u] or [u for u in family["sources"] if "/abs/" in u]
        if official:
            jobs.append({"name": f"{index:02d}-{re.sub(r'[^A-Za-z0-9]+', '-', family['name']).strip('-')}",
                         "family": family["name"], "url": official[-1].removesuffix(".git")})
    return jobs


def release_clues(text):
    lines = [line for line in text.split("\n\n") if len(line) < 1200]
    return [line[:400] for line in lines if re.search(r"(?i)\b(release[sd]?|v\d+(\.\d+)+|changelog|new version)\b", line)][:10]


def main():
    cli = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    cli.add_argument("jobs", nargs="?", type=Path)
    cli.add_argument("--families", action="store_true")
    cli.add_argument("--out", type=Path, required=True)
    cli.add_argument("--keep-raw", action="store_true")
    args = cli.parse_args()
    if bool(args.jobs) == args.families:
        cli.error("Give a jobs file or --families")
    jobs = family_jobs() if args.families else json.loads(args.jobs.read_text())
    args.out.mkdir(parents=True, exist_ok=True)
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(lambda job: fetch(job, args.out, args.keep_raw), jobs))
    if args.families:
        for result in results:
            if result["status"] == "fetched":
                result["releaseClues"] = release_clues(Path(result["file"]).read_text())
    log = args.out / "fetches.json"
    previous = json.loads(log.read_text()) if log.exists() else []
    log.write_text(json.dumps(previous + results, ensure_ascii=False, indent=2) + "\n")
    failed = [r for r in results if r["status"] != "fetched"]
    if args.families:
        # Same run format as collector reports, so collect:finish can advance the weekly families checkpoint.
        runs = [{"source": r["url"], "channel": "families", "status": "complete" if r["status"] == "fetched" else "failed",
                 **({"error": r["error"]} if "error" in r else {})} for r in results]
        (args.out.parent / "families-report.json").write_text(json.dumps({"runs": runs}, ensure_ascii=False, indent=2) + "\n")
    for result in failed:
        print(f"失败：{result['url']} — {result['error']}", file=sys.stderr)
    print(f"已获取 {len(results) - len(failed)}/{len(results)}；记录见 {log}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
