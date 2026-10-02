"""Scholarly sources: free APIs that need no key.

- OpenAlex  (api.openalex.org)      - almost every paper, with journal, date, type and abstract
- arXiv     (export.arxiv.org)      - physics / astronomy / CS preprints (NOT peer-reviewed)
- PubMed    (eutils.ncbi.nlm.nih.gov) - biomedical papers with abstracts
- Crossref  (api.crossref.org)      - publisher records: journal, date, type

Each hit becomes a Doc whose text starts with a plain sentence saying WHERE and WHEN it was
published and whether it is peer-reviewed or a preprint, followed by the abstract. That line is
what lets the skeptic say "preliminary" and the fact sheet copy the exact title and names.
Approach and endpoints follow the search engines in MCP/budget-mcp/local-deep-research and
MCP/budget-mcp/alex-mcp.
"""
from __future__ import annotations

import asyncio
import html
import re
import xml.etree.ElementTree as ET

import httpx

from swarm.tools import UA, Doc

TIMEOUT = 12


def secret(name: str) -> str:
    """An API key from the environment or from runtime/secrets.json (runtime/ is never committed)."""
    import json
    import os
    from swarm.paths import RUNTIME
    if os.environ.get(name):
        return os.environ[name]
    try:
        return str(json.loads((RUNTIME / "secrets.json").read_text(encoding="utf-8")).get(name, "") or "")
    except Exception:
        return ""
_pubmed_lock = asyncio.Lock()   # NCBI allows ~3 requests/second without a key
_arxiv_lock = asyncio.Lock()    # arXiv wants one request every ~3 s; faster ones get "406 Not Acceptable"
_arxiv_last = [0.0]


_STOP = set("""a an the of in on at to for from by with and or but is are was were be been being do does did
what which who whom whose when where why how that this these those it its as into about than then there
their they them he she his her we our you your i me my can could would should will may might has have had
not no yes if so such also any all some most more many much very just only first""".split())


def plain_query(query: str) -> str:
    """The search words without search-engine syntax: OpenAlex reads ? and * as wildcards (400 Bad
    Request) and ADS/Solr reads : ( ) [ ] { } ^ ~ " ! and a leading - as operators."""
    q = re.sub(r"[?*:()\[\]{}^~\"!\\/]", " ", query or "")
    q = re.sub(r"(?<!\w)-+|-+(?!\w)", " ", q)   # keep hyphens only inside words (Roman-era)
    q = re.sub(r"(?<=\d)-(?=\d)", " ", q)        # but not in number ranges: ADS reads 1290-1200 as syntax
    return re.sub(r"\s+", " ", q).strip()


def key_terms(query: str, n: int = 5) -> list[str]:
    """Up to n content words (no question words or other stopwords), for engines that AND every term."""
    words = re.findall(r"[\w-]+", plain_query(query))
    return [w for w in words if w.lower() not in _STOP and len(w) > 1][:n]


async def _get(c: httpx.AsyncClient, url: str, params: dict) -> httpx.Response:
    """GET with a polite retry when the API says 429 Too Many Requests, and one retry on a
    temporary server error (500/502/503/504)."""
    for attempt in range(3):
        r = await c.get(url, params=params)
        if r.status_code in (500, 502, 503, 504) and attempt == 0:
            await asyncio.sleep(2.0)
            continue
        if r.status_code != 429:
            r.raise_for_status()
            return r
        wait = float(r.headers.get("retry-after", "0") or 0)
        if wait > 30:  # a daily quota is used up: give up now instead of stalling the research step
            break
        await asyncio.sleep(max(wait, 2.0 * (attempt + 1)))
    r.raise_for_status()
    return r


def _clean(t: str) -> str:
    t = re.sub(r"<[^>]+>", " ", html.unescape(t or ""))   # JATS / HTML tags in abstracts
    return re.sub(r"\s+", " ", t).strip()


def _doc(url: str, title: str, authors: list[str], venue: str, date: str, kind: str, abstract: str,
         source: str) -> Doc:
    who = ", ".join(a for a in authors[:4] if a) + (" et al." if len(authors) > 4 else "")
    status = ("a preprint (not yet peer-reviewed)" if kind == "preprint"
              else "a peer-reviewed journal article" if kind == "article"
              else f"a {kind}" if kind else "a publication")
    head = f"Scholarly record: \"{title}\" is {status}"
    if venue:
        head += f" published in {venue}"
    if date:
        head += f" on {date}"
    head += "."
    if who:
        head += f" Authors: {who}."
    text = head + ("\n\n" + abstract if abstract else "\n\n(No abstract available.)")
    return Doc(url, f"{title} ({venue or source})"[:200], text, "paper")


