"""Official proceedings, full-text search, semantic recall and citation discovery.

All outputs are review candidates. Search/index dates never certify first release,
and an aggregator's venue field never certifies acceptance or a presentation award.
"""
import calendar
import html
import json
import re
import urllib.parse
import xml.etree.ElementTree as ET


def clean(value):
    return " ".join(html.unescape(re.sub(r"<[^>]+>", " ", str(value or ""))).split())


def bib_fields(block):
    """Read balanced BibTeX values, including nested title/TeX braces."""
    fields, position = {}, 0
    pattern = re.compile(r"(?m)^\s*(\w+)\s*=\s*([\{\"])")
    while match := pattern.search(block, position):
        start = position = match.end()
        brace, depth = match[2] == "{", 1
        while position < len(block):
            char = block[position]
            if char == "\\":
                position += 2
                continue
            if brace and char == "{":
                depth += 1
            if (brace and char == "}") or (not brace and char == '"'):
                depth -= 1
                if not depth:
                    break
            position += 1
        if depth:
            raise ValueError("Unbalanced BibTeX field")
        fields[match[1].lower()] = clean(block[start:position].replace("{", "").replace("}", ""))
        position += 1
    return fields


def parse_bibliography(raw, venue):
    papers = []
    for block in re.split(r"(?mi)^@", raw)[1:]:
        if not block.lower().startswith("inproceedings{"):
            continue
        item = bib_fields(block)
        if not item.get("title") or not item.get("url"):
            raise ValueError("Proceedings entry lacks title or URL")
        papers.append({
            "title": item["title"], "abstract": item.get("abstract", ""),
            "url": item["url"], "pdf": item.get("pdf"), "venue": venue,
            "venueYear": item.get("year"), "booktitle": item.get("booktitle"),
            "sources": [u for u in [item["url"], item.get("pdf")] if u],
        })
    if not papers:
        raise ValueError("No proceedings articles found")
    return papers


def pmlr_volumes(raw, since_year, until_year, venue_pattern):
    volumes = []
    for item in re.findall(r"<li\b[^>]*>(.*?)</li>", raw, re.S | re.I):
        match = re.search(r'href=[\"\'](?:https://proceedings\.mlr\.press/)?(v\d+)/?[\"\']', item)
        years = [int(y) for y in re.findall(r"\b20\d\d\b", clean(item))]
        if match and years and since_year <= max(years) <= until_year and re.search(venue_pattern, clean(item), re.I):
            volumes.append({"name": clean(item), "url": f"https://proceedings.mlr.press/{match[1]}/"})
    if not volumes:
        raise ValueError("PMLR directory discovery returned no matching volumes")
    return volumes


def programme_links(raw, origin):
    links = re.findall(r'[\"\']([^\"\']*?/static/virtual/data/[^\"\']+\.json)[\"\']', raw)
    return list(dict.fromkeys(urllib.parse.urljoin(origin, path) for path in links))


def parse_programme(data, abstracts, source, year):
    items = data if isinstance(data, list) else data.get("results", [])
    if not items:
        raise ValueError("Conference programme has no paper entries")
    if isinstance(data, dict) and (data.get("next") or data.get("count", len(items)) > len(items)):
        raise ValueError("Conference programme is paginated or incomplete")
    papers = []
    for item in items:
        page = urllib.parse.urljoin(source["origin"], item["virtualsite_url"]) if item.get("virtualsite_url") else None
        url = item.get("paper_url") or page
        if not url:
            continue
        abstract = item.get("abstract") or abstracts.get(str(item["id"]), "")
        if isinstance(abstract, dict):
            abstract = abstract.get("abstract", "")
        papers.append({
            "title": clean(item.get("name") or item.get("title")), "abstract": clean(abstract),
            "url": url, "pdf": item.get("paper_pdf_url"), "venue": f'{source["name"]} {year}',
            "venueYear": str(year), "venueTrack": item.get("sourceurl"),
            "officialDecision": item.get("decision"), "sources": list(dict.fromkeys(u for u in [url, page] if u)),
        })
    if not papers:
        raise ValueError("No programme entries link to papers")
    return papers


def xml_text(node):
    return clean("".join(node.itertext())) if node is not None else ""


