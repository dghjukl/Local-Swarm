"""Notebook mode: the workers share a working memory instead of only meeting at the end.

How a question is answered (mode: notebook):

  1. Independent reading. Each worker reads its share of the evidence a few passages at a time
     and keeps running notes (one fact per note, with the passage ids that state it) plus a list
     of what is still missing. Every passage is read by `reads_per_passage` workers, so a fact
     can be found independently by more than one of them. Workers do NOT see each other's notes
     yet (their first take stays independent: the guard against groupthink).
  2. Shared notebook. All notes are merged; a fact found by two workers becomes one note with
     two independent readers. The verifier checks every note against the passages it cites.
  3. Collaboration round(s). Each worker sees the notebook and the open questions, and may
     agree with notes, dispute them (with a reason) or add notes that answer open questions from
     the passages it read. New notes are verified too.
  4. The answer is written from the notebook (verified notes first, disputes shown) plus the
     passages those notes cite, never from the full history. Who writes it:
       leader: coordinator   the coordinator model (a big one, or a tiny one: same code)
       leader: none          the worker whose notes held up best writes it; every other worker
                             reviews the draft once, and the writer revises if anyone objects.

The notebook, every note's readers / supporters / disputes and the drafts are kept in the trace.
"""
from __future__ import annotations

import asyncio
import re
import time
from dataclasses import asdict, dataclass, field

from swarm import evidence as ev
from swarm import llm

NOTES_SYSTEM = """You are one member of a research team. You read sources a few at a time and keep
running notes for the team's notebook.
Rules:
- A note is ONE specific fact that helps answer the question (a name, number, date, place, result),
  written as a short self-contained sentence, with the ids of the passages that state it, like ["E3"].
- Only write facts the passages actually state. Never add your own knowledge.
- Keep your earlier notes (correct them if a new passage shows they were wrong) and add new ones.
- open_questions: what is still missing to answer the question (short).
Output the JSON only."""

NOTES_SCHEMA = {
    "type": "object",
    "properties": {
        "notes": {"type": "array", "maxItems": 12, "items": {
            "type": "object",
            "properties": {"fact": {"type": "string", "maxLength": 300},
                           "sources": {"type": "array", "items": {"type": "string"}, "maxItems": 4}},
            "required": ["fact", "sources"]}},
        "open_questions": {"type": "array", "maxItems": 4, "items": {"type": "string", "maxLength": 160}},
    },
    "required": ["notes", "open_questions"],
}

REVIEW_NOTES_SYSTEM = """You are one member of a research team. Below is the team notebook: notes other
members wrote, each with the passages it cites and how many members found it independently.
Using ONLY the passages you were given, do three things:
- agree: ids of notes your passages also support
- dispute: notes your passages contradict, with a short reason (only if a passage really disagrees)
- new_notes: facts from your passages that answer an open question or are missing from the notebook,
  each with its passage ids
Do not dispute a note just because your passages don't mention it. Output the JSON only."""

REVIEW_NOTES_SCHEMA = {
    "type": "object",
    "properties": {
        "agree": {"type": "array", "maxItems": 20, "items": {"type": "string"}},
        "dispute": {"type": "array", "maxItems": 4, "items": {
            "type": "object", "properties": {"id": {"type": "string"}, "reason": {"type": "string", "maxLength": 200}},
            "required": ["id", "reason"]}},
        "new_notes": NOTES_SCHEMA["properties"]["notes"] | {"maxItems": 6},
    },
    "required": ["agree", "dispute", "new_notes"],
}

WRITE_SYSTEM = """You write the final answer for a research team, using the team's notebook.
Today is {today}.
- Answer the user's question directly in the first sentence, then add the key supporting details.
- Use ONLY facts from the notebook and the passages. Prefer notes marked VERIFIED and notes found by
  more members. Do not rely on notes marked DISPUTED or UNSUPPORTED unless a passage clearly supports them.
- If the notebook does not answer part of the question, say so plainly; never guess.
- If the question rests on something the notes contradict, say that.
- Cite passage ids after each fact, like [E3]. Only E-numbers are citations; never write anything
  else in brackets and never mention how notes were checked. Keep it under 200 words."""


TAG_RE = re.compile(r"\s*\[(?:VERIFIED|PARTLY SUPPORTED|UNCHECKED|UNSUPPORTED|DISPUTED|verified|partly supported|"
                    r"unchecked|disputed)[^\]]*\]")
BRACKET_RE = re.compile(r"\[([^\[\]]{1,80})\]")


