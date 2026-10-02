"""Turn fetched documents into short, ranked, citable passages."""
from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import asdict, dataclass

from swarm.tools import Doc

STOP = set("""a an the and or but if of to in on at by for with from as is are was were be been being
it its this that these those there here what which who whom whose when where why how do does did
not no yes can could should would will shall may might must than then so such into over under about
between after before during also more most other some any each all both few many much very just
i you he she we they them his her our your their my me us""".split())

_TOKEN = re.compile(r"[a-z0-9]+(?:'[a-z]+)?")


def tokens(text: str) -> list[str]:
    return [t for t in _TOKEN.findall(text.lower()) if t not in STOP and len(t) > 1]


# Question words and the words sources usually use instead. Small on purpose;
# an embedding/reranker model is the long-term fix.
EXPAND = {
    "height": ["tall", "metres", "meters", "feet", "ft"],
    "tall": ["height", "metres", "meters", "feet"],
    "built": ["constructed", "construction", "completed", "opened", "erected"],
    "constructed": ["built", "construction", "completed", "opened"],
    "construction": ["built", "constructed", "completed"],
    "born": ["birth"], "died": ["death"], "death": ["died"],
    "founded": ["established", "founder", "founding"],
    "population": ["inhabitants", "residents", "census"],
    "cost": ["price", "costs", "usd", "dollars"], "price": ["cost", "costs"],
    "located": ["location", "situated"], "where": ["location", "located"],
    "invented": ["inventor", "invention"], "wrote": ["author", "written"],
    "size": ["area", "length", "width"], "weight": ["weighs", "mass", "tonnes", "tons"],
}


def query_tokens(text: str) -> list[str]:
    toks = tokens(text)
    extra = [e for t in toks for e in EXPAND.get(t, [])]
    return toks + extra


@dataclass
class Passage:
    id: str
    url: str
    title: str
    text: str
    source: str
    score: float = 0.0
    pos: int = 0          # chunk position in its document (0 = opening passage)

    def to_dict(self) -> dict:
        return asdict(self)


BOILER = re.compile(
    r"subscri|sign in|log in|cookie|newsletter|privacy policy|terms of (use|service)|all rights reserved|"
    r"share (this|on)|follow us|advertis|email protected|skip to (main )?content|site navigation|"
    r"explore by|related (articles|stories)|read more|click here|javascript", re.I)


# "related stories" rails: "3 min read  Some Headline  article 2 days ago" repeated along a line
TEASER = re.compile(r"\d+\s*min(ute)?s?\s*read|\barticle\s*\d+\s*(minutes?|hours?|days?|weeks?|months?|years?)\s+ago",
                    re.I)


def clean(text: str) -> str:
    text = re.sub(r"!\[[^\]]*\]\([^)]*\)", "", text)                 # images
    text = re.sub(r"\[\s*\]\((?:[^)(]|\([^)]*\))*\)", "", text)          # icon links with no text
    text = re.sub(r"\[([^\]]+)\]\((?:[^)(]|\([^)]*\))*\)", r"\1", text)  # links -> text
    text = re.sub(r"\[\d+\]", "", text)                               # [12] footnote marks
    text = re.sub(r"(?m)^\s*[*#>|=_-]{0,4}\s*$", "", text)             # rules / empty md
    lines = []
    for line in text.splitlines():
        s = line.strip()
        # menus and page furniture: short bullets, short headings, subscription/cookie/share boilerplate
        if re.match(r"^[*+\-]\s+\S", s) and len(s) < 70:
            continue
        if re.match(r"^#{1,6}\s", s) and len(s) < 60:
            continue
        if BOILER.search(s) and len(s) < 200:
            continue
        teasers = len(TEASER.findall(s))
        if teasers >= 2 or (teasers == 1 and len(s) < 160):
            continue
        s = re.sub(r"^#{1,6}\s*", "", s)
        # drop navigation crumbs: very short lines without sentence punctuation
        if len(s) < 40 and not re.search(r"[.!?:]\s*$", s) and not s.startswith("#"):
            if len(s.split()) <= 4:
                continue
        lines.append(s)
    text = "\n".join(lines)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def chunk(text: str, size: int = 900, overlap: int = 120) -> list[str]:
    """Split on paragraph boundaries into ~size-char chunks."""
    paras = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    out, cur = [], ""
    for p in paras:
        while len(p) > size * 1.5:                  # very long paragraph: hard split on sentences
            cut = p.rfind(". ", 0, size)
            cut = cut + 1 if cut > size // 3 else size
            piece, p = p[:cut].strip(), p[cut:].strip()
            if cur:
                out.append(cur)
                cur = ""
            out.append(piece)
        if len(cur) + len(p) + 1 <= size:
            cur = f"{cur}\n{p}" if cur else p
        else:
            if cur:
                out.append(cur)
            tail = cur[-overlap:] if cur and overlap else ""
            cur = (tail + " " + p).strip() if tail and len(tail) + len(p) <= size else p
    if cur:
        out.append(cur)
    return [c for c in out if len(c) > 80]