async def openalex(query: str, n: int = 3, since: str = "") -> list[Doc]:
    params = {"search": plain_query(query), "per_page": n, "mailto": "localswarm@example.org"}
    key = secret("OPENALEX_API_KEY")   # optional: without a key OpenAlex allows very few searches a day
    if key:
        params["api_key"] = key
    if since:
        params["filter"] = f"from_publication_date:{since}"
    async with httpx.AsyncClient(timeout=TIMEOUT, headers={"User-Agent": UA}) as c:
        r = await _get(c, "https://api.openalex.org/works", params)
    out = []
    for w in r.json().get("results", []):
        inv = w.get("abstract_inverted_index") or {}
        words = sorted(((p, word) for word, ps in inv.items() for p in ps))
        abstract = " ".join(word for _, word in words)
        loc = w.get("primary_location") or {}
        venue = ((loc.get("source") or {}).get("display_name") or "")
        kind = {"preprint": "preprint", "article": "article"}.get(w.get("type", ""), w.get("type", ""))
        if kind == "article" and "arxiv" in venue.lower():
            kind = "preprint"
        url = w.get("doi") or loc.get("landing_page_url") or w.get("id", "")
        authors = [(a.get("author") or {}).get("display_name", "") for a in w.get("authorships", [])]
        if w.get("title"):
            out.append(_doc(url, _clean(w["title"]), authors, venue, w.get("publication_date", ""), kind,
                            _clean(abstract), "OpenAlex"))
    return out


async def arxiv(query: str, n: int = 3, since: str = "") -> list[Doc]:
    import time
    # arXiv's search ANDs every term, so whole questions ("What did the ... ?") found nothing:
    # search the first 4 content words, and if that finds nothing, the first 3
    words = key_terms(query, 4)
    tries = [words, words[:3]] if len(words) > 3 else [words]
    async with _arxiv_lock, httpx.AsyncClient(timeout=25, headers={"User-Agent": UA},
                                              follow_redirects=True) as c:
        for ws in tries:
            terms = " AND ".join(f"all:{w}" for w in ws) or f"all:{plain_query(query)}"
            for attempt in range(3):
                wait = 3.5 - (time.time() - _arxiv_last[0])
                if wait > 0:
                    await asyncio.sleep(wait)
                _arxiv_last[0] = time.time()
                r = await c.get("https://export.arxiv.org/api/query",
                                params={"search_query": terms, "max_results": n * 3 if since else n,
                                        "sortBy": "relevance"})
                if r.status_code not in (406, 429, 503):
                    break
                await asyncio.sleep(4.0 * (attempt + 1))  # throttled: back off
            r.raise_for_status()
            if "<entry>" in r.text:
                break
    ns = {"a": "http://www.w3.org/2005/Atom"}
    out = []
    for e in ET.fromstring(r.text).findall("a:entry", ns):
        title = _clean(e.findtext("a:title", "", ns))
        if not title:
            continue
        authors = [_clean(a.findtext("a:name", "", ns)) for a in e.findall("a:author", ns)]
        date = (e.findtext("a:published", "", ns) or "")[:10]
        if since and date and date < since:
            continue
        url = e.findtext("a:id", "", ns)
        out.append(_doc(url, title, authors, "arXiv", date, "preprint",
                        _clean(e.findtext("a:summary", "", ns)), "arXiv"))
    return out[:n]


async def pubmed(query: str, n: int = 3, since: str = "") -> list[Doc]:
    base = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
    params = {"db": "pubmed", "term": query, "retmax": n, "retmode": "json", "sort": "relevance"}
    if since:
        params.update({"datetype": "pdat", "mindate": since.replace("-", "/"), "maxdate": "3000"})
    async with _pubmed_lock, httpx.AsyncClient(timeout=TIMEOUT, headers={"User-Agent": UA}) as c:
        r = await _get(c, f"{base}/esearch.fcgi", params)
        ids = r.json().get("esearchresult", {}).get("idlist", [])
        if not ids:
            return []
        await asyncio.sleep(0.4)
        r = await _get(c, f"{base}/efetch.fcgi", {"db": "pubmed", "id": ",".join(ids), "retmode": "xml"})
    out = []
    for art in ET.fromstring(r.text).findall(".//PubmedArticle"):
        pmid = art.findtext(".//PMID", "")
        title = _clean("".join(art.find(".//ArticleTitle").itertext()) if art.find(".//ArticleTitle") is not None else "")
        abstract = _clean(" ".join("".join(t.itertext()) for t in art.findall(".//AbstractText")))
        venue = _clean(art.findtext(".//Journal/Title", ""))
        y, m, d = (art.findtext(f".//PubDate/{k}", "") for k in ("Year", "Month", "Day"))
        date = " ".join(x for x in (d, m, y) if x)
        authors = [_clean(f"{a.findtext('ForeName', '')} {a.findtext('LastName', '')}")
                   for a in art.findall(".//Author")]
        types = [t.text or "" for t in art.findall(".//PublicationType")]
        kind = "preprint" if any("Preprint" in t for t in types) else "article"
        if title:
            out.append(_doc(f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/", title, authors, venue, date, kind,
                            abstract, "PubMed"))
    return out