def clean_citations(text: str) -> str:
    """Drop note ids and status tags a writer copied from the notebook; keep E-citations."""
    text = TAG_RE.sub("", text)

    def fix(m: re.Match) -> str:
        parts = [p.strip() for p in re.split(r"[,;]", m.group(1))]
        if not any(re.fullmatch(r"N\d+", p) for p in parts):
            return m.group(0)
        keep = [p for p in parts if re.fullmatch(r"E\d+", p)]
        return f"[{', '.join(keep)}]" if keep else ""
    text = BRACKET_RE.sub(fix, text)
    text = re.sub(r"\bN\d+(?=\s*(?:and|,)?\s*(?:\[|E\d|confirm|show|state|indicate))", "", text)
    text = re.sub(r"[ \t]+([.,;:])", r"\1", re.sub(r"[ \t]{2,}", " ", text))
    return re.sub(r"(?:,\s*)+(?=[.;:]|\s*$)", "", text, flags=re.M).strip()

DRAFT_REVIEW_SYSTEM = """You review a teammate's draft answer against the team notebook and the passages.
Object only to real problems: a claim the notes or passages do not support, a contradiction with a
verified note, an important verified fact that is missing, or a direct answer that is missing.
If the draft is fine, set ok to true and leave problems empty. Output the JSON only."""

DRAFT_REVIEW_SCHEMA = {
    "type": "object",
    "properties": {"ok": {"type": "boolean"},
                   "problems": {"type": "array", "maxItems": 3, "items": {"type": "string", "maxLength": 220}}},
    "required": ["ok", "problems"],
}

STATUS_LABEL = {"supported": "VERIFIED", "partial": "PARTLY SUPPORTED", "unsupported": "UNSUPPORTED",
                "unchecked": "UNCHECKED", "disputed": "DISPUTED"}


@dataclass
class Note:
    id: str
    fact: str
    sources: list[str]
    readers: list[str] = field(default_factory=list)      # found it independently (phase 1)
    agree: list[str] = field(default_factory=list)        # endorsed it in a collaboration round
    disputes: list[dict] = field(default_factory=list)    # {"by", "reason"}
    status: str = "unchecked"                             # supported / partial / unsupported / unchecked
    reason: str = ""
    added_in: str = "reading"                             # reading / round 1 / ...

    def support(self) -> int:
        return len(set(self.readers) | set(self.agree))


def _words(s: str) -> set[str]:
    return {w for w in re.findall(r"[a-z0-9]+", s.lower()) if len(w) > 2}


def _numbers(s: str) -> set[str]:
    return set(re.findall(r"\d+(?:[.,]\d+)?", s))


def same_fact(a: str, b: str) -> bool:
    """Two notes state the same fact. v1 needed word-Jaccard >= 0.6, which almost never matched
    two members' different wordings (found_by_2plus stayed near 0). Now: no conflicting numbers, and
    either Jaccard >= 0.45 or one note's words are mostly (>= 70%) inside the other's."""
    na, nb = _numbers(a), _numbers(b)
    if na and nb and not (na <= nb or nb <= na):
        return False  # "695 billion tonnes" vs "120 billion tonnes": different facts, never merged
    wa, wb = _words(a), _words(b)
    if not wa or not wb:
        return False
    inter = len(wa & wb)
    return inter / len(wa | wb) >= 0.45 or inter / min(len(wa), len(wb)) >= 0.7


QUESTION_START = re.compile(r"^(what|how|why|when|where|who|whom|which|whose|is|are|was|were|has|have|had|"
                            r"does|do|did|can|could|will|would|should)\b", re.I)
FILLER = re.compile(r"\b(additional details|new passages?|no (new )?(relevant )?information|not mentioned|"
                    r"the passages? (do|does) not|n/?a)\b", re.I)


def clean_fact(fact: str) -> str | None:
    """A usable note, or None. v1 let through headings, questions written as notes and filler
    ('Additional details from new passages'), mostly from EXAONE-1.2B (claim support 65%)."""
    f = re.sub(r"^[#*\-\s\d.)]+", "", " ".join(str(fact or "").split())).replace("**", "").strip()
    if len(f) < 25 or len(f.split()) < 5:
        return None
    if f.endswith("?") or (QUESTION_START.match(f) and not f.endswith(".")):
        return None  # a question, not a fact
    if FILLER.search(f):
        return None
    return f