class BM25:
    def __init__(self, docs: list[list[str]], k1: float = 1.4, b: float = 0.75):
        self.docs = docs
        self.k1, self.b = k1, b
        self.avg = sum(len(d) for d in docs) / max(1, len(docs))
        df = Counter()
        for d in docs:
            df.update(set(d))
        n = len(docs)
        self.idf = {t: math.log(1 + (n - c + 0.5) / (c + 0.5)) for t, c in df.items()}
        self.tf = [Counter(d) for d in docs]

    def score(self, query: list[str], i: int) -> float:
        tf, dl = self.tf[i], len(self.docs[i])
        s = 0.0
        for t in set(query):
            if t not in tf:
                continue
            f = tf[t]
            s += self.idf.get(t, 0) * f * (self.k1 + 1) / (f + self.k1 * (1 - self.b + self.b * dl / self.avg))
        return s


def build_passages(docs: list[Doc], size: int = 900) -> list[Passage]:
    out: list[Passage] = []
    for d in docs:
        if d.error or not d.text:
            continue
        for i, c in enumerate(chunk(clean(d.text), size=size)):
            out.append(Passage(id="", url=d.url, title=d.title, text=c, source=d.source, pos=i))
    return out


def select(passages: list[Passage], queries: list[str], k: int, per_source: int | None = None) -> list[Passage]:
    """Top-k passages for a set of queries.

    Opening passages get a boost (article leads summarise the key facts). At most
    `per_source` passages come from one URL, unless there are only a few sources.
    """
    if not passages:
        return []
    n_urls = len({p.url for p in passages})
    if per_source is None:
        per_source = k if n_urls <= 3 else max(2, k // 2)
    bm = BM25([tokens(p.title + " " + p.text) for p in passages])
    qtoks = [query_tokens(q) for q in queries if q.strip()]
    scored = []
    for i, p in enumerate(passages):
        s = max((bm.score(q, i) for q in qtoks), default=0.0)
        if s > 0 and p.pos < 4:          # the first few passages usually hold the summary
            s *= 1.5
        scored.append((s, i))
    relevance = {i: sc for sc, i in scored}
    scored.sort(reverse=True)
    picked, per = [], Counter()
    for s, i in scored:
        if s <= 0:
            break
        p = passages[i]
        if per[p.url] >= per_source:
            continue
        per[p.url] += 1
        picked.append(Passage(**{**p.to_dict(), "score": round(s, 3)}))
        if len(picked) >= k:
            break
    # an article's lead usually runs over two chunks (the name of the thing is often in the second):
    # when a lead passage is picked, bring its continuation along
    have = {(p.url, p.pos) for p in picked}
    extra = []
    for p in picked:
        if p.pos == 0 and (p.url, 1) not in have:
            j = next((j for j, x in enumerate(passages) if x.url == p.url and x.pos == 1), None)
            nxt = passages[j] if j is not None and relevance.get(j, 0) > 0 else None  # only if on topic
            if nxt:
                extra.append(Passage(**{**nxt.to_dict(), "score": round(p.score * 0.9, 3)}))
                have.add((p.url, 1))
    return picked + extra[:2]


def assign_ids(groups: list[list[Passage]]) -> list[Passage]:
    """Give every distinct passage a stable id E1, E2, ... across all sub-questions."""
    seen: dict[tuple[str, str], str] = {}
    ordered: list[Passage] = []
    for g in groups:
        for p in g:
            key = (p.url, p.text[:120])
            if key not in seen:
                seen[key] = f"E{len(seen) + 1}"
                p.id = seen[key]
                ordered.append(p)
            else:
                p.id = seen[key]
    return ordered