def parse_anthology(raw):
    root = ET.fromstring(raw)
    records = []
    months = {name.lower(): i for i, name in enumerate(calendar.month_name) if name}
    for volume in root.findall("volume"):
        meta = volume.find("meta")
        year, month = meta.findtext("year", ""), meta.findtext("month", "")
        month_number = months.get(month.lower())
        venue_date = f"{year}-{month_number:02d}" if month_number else year
        for paper in volume.findall("paper"):
            if paper.attrib.get("id") == "0":
                continue  # Proceedings front matter is not a research paper.
            identifier = f'{root.attrib["id"]}-{volume.attrib["id"]}.{paper.attrib["id"]}'
            url = f"https://aclanthology.org/{identifier}/"
            records.append({
                "title": xml_text(paper.find("title")), "abstract": xml_text(paper.find("abstract")),
                "url": url, "pdf": f"https://aclanthology.org/{identifier}.pdf",
                "doi": paper.findtext("doi"), "venue": xml_text(meta.find("booktitle")),
                "venueDate": venue_date, "sources": [url],
            })
    if not records and not (root.findall("event") and not root.findall("volume")):
        raise ValueError("ACL collection has no papers")
    return records


def restore_abstract(index):
    if not isinstance(index, dict):
        return ""
    words = [(position, word) for word, positions in index.items() for position in positions]
    return " ".join(word for _, word in sorted(words))


def parse_tmlr(raw, start_year, end_year):
    papers = []
    for block in re.findall(r'<li\b[^>]*class="item\b[^\"]*"[^>]*>(.*?)</li>', raw, re.S):
        title = re.search(r'<h4\b[^>]*>(.*?)</h4>', block, re.S)
        link = re.search(r'href="(https://openreview.net/forum\?id=[^\"]+)"', block)
        published = re.search(r'(January|February|March|April|May|June|July|August|September|October|November|December) (20\d\d)', clean(block))
        if not title or not link or not published:
            continue
        if not start_year <= int(published[2]) <= end_year:
            continue
        month = list(calendar.month_name).index(published[1])
        papers.append({"title": clean(title[1]), "url": html.unescape(link[1]), "abstract": "",
                       "venue": "TMLR", "venueDate": f"{published[2]}-{month:02d}",
                       "officialDecision": "Accepted", "sources": [html.unescape(link[1])],
                       "officialVenueEvidence": "https://jmlr.org/tmlr/papers/"})
    if not papers:
        raise ValueError("No accepted TMLR entries found for the requested years")
    return papers


def openalex_record(item, lane):
    locations = [item.get("primary_location") or {}, *(item.get("locations") or [])]
    sources = list(dict.fromkeys(u for u in [item.get("doi"), item.get("id"),
        *(loc.get("landing_page_url") for loc in locations)] if u and u.startswith("https://")))
    source = (item.get("primary_location") or {}).get("source") or {}
    return {
        "title": item.get("title") or item.get("display_name"), "url": sources[0],
        "openalexId": item["id"], "doi": item.get("doi"),
        "abstract": restore_abstract(item.get("abstract_inverted_index")),
        "date": item.get("publication_date"), "dateSource": "OpenAlex metadata; verify earliest release",
        "venueReported": source.get("display_name"), "sources": sources,
        "pdf": next((loc["pdf_url"] for loc in locations if loc.get("pdf_url")), None),
        "referencedWorks": item.get("referenced_works", []), "hasFulltext": item.get("has_fulltext", False),
        "discoveredVia": [lane], "retrievalEvidence": [lane],
    }