def clean_question(q: str) -> str | None:
    """An open question must be a question (v1 got facts posted as open questions)."""
    q = re.sub(r"^[#*\-\s\d.)]+", "", " ".join(str(q or "").split())).replace("**", "").strip()
    if len(q) < 10 or not (q.endswith("?") or QUESTION_START.match(q)):
        return None
    return q if q.endswith("?") else q + "?"


class Notebook:
    def __init__(self, valid_ids: set[str]):
        self.notes: list[Note] = []
        self.open_questions: list[dict] = []   # {"q", "by"}
        self.valid = valid_ids
        self.rejected = 0                      # notes dropped by the quality filter / missing sources

    def add(self, fact: str, sources, author: str, added_in: str = "reading",
            as_reader: bool = True) -> Note | None:
        fact = clean_fact(fact)
        srcs = [s for s in dict.fromkeys(re.findall(r"E\d+", " ".join(map(str, sources or [])))) if s in self.valid]
        if not fact or not srcs:  # junk, or a note without a real source (cannot be checked): dropped
            self.rejected += 1
            return None
        for n in self.notes:  # the same fact found by someone else: one note, more readers
            if same_fact(fact, n.fact):
                n.sources = list(dict.fromkeys(n.sources + srcs))
                who = n.readers if as_reader else n.agree
                if author not in who:
                    who.append(author)
                return n
        n = Note(id=f"N{len(self.notes) + 1}", fact=fact, sources=srcs,
                 readers=[author] if as_reader else [], agree=[] if as_reader else [author], added_in=added_in)
        self.notes.append(n)
        return n

    def add_question(self, q: str, by: str) -> None:
        q = clean_question(q)
        if not q:
            return
        w = _words(q)
        for o in self.open_questions:
            ow = _words(o["q"])
            if w and ow and len(w & ow) / len(w | ow) >= 0.5:
                return
        self.open_questions.append({"q": q, "by": by})

    def ordered(self) -> list[Note]:
        rank = {"supported": 0, "partial": 1, "unchecked": 2, "unsupported": 3}
        return sorted(self.notes, key=lambda n: (rank.get(n.status, 2) + (2 if n.disputes else 0), -n.support()))

    def render(self, limit: int = 30, with_open: bool = True) -> str:
        lines = []
        for n in self.ordered()[:limit]:
            tag = "DISPUTED" if n.disputes else STATUS_LABEL.get(n.status, n.status.upper())
            line = f"{n.id} [{tag}; found by {n.support()}] {n.fact} ({', '.join(n.sources)})"
            for d in n.disputes[:2]:
                line += f"\n    - disputed: {d['reason']}"
            lines.append(line)
        if with_open and self.open_questions:
            lines.append("Open questions:")
            lines += [f"- {o['q']}" for o in self.open_questions[:6]]
        return "\n".join(lines) or "(the notebook is empty)"

    def render_for_writer(self, limit: int = 30) -> str:
        """The notebook as the writer sees it: no note ids (v1 writers cited "N14" and copied
        "[VERIFIED; found by 2]" into answers), only facts, their passage ids and how solid they are."""
        lines = []
        for n in self.ordered()[:limit]:
            how = "disputed" if n.disputes else {"supported": "verified", "partial": "partly supported",
                                                  "unsupported": "NOT supported by its passages"}.get(n.status, "unchecked")
            line = f"- {n.fact} [{', '.join(n.sources)}] ({how}; found by {n.support()} member{'s' if n.support() != 1 else ''})"
            for d in n.disputes[:2]:
                line += f"\n    objection: {d['reason']}"
            lines.append(line)
        return "\n".join(lines) or "(the notebook is empty)"

    def to_list(self) -> list[dict]:
        return [asdict(n) for n in self.notes]


def assign_passages(passages: list[ev.Passage], workers: list[str], reads: int) -> dict[str, list[ev.Passage]]:
    """Every passage goes to `reads` different workers, spread evenly."""
    reads = max(1, min(reads, len(workers)))
    out: dict[str, list[ev.Passage]] = {w: [] for w in workers}
    for i, p in enumerate(passages):
        for k in range(reads):
            out[workers[(i + k) % len(workers)]].append(p)
    return out