async def crossref(query: str, n: int = 3, since: str = "") -> list[Doc]:
    params = {"query.bibliographic": query, "rows": n,
              "select": "DOI,title,author,container-title,issued,type,abstract,URL",
              # papers and preprints only (not peer-review reports, book chapters, datasets)
              "filter": "type:journal-article,type:posted-content,type:proceedings-article"}
    if since:
        params["filter"] += f",from-pub-date:{since}"
    async with httpx.AsyncClient(timeout=TIMEOUT, headers={"User-Agent": UA}) as c:
        r = await _get(c, "https://api.crossref.org/works", params)
    out = []
    for it in r.json().get("message", {}).get("items", []):
        title = _clean((it.get("title") or [""])[0])
        if not title:
            continue
        parts = ((it.get("issued") or {}).get("date-parts") or [[]])[0]
        date = "-".join(str(p).zfill(2) for p in parts)
        t = it.get("type", "")
        kind = "preprint" if t == "posted-content" else "article" if t == "journal-article" else t.replace("-", " ")
        authors = [f"{a.get('given', '')} {a.get('family', '')}".strip() for a in it.get("author", [])]
        venue = (it.get("container-title") or [""])[0]
        out.append(_doc(it.get("URL") or f"https://doi.org/{it.get('DOI', '')}", title, authors, venue, date,
                        kind, _clean(it.get("abstract", "")), "Crossref"))
    return out


async def ads(query: str, n: int = 3, since: str = "") -> list[Doc]:
    """NASA ADS (astronomy and physics). Needs a free token: ADS_API_TOKEN in runtime/secrets.json."""
    token = secret("ADS_API_TOKEN")
    if not token:
        return []
    q = plain_query(query) + (f" pubdate:[{since[:7]} TO *]" if since else "")
    async with httpx.AsyncClient(timeout=TIMEOUT, headers={"User-Agent": UA, "Authorization": f"Bearer {token}"}) as c:
        r = await _get(c, "https://api.adsabs.harvard.edu/v1/search/query",
                       {"q": q, "rows": n, "sort": "score desc",
                        "fl": "title,author,pub,pubdate,doctype,property,bibcode,doi,abstract"})
    out = []
    for d in r.json().get("response", {}).get("docs", []):
        title = _clean((d.get("title") or [""])[0])
        if not title:
            continue
        props = set(d.get("property") or [])
        kind = ("article" if "REFEREED" in props
                else "preprint" if d.get("doctype") == "eprint" or "EPRINT_OPENACCESS" in props
                else (d.get("doctype") or "").replace("inproceedings", "conference paper"))
        doi = (d.get("doi") or [""])[0]
        url = f"https://doi.org/{doi}" if doi else f"https://ui.adsabs.harvard.edu/abs/{d.get('bibcode', '')}"
        date = (d.get("pubdate") or "").replace("-00", "")
        out.append(_doc(url, title, d.get("author") or [], d.get("pub", ""), date, kind,
                        _clean(d.get("abstract", "")), "NASA ADS"))
    return out


SOURCES = {"openalex": openalex, "arxiv": arxiv, "pubmed": pubmed, "crossref": crossref, "ads": ads}


async def search_all(query: str, n: int = 2, sources: list[str] | None = None,
                     since: str = "") -> dict[str, list[Doc] | Exception]:
    """Run every scholarly source for one query; each result is a list of Docs or the error.
    since='YYYY-MM-DD' keeps only work published on or after that date (for questions about
    recent discoveries, where a 2004 paper with a similar title is only a distraction)."""
    names = [s for s in (sources or list(SOURCES)) if s in SOURCES]
    res = await asyncio.gather(*(SOURCES[s](query, n, since) for s in names), return_exceptions=True)
    return dict(zip(names, res))


def recent_since(text: str, today=None) -> str:
    """'YYYY-01-01' two years back when the question is about something new, else ''."""
    import datetime as _dt
    today = today or _dt.date.today()
    years = [int(y) for y in re.findall(r"\b(20\d\d)\b", text)]
    if any(y >= today.year - 1 for y in years) or re.search(r"\b(new|newly|newest|latest|recent|recently|just|this year)\b",
                                                           text, re.I):
        return f"{today.year - 2}-01-01"
    return ""