class Discovery:
    def __init__(self, config, fetch, since, until, max_pages, papers, emit):
        self.config, self.fetch, self.since, self.until = config, fetch, since, until
        self.max_pages, self.papers, self.emit = max_pages, papers, emit
        self.records, self.runs = list(config.get("_resumeCandidates", [])), []
        self.terms = re.compile(config["relevancePattern"], re.I)
        self.channel = None
        # OpenAlex serves the first page without a key but rejects cursor paging (401).
        self.keyed = config.get("_openalexKey", True)

    def report(self, source, **values):
        run = {"source": source, "channel": self.channel, **values}
        self.runs.append(run)
        self.emit(run)

    def retain(self, records, source):
        selected = []
        for paper in records:
            matched = [field for field in ("title", "abstract") if self.terms.search(paper.get(field) or "")]
            if matched:
                paper["discoveredVia"] = [source]
                paper["retrievalEvidence"] = ["official-metadata:" + field for field in matched]
                selected.append(paper)
        self.records.extend(selected)
        return len(selected)

    def formal(self):
        start_year = min(self.since.year, self.until.year - 1)
        pmlr = self.config["formalSources"]["pmlr"]
        try:
            volumes = pmlr_volumes(self.fetch(pmlr["index"]), start_year, self.until.year, pmlr["venuePattern"])
            self.report(pmlr["index"], status="complete", volumes=len(volumes), discovery="dynamic-volume-directory")
        except Exception as error:
            volumes = []
            self.report(pmlr["index"], status="failed", error=str(error))
        for volume in volumes:
            source = volume["url"]
            try:
                raw = self.fetch(source)
                links = re.findall(r'href=[\"\']([^\"\']+\.bib)[\"\']', raw)
                if not links:
                    raise ValueError("Official volume lacks a bulk bibliography link")
                bib_url = urllib.parse.urljoin(source, links[0])
                papers = parse_bibliography(self.fetch(bib_url), volume["name"])
                count = self.retain(papers, source)
                self.report(source, status="complete", indexEntries=len(papers), candidates=count,
                            missingAbstracts=sum(not p.get("abstract") for p in papers), searchedFields=["title", "abstract"], metadataUrl=bib_url)
            except Exception as error:
                self.report(source, status="failed", error=str(error))

        for conference in self.config["formalSources"]["programmes"]:
            for year in range(start_year, self.until.year + 1):
                source = f'{conference["origin"]}/virtual/{year}/papers.html'
                try:
                    links = programme_links(self.fetch(source), conference["origin"])
                    paper_url = next((u for u in links if "orals-posters" in u), None)
                    if not paper_url:
                        raise ValueError("No published programme metadata found")
                    data = json.loads(self.fetch(paper_url))
                    items = data.get("results", []) if isinstance(data, dict) else data
                    abstracts = {}
                    supplement_error = None
                    if any(not p.get("abstract") for p in items):
                        abstract_url = next((u for u in links if "abstracts" in u), None)
                        if abstract_url:
                            try:
                                abstracts = json.loads(self.fetch(abstract_url))
                            except Exception as error:
                                supplement_error = str(error)
                    papers = parse_programme(data, abstracts, conference, year)
                    count = self.retain(papers, source)
                    missing = sum(not p.get("abstract") for p in papers)
                    self.report(source, status="complete", indexEntries=len(papers), candidates=count,
                                missingAbstracts=missing, searchedFields=["title", "abstract"],
                                coverage="title-abstract-with-gaps" if missing else "title-and-abstract",
                                abstractSupplementError=supplement_error)
                except Exception as error:
                    self.report(source, status="failed", error=str(error))

        acl = self.config["formalSources"]["acl"]
        try:
            tree = json.loads(self.fetch(acl["tree"]))
            if tree.get("truncated"):
                raise ValueError("ACL metadata tree is truncated")
            paths = []
            for item in tree.get("tree", []):
                match = re.fullmatch(r"data/xml/(\d{4})\.([\w-]+)\.xml", item["path"])
                if match and start_year <= int(match[1]) <= self.until.year and match[2] in acl["collections"]:
                    paths.append(item["path"])
            if not paths:
                raise ValueError("ACL metadata directory returned no requested collections")
            self.report(acl["tree"], status="complete", collections=len(paths), discovery="dynamic-official-xml")
        except Exception as error:
            paths = []
            self.report(acl["tree"], status="failed", error=str(error))
        for path in paths:
            source = acl["rawBase"] + path
            try:
                papers = parse_anthology(self.fetch(source))
                count = self.retain(papers, source)
                self.report(source, status="complete", indexEntries=len(papers), candidates=count,
                            missingAbstracts=sum(not p.get("abstract") for p in papers), searchedFields=["title", "abstract"])
            except Exception as error:
                self.report(source, status="failed", error=str(error))

        source = self.config["formalSources"].get("tmlrAccepted")
        if source:
            try:
                papers = parse_tmlr(self.fetch(source), start_year, self.until.year)
                count = self.retain(papers, source)
                self.report(source, status="complete", indexEntries=len(papers), candidates=count,
                            missingAbstracts=len(papers), searchedFields=["title"], coverage="official-accepted-titles")
            except Exception as error:
                self.report(source, status="failed", error=str(error))

    def alex_pages(self, params, lane, semantic=False):
        fetched, total, page = [], None, 0
        cursor = "*"
        previous = next((r for r in reversed(self.config.get("_resumeRuns", []))
                         if r["source"] == lane and r.get("query") == params), None)
        if previous and previous["status"] == "complete":
            self.report(lane, **{k: v for k, v in previous.items() if k not in ("source", "reused")}, reused=True)
            return []
        previous_count = 0
        if not semantic and previous and previous.get("nextCursor"):
            if not self.keyed:
                self.report(lane, status="truncated", count=previous.get("count", 0), query=params, nextCursor=previous["nextCursor"],
                            error="Cursor paging needs OPENALEX_API_KEY; skipped instead of spending a failing request")
                return []
            cursor, previous_count = previous["nextCursor"], previous.get("count", 0)
        max_pages = 1 if semantic or not self.keyed else self.max_pages
        try:
            for page in range(1, max_pages + 1):
                query = {**params, "per_page": 50 if semantic else 100}
                if not semantic:
                    query["cursor"] = cursor
                url = "https://api.openalex.org/works?" + urllib.parse.urlencode(query)
                data = json.loads(self.fetch(url))
                total = data["meta"]["count"]
                batch = [openalex_record(item, lane) for item in data["results"]]
                fetched.extend(batch)
                cursor = data["meta"].get("next_cursor")
                if semantic or not cursor or not batch or previous_count + len(fetched) >= total:
                    break
            self.records.extend(fetched)
            complete = semantic or previous_count + len(fetched) >= total or not cursor
            extra = {} if complete or self.keyed else {"error": "Only the first page is available without OPENALEX_API_KEY"}
            self.report(lane, status="complete" if complete else "truncated", count=previous_count + len(fetched), total=total,
                        query=params, coverage="ranked-top-50" if semantic else "indexed-results", nextCursor=None if complete else cursor, **extra)
        except Exception as error:
            self.records.extend(fetched)
            self.report(lane, status="failed", count=previous_count + len(fetched), query=params, error=str(error), nextCursor=cursor)
        return fetched

    def fulltext(self):
        date_filter = f"from_publication_date:{self.since},to_publication_date:{self.until}"
        for lane in self.config["openalexQueries"]:
            self.alex_pages({"search": lane["query"], "filter": date_filter}, "openalex:fulltext:" + lane["id"])

    def semantic(self):
        # Semantic search supports years, not from/to_publication_date. Keep all
        # ranked results, including useful older context within those years.
        years = "|".join(str(year) for year in range(self.since.year, self.until.year + 1))
        for lane in self.config["semanticQueries"]:
            self.alex_pages({"search.semantic": lane["query"], "filter": "publication_year:" + years},
                            "openalex:semantic:" + lane["id"], semantic=True)

    def indexed_venues(self):
        """Automatic coverage for journals and proceedings outside bulk sources."""
        years = f"{min(self.since.year, self.until.year - 1)}-{self.until.year}"
        for venue in self.config["formalSources"].get("indexedVenues", []):
            try:
                query = urllib.parse.urlencode({"search": venue["name"], "per_page": 100})
                data = json.loads(self.fetch("https://api.openalex.org/sources?" + query))
                wanted = {s.casefold() for s in [venue["name"], *venue.get("aliases", [])]}
                sources = [s for s in data["results"] if s["display_name"].casefold() in wanted or
                           set(s.get("issn") or []) & set(venue.get("issn", []))]
                if not sources:
                    raise ValueError("No unambiguous journal/conference source match")
                source_ids = "|".join(s["id"].rsplit("/", 1)[-1] for s in sources)
                lane = "openalex:venue:" + venue["name"]
                # Search across indexed full text as well as abstracts for this venue.
                for theme in self.config["venueQueries"]:
                    self.alex_pages({"search": theme, "filter": f"locations.source.id:{source_ids},publication_year:{years}"}, lane)
            except Exception as error:
                self.report("openalex:venue:" + venue["name"], status="failed", error=str(error))

    def citations(self):
        normalize = lambda text: re.sub(r"[^\w]", "", str(text).casefold())
        titles = {normalize(p["title"]) for p in self.papers}
        seeds = {p["openalexId"]: p for p in self.records if p.get("openalexId") and normalize(p.get("title")) in titles}
        for identifier in self.config.get("citationSeeds", []):
            if identifier not in seeds:
                try:
                    item = json.loads(self.fetch("https://api.openalex.org/works/" + identifier.rsplit("/", 1)[-1]))
                    seeds[item["id"]] = openalex_record(item, "openalex:seed")
                except Exception as error:
                    self.report("openalex:seed:" + identifier, status="failed", error=str(error))
        ids = list(seeds)
        for index in range(0, len(ids), 50):
            group = ids[index:index + 50]
            filters = "cites:" + "|".join(s.rsplit("/", 1)[-1] for s in group)
            filters += f",from_publication_date:{self.since},to_publication_date:{self.until}"
            self.alex_pages({"filter": filters}, "openalex:incoming-citations")
        referenced = sorted({r for p in seeds.values() for r in p.get("referencedWorks", [])})
        for index in range(0, len(referenced), 100):
            group = referenced[index:index + 100]
            self.alex_pages({"filter": "openalex_id:" + "|".join(s.rsplit("/", 1)[-1] for s in group)}, "openalex:references")
        self.report("citation-frontier", status="complete", seeds=ids, referencedIds=len(referenced), depth=1,
                    coverage="incoming and outgoing indexed citations; no keyword gate")


def discover(config, fetch, since, until, max_pages, papers, emit, channels):
    discovery = Discovery(config, fetch, since, until, max_pages, papers, emit)
    steps = {"formal": [discovery.formal, discovery.indexed_venues], "fulltext": [discovery.fulltext],
             "semantic": [discovery.semantic], "citations": [discovery.citations]}
    for channel, functions in steps.items():
        if channel in channels:
            discovery.channel = channel
            for function in functions:
                function()
    return discovery.records, discovery.runs