async def run_notebook(sw, question: str, subqs: list[str], groups: list[list[ev.Passage]],
                       evidence: list[ev.Passage], send, stage, trace: dict, t_start: float,
                       stage_times: dict, today: str) -> dict:
    from swarm.orchestrator import VERIFY_SCHEMA, VERIFY_SYSTEM, _fmt_passages, _save
    nb_cfg = sw.cfg.get("notebook") or {}
    leader = str(nb_cfg.get("leader", "coordinator"))
    chunk = int(nb_cfg.get("chunk_passages", 4))
    reads = int(nb_cfg.get("reads_per_passage", 2))
    rounds = int(nb_cfg.get("rounds", 1))
    w = sw.role("workers")
    wctx = int(nb_cfg.get("ctx_per_slot", max(8192, w["ctx_per_slot"])))
    coord, ver = sw.role("coordinator"), sw.role("verifier")
    slots = sw.team_slots()                      # (label, model)
    labels = [lab for lab, _ in slots]
    model_of = dict(slots)
    copies = {m: sum(1 for _, x in slots if x == m) for _, m in slots}  # copies of one model share a server
    by_id = {p.id: p for p in evidence}
    book = Notebook(set(by_id))
    trace["team"] = labels
    trace["notebook_config"] = {"leader": leader, "chunk_passages": chunk, "reads_per_passage": reads,
                                "rounds": rounds}
    await send({"type": "team", "coordinator": coord["model"] if leader != "none" else None,
                "verifier": ver["model"], "workers": [{"model": lab, "lab": sw.cards[m].lab,
                                                         "lineage": sw.cards[m].lineage} for lab, m in slots]})
    parts = "\n".join(f"- {sq}" for sq in subqs)
    shares = assign_passages(evidence, labels, reads)
    worker_recs: dict[str, dict] = {lab: {"model": lab, "base_model": m, "lab": sw.cards[m].lab, "subq": 0,
                                          "notes_written": 0, "seconds": 0.0} for lab, m in slots}

    # ---------------- 1. independent reading, running notes
    await stage("work", f"{len(labels)} models reading and taking notes")
    personal: dict[str, list[dict]] = {}

    async def read(label: str) -> None:
        m = model_of[label]
        rec = worker_recs[label]
        t0 = time.time()
        notes: list[dict] = []
        opens: list[str] = []
        mine = shares[label]
        try:
            async with sw.pool.use(m, wctx, copies[m]) as url:
                for i in range(0, len(mine), chunk):
                    part = mine[i:i + chunk]
                    have = "\n".join(f"- {n['fact']} ({', '.join(n['sources'])})" for n in notes) or "(none yet)"
                    user = (f"Question: {question}\nParts to cover:\n{parts}\n\nYour notes so far:\n{have}\n\n"
                            f"New passages:\n{_fmt_passages(part, limit=900)}")
                    try:
                        res = await llm.chat_json(url, [{"role": "system", "content": NOTES_SYSTEM},
                                                        {"role": "user", "content": user}],
                                                  NOTES_SCHEMA, max_tokens=900, temperature=0.2)
                    except llm.BudgetExhausted:
                        break
                    except Exception as e:  # one bad chunk: keep the notes so far, go on
                        rec.setdefault("chunk_errors", []).append(f"{type(e).__name__}: {e}"[:160])
                        continue
                    data = res.data if isinstance(res.data, dict) else {}
                    new = [n for n in data.get("notes", []) if isinstance(n, dict) and n.get("fact")]
                    if new:
                        notes = new
                    opens = [str(q) for q in data.get("open_questions", []) if q][:4]
        except Exception as e:
            rec["error"] = f"{type(e).__name__}: {e}"[:400]
        rec["seconds"] = round(time.time() - t0, 1)
        personal[label] = notes
        for q in opens:
            book.add_question(q, label)
        await send({"type": "notes", "model": label, "count": len(notes)})

    await asyncio.gather(*(read(lab) for lab in labels))
    for lab in labels:  # merge in team order (deterministic note ids)
        for n in personal.get(lab, []):
            if book.add(n.get("fact", ""), n.get("sources", []), lab):
                worker_recs[lab]["notes_written"] += 1

    # ---------------- 2. verify every note against the passages it cites
    await stage("verify", "Fact-checking the notebook")

    verify_stats = {"retried_ok": 0, "failed": 0}

    async def verify(notes: list[Note]) -> None:
        if not notes:
            return
        async with sw.pool.use(ver["model"], ver["ctx_per_slot"], ver["parallel"]) as url:
            for i in range(0, len(notes), 4):  # a few notes at a time: passages stay small
                batch = notes[i:i + 4]
                cited = sorted({s for n in batch for s in n.sources}, key=lambda x: int(x[1:]))
                claims = "\n".join(f"{k + 1}. {n.fact}  (cites {', '.join(n.sources)})" for k, n in enumerate(batch))
                user = f"Passages:\n{_fmt_passages([by_id[c] for c in cited], limit=900)}\n\nClaims to check:\n{claims}"
                got = await check(url, user)
                if got is None:
                    return
                missing = [n for k, n in enumerate(batch) if not apply(n, got.get(k + 1))]
                # v1 left a whole batch unchecked when one call failed: retry the missing notes one by one
                for n in missing:
                    one = (f"Passages:\n{_fmt_passages([by_id[c] for c in n.sources], limit=900)}\n\n"
                           f"Claims to check:\n1. {n.fact}  (cites {', '.join(n.sources)})")
                    got1 = await check(url, one)
                    if got1 is None:
                        return
                    if not apply(n, got1.get(1)):
                        verify_stats["failed"] += 1
                    else:
                        verify_stats["retried_ok"] += 1

    async def check(url: str, user: str) -> dict | None:
        """{claim number: verdict} (empty after two failed tries); None = out of budget."""
        for _ in range(2):
            try:
                res = await llm.chat_json(url, [{"role": "system", "content": VERIFY_SYSTEM},
                                                {"role": "user", "content": user}], VERIFY_SCHEMA, max_tokens=600)
            except llm.BudgetExhausted:
                return None
            except Exception:
                continue
            got = {}
            for x in (res.data or {}).get("verdicts", []) if isinstance(res.data, dict) else []:
                if isinstance(x, dict):
                    try:
                        got[int(x.get("n", -1))] = x
                    except (TypeError, ValueError):
                        pass
            if got:
                return got
        return {}

    def apply(n: Note, x: dict | None) -> bool:
        if x and x.get("verdict") in ("supported", "partial", "unsupported"):
            n.status, n.reason = x["verdict"], str(x.get("reason", ""))[:200]
            return True
        return False

    await verify(list(book.notes))

    # ---------------- 3. collaboration: read the notebook, agree / dispute / fill gaps
    for rnd in range(1, rounds + 1):
        await stage(f"round{rnd}", f"Team reviews the notebook (round {rnd})")
        before = len(book.notes)

        async def review(label: str) -> None:
            if worker_recs[label].get("error"):
                return
            m = model_of[label]
            mine = shares[label][:6]
            user = (f"Question: {question}\n\n=== Team notebook ===\n{book.render(limit=25)}\n\n"
                    f"=== Your passages ===\n{_fmt_passages(mine, limit=600)}")
            try:
                async with sw.pool.use(m, wctx, copies[m]) as url:
                    res = await llm.chat_json(url, [{"role": "system", "content": REVIEW_NOTES_SYSTEM},
                                                    {"role": "user", "content": user}],
                                              REVIEW_NOTES_SCHEMA, max_tokens=700, temperature=0.2)
            except Exception as e:
                worker_recs[label].setdefault("round_errors", []).append(f"{type(e).__name__}: {e}"[:160])
                return
            data = res.data if isinstance(res.data, dict) else {}
            ids = {n.id: n for n in book.notes}
            for nid in data.get("agree", []):
                n = ids.get(str(nid).strip())
                if n and label not in n.readers and label not in n.agree:
                    n.agree.append(label)
            for d in data.get("dispute", []):
                n = ids.get(str((d or {}).get("id", "")).strip()) if isinstance(d, dict) else None
                if n and label not in n.readers:
                    n.disputes.append({"by": label, "reason": str(d.get("reason", ""))[:200]})
            for nn in data.get("new_notes", []):
                if isinstance(nn, dict) and book.add(nn.get("fact", ""), nn.get("sources", []), label,
                                                     added_in=f"round {rnd}", as_reader=False):
                    worker_recs[label]["notes_written"] += 1

        await asyncio.gather(*(review(lab) for lab in labels))
        await verify([n for n in book.notes[before:]])

    # ---------------- 4. write the answer from the notebook
    await stage("synthesize", "Writing the answer from the notebook")
    good = [n for n in book.ordered() if n.status in ("supported", "partial", "unchecked")]
    cite_ids = sorted({s for n in good[:20] for s in n.sources}, key=lambda x: int(x[1:]))[:10]
    write_user = (f"User question: {question}\nParts to cover:\n{parts}\n\n=== Team notebook ===\n"
                  f"{book.render_for_writer(limit=30)}\n\n=== Passages the notes cite ===\n"
                  f"{_fmt_passages([by_id[i] for i in cite_ids], limit=700)}")
    msgs = [{"role": "system", "content": WRITE_SYSTEM.format(today=today)}, {"role": "user", "content": write_user}]

    async def delta(txt: str) -> None:
        await send({"type": "answer_delta", "text": txt})

    drafts: list[dict] = []
    if leader == "none":
        # the member whose notes held up best writes; everyone else reviews the draft once
        def score(lab: str) -> tuple:
            mine = [n for n in book.notes if lab in n.readers or lab in n.agree]
            return (sum(1 for n in mine if n.status == "supported"), -labels.index(lab))
        alive = [lab for lab in labels if not worker_recs[lab].get("error")] or labels
        writer = max(alive, key=score)
        trace["writer"] = writer
        async with sw.pool.use(model_of[writer], wctx, copies[model_of[writer]]) as url:
            draft = await llm.chat(url, msgs, max_tokens=700, temperature=0.2, final=True)
        drafts.append({"by": writer, "text": draft.text})
        objections: list[str] = []

        async def critique(label: str) -> None:
            try:
                async with sw.pool.use(model_of[label], wctx, copies[model_of[label]]) as url:
                    res = await llm.chat_json(url, [{"role": "system", "content": DRAFT_REVIEW_SYSTEM},
                                                    {"role": "user", "content": f"{write_user}\n\n=== Draft ===\n{draft.text}"}],
                                              DRAFT_REVIEW_SCHEMA, max_tokens=400, temperature=0.2)
            except Exception:
                return
            data = res.data if isinstance(res.data, dict) else {}
            if not data.get("ok", True):
                objections.extend(f"{label}: {p}" for p in data.get("problems", [])[:3] if p)

        await asyncio.gather(*(critique(lab) for lab in alive if lab != writer))
        trace["objections"] = objections
        if objections:
            fix = msgs + [{"role": "assistant", "content": draft.text},
                          {"role": "user", "content": "Your teammates raised these problems:\n"
                           + "\n".join(f"- {o}" for o in objections)
                           + "\nRewrite the answer, fixing the real problems (ignore objections the notebook "
                             "does not support). Same rules as before."}]
            async with sw.pool.use(model_of[writer], wctx, copies[model_of[writer]]) as url:
                final = await llm.chat(url, fix, max_tokens=700, temperature=0.2, on_delta=delta, final=True)
            drafts.append({"by": writer, "text": final.text, "revision": True})
        else:
            final = draft
            await delta(final.text)
    else:
        async with sw.pool.use(coord["model"], coord["ctx_per_slot"], coord["parallel"], pin=True) as url:
            final = await llm.chat(url, msgs, max_tokens=900, temperature=0.2, on_delta=delta, final=True)

    answer, sources = sw._cite(clean_citations(final.text), by_id)
    trace["notebook"] = {"notes": book.to_list(), "open_questions": book.open_questions}
    trace["drafts"] = drafts
    trace["final"] = {"answer": answer, "sources": sources, "seconds": round(final.seconds, 2)}
    results = []
    for lab in labels:
        rec = worker_recs[lab]
        mine = [n for n in book.notes if lab in n.readers or lab in n.agree]
        checked = [n for n in mine if n.status in ("supported", "partial", "unsupported")]
        rec["support_rate"] = (round(sum({"supported": 1, "partial": 0.5}.get(n.status, 0) for n in checked)
                                     / len(checked), 2) if checked else None)
        rec["claims"] = [{"claim": n.fact, "evidence": n.sources, "verdict": n.status} for n in mine]
        results.append(rec)
    trace["worker_results"] = results
    stats = sw._stats(results, t_start, stage_times)
    stats["mode"] = "notebook"
    stats["notebook"] = {"notes": len(book.notes),
                         "verified": sum(1 for n in book.notes if n.status == "supported"),
                         "found_by_2plus": sum(1 for n in book.notes if len(set(n.readers)) >= 2),
                         "disputed": sum(1 for n in book.notes if n.disputes),
                         "added_in_rounds": sum(1 for n in book.notes if n.added_in != "reading"),
                         "objections": len(trace.get("objections") or []),
                         "rejected_notes": book.rejected,
                         "unchecked": sum(1 for n in book.notes if n.status == "unchecked"),
                         "verify_retried_ok": verify_stats["retried_ok"],
                         "verify_failed": verify_stats["failed"]}
    trace["stats"] = stats
    path = _save(trace, getattr(sw, "_save_dir", None))
    await send({"type": "final", "answer": answer, "sources": sources, "stats": stats, "trace": path.name})
    return trace
