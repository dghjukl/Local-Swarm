"""The swarm loop for research questions.

  1. PLAN        coordinator decides: answer directly, or research (sub-questions + search queries)
  2. GATHER      web search + Wikipedia -> fetch pages -> ranked, citable passages [E1..En]
  3. WORK        a team of small models from different lineages answers every sub-question
                 from the passages, citing them, in parallel
  4. VERIFY      a verifier model checks each cited claim against its passages
  5. SYNTHESIZE  coordinator writes one answer, preferring verified claims, citing [E#]

Every run is saved to runtime/runs/*.json so it can be scored later.
"""
from __future__ import annotations

import asyncio
import datetime as dt
import json
import re
import time
from typing import Awaitable, Callable
from urllib.parse import urlparse

import httpx

from swarm import evidence as ev
from swarm import scholar
from swarm import strategies as strat
from swarm import llm
from swarm.paths import RUNS
from swarm.pool import ModelPool
from swarm.registry import ModelCard
from swarm.tools import Doc, ResearchMCP, wikipedia

Emit = Callable[[dict], Awaitable[None]]

# ------------------------------------------------------------------ prompts

PLAN_SYSTEM = """You coordinate a team of small AI models that can search the web.
Today is {today}. Decide how to handle the user's message.

Use mode "direct" ONLY for greetings, chit-chat, simple arithmetic, or rewriting text the user gave you.
Use mode "research" for anything that asks about facts, people, places, events, products, prices,
science, history, how-to, or anything that could have changed recently. When unsure, choose "research".

For research:
- subquestions: the FEWEST short, specific questions that together answer the user's message
  (one per distinct thing the user asked; usually 1 or 2, never more than 4).
  Do not add questions the user did not ask about.
- search_queries: 1 to 4 short keyword web searches (like you would type into a search engine)."""

PLAN_SCHEMA = {
    "type": "object",
    "properties": {
        "mode": {"type": "string", "enum": ["direct", "research"]},
        "subquestions": {"type": "array", "items": {"type": "string"}, "maxItems": 4},
        "search_queries": {"type": "array", "items": {"type": "string"}, "maxItems": 4},
    },
    "required": ["mode", "subquestions", "search_queries"],
}

DIRECT_SYSTEM = """You are a helpful assistant running locally. Today is {today}.
Answer clearly and concisely. If the question needs up-to-date facts you cannot know, say so."""

WORKER_SYSTEM = """You are a careful research assistant on a team. Answer the question using ONLY the
evidence passages provided. Every factual claim must cite the passage ids it comes from, like [E3].
If the passages do not contain the answer, say that plainly and leave claims empty.
Never add facts that are not in the passages. Keep the answer to 1-3 sentences and list at most
4 claims. Output the JSON only."""

WORKER_SCHEMA = {
    "type": "object",
    "properties": {
        "answer": {"type": "string"},
        "claims": {
            "type": "array",
            "maxItems": 5,
            "items": {
                "type": "object",
                "properties": {
                    "claim": {"type": "string"},
                    "evidence": {"type": "array", "items": {"type": "string"}, "maxItems": 3},
                },
                "required": ["claim", "evidence"],
            },
        },
        "confidence": {"type": "number"},
        "missing": {"type": "string"},
    },
    "required": ["answer", "claims", "confidence"],
}

# Granite Guardian's prompt format (from its model card): a <guardian> block appended as the last
# user message; 'yes' means the last assistant text meets the criterion
GUARDIAN_BLOCK = """<guardian><no-think>As a judge agent, assess whether the provided text meets the given judging criteria using all available information, including conversations, documents, and tools. Provide your score immediately without explanation. Output empty <think>
</think> tags followed by your score in <score></score> tags.

### Criteria: The assistant's text is fully supported by the passages in the conversation: every fact it states appears in, or follows directly from, those passages, and nothing in it contradicts them.

### Scoring Schema: If the last assistant's text meets the criteria, return 'yes'; otherwise, return 'no'."""

# used with the model's own thinking mode, where no grammar enforces the JSON shape
NATIVE_FORMAT = """
Think it through first. Then reply with ONLY this JSON object:
{"answer": "...", "claims": [{"claim": "...", "evidence": ["E3"]}], "confidence": 0.0-1.0, "missing": "..."}"""

WORKER_SCHEMA_REASONED = {
    "type": "object",
    "properties": {"reasoning": {"type": "string"}, **WORKER_SCHEMA["properties"]},
    "required": ["reasoning", *WORKER_SCHEMA["required"]],
}

VERIFY_SYSTEM = """You are a strict fact checker. For each numbered claim, decide whether the cited
passages support it:
- "supported": the passages clearly state it
- "partial": some of it is in the passages, some is not or is overstated
- "unsupported": the passages do not say this, or say something different
Judge only against the passages, not your own knowledge. Give a short reason."""

VERIFY_SCHEMA = {
    "type": "object",
    "properties": {
        "verdicts": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "n": {"type": "integer"},
                    "verdict": {"type": "string", "enum": ["supported", "partial", "unsupported"]},
                    "reason": {"type": "string"},
                },
                "required": ["n", "verdict", "reason"],
            },
        }
    },
    "required": ["verdicts"],
}

SOLO_SYSTEM = """You are a research assistant. Answer the user's question using ONLY the evidence passages.
- Lead with the direct answer, then brief supporting detail.
- Cite evidence ids in square brackets after each fact, like [E2]. Only cite ids that exist.
- If the evidence does not answer part of the question, say what is missing.
- Plain, clear language. No preamble. Today is {today}."""

SOLO_MERGE_SYSTEM = """You wrote several independent drafts answering the same question from the same
evidence. Write the one final answer for the user:
- Keep facts the drafts agree on AND the evidence supports. Where drafts disagree, check the evidence
  and go with what it says; if it cannot settle it, say so.
- Lead with the direct answer, then brief supporting detail.
- Cite evidence ids in square brackets after each fact, like [E2]. Only cite ids that exist.
- Plain, clear language. No preamble. Today is {today}."""

SYNTH_SYSTEM = """You are the coordinator of a research team. Several small models answered parts of
the user's question from the same evidence, and a fact checker marked each claim.
Write the final answer for the user:
- Lead with the direct answer, then brief supporting detail.
- Use claims marked SUPPORTED. Use PARTIAL claims only for the part the evidence backs.
  Ignore UNSUPPORTED claims.
- If team members disagree, check the evidence yourself and go with what it says. If the evidence
  cannot settle it, say so.
- Cite evidence ids in square brackets after each fact, like [E2]. Only cite ids that exist.
- If the evidence does not answer part of the question, say what is missing.
- Plain, clear language. No preamble. Today is {today}."""

ROLE_EXTRA_RULES = """
- Use names and numbers exactly as the FACT SHEET gives them; do not swap in a similar name from elsewhere.
- Apply the SKEPTIC's cautions: state the real strength of each finding (association, not cause;
  animals/lab only, not people; preliminary or not peer-reviewed) instead of overclaiming.
- If the PREMISE CHECK says the question assumes something untrue or not yet happened, say that first.
- Do not doubt a finding only because the evidence does not state its year."""

FACTS_SYSTEM = """You extract exact facts for a research team. From the passages, list the specific names,
numbers, dates and places that directly answer the question. Copy names and numbers exactly as written.
If the passages mention several similar things (for example several planets, drugs or studies), make
clear which one the question is about, and list the others under not_to_confuse.
Use only the passages. Cite passage ids like E3."""

FACTS_SCHEMA = {
    "type": "object",
    "properties": {
        "facts": {"type": "array", "maxItems": 8, "items": {"type": "object", "properties": {
            "fact": {"type": "string"}, "evidence": {"type": "array", "items": {"type": "string"}, "maxItems": 3}},
            "required": ["fact", "evidence"]}},
        "not_to_confuse": {"type": "array", "maxItems": 4, "items": {"type": "string"}},
    },
    "required": ["facts", "not_to_confuse"],
}

PREMISE_SYSTEM = """You check a user's question for a FALSE PREMISE: the question takes for granted that
something happened or exists, and a passage directly says it did NOT happen, does not exist, or has not
happened yet (for example "the telescope has not yet released images").
Answer premise_ok = true in every other case, including when:
- the passages do not mention the question's year or date, or give a different month
- the passages are vague, incomplete, or describe the finding in other words
- older reports disagree with a newer one
Most questions are fine: if you are unsure, premise_ok = true.
When premise_ok = false, copy into `quote` the exact sentence from a passage that contradicts the question."""

PREMISE_SCHEMA = {
    "type": "object",
    "properties": {"premise_ok": {"type": "boolean"}, "quote": {"type": "string"}, "problem": {"type": "string"},
                   "evidence": {"type": "array", "items": {"type": "string"}, "maxItems": 3}},
    "required": ["premise_ok", "quote", "problem"],
}


def _quote_found(quote: str, passages: list) -> bool:
    """True when the quoted sentence (or a long stretch of it) really is in a passage."""
    norm = lambda t: re.sub(r"[^a-z0-9]+", " ", t.lower()).strip()
    q = norm(quote)
    if len(q) < 25:
        return False
    text = " ".join(norm(p.text) for p in passages)
    words = q.split()
    return q in text or any(" ".join(words[i:i + 8]) in text for i in range(0, max(1, len(words) - 7), 4))


SKEPTIC_SYSTEM = """You are the team skeptic. For each numbered claim, decide whether its wording is STRONGER
than its cited passages allow. Look for:
- causation: says X causes/prevents Y when the passages only show an association or link
- lab_only: results in animals, cells or lab models stated as if shown in people
- preliminary: a conference talk, preprint or early result stated as settled
- overcertain: "proves", "first", "record", "confirmed" where the passages hedge
- wrong_entity: the claim names a different thing than the passages (a similar planet, drug, species...)
Use issue "none" when the wording is fine. Give a short corrected wording in fix."""

SKEPTIC_SCHEMA = {
    "type": "object",
    "properties": {"reviews": {"type": "array", "items": {"type": "object", "properties": {
        "n": {"type": "integer"},
        "issue": {"type": "string", "enum": ["none", "causation", "lab_only", "preliminary", "overcertain",
                                              "wrong_entity", "other"]},
        "fix": {"type": "string"}}, "required": ["n", "issue", "fix"]}}},
    "required": ["reviews"],
}

ROLE_LABELS = {"facts": "Fact sheet", "premise": "Premise check", "skeptic": "Skeptic"}

VERDICT_WEIGHT = {"supported": 1.0, "partial": 0.5, "unsupported": 0.0, "uncited": 0.0}


def _today() -> str:
    return dt.date.today().strftime("%A, %B %d, %Y")


def _interleave(groups: list[list[ev.Passage]], n: int) -> list[ev.Passage]:
    """Take passages round-robin from each sub-question's ranked list, no duplicates, at most n."""
    out, seen = [], set()
    for rank in range(max((len(g) for g in groups), default=0)):
        for g in groups:
            if rank < len(g) and g[rank].id not in seen:
                seen.add(g[rank].id)
                out.append(g[rank])
    return sorted(out[:n], key=lambda p: int(p.id[1:]))


def _fmt_passages(ps: list[ev.Passage], limit: int | None = None) -> str:
    out = []
    for p in ps:
        text = p.text if limit is None else p.text[:limit]
        out.append(f"[{p.id}] ({p.title})\n{text}")
    return "\n\n".join(out)


class Swarm:
    def __init__(self, cfg: dict, pool: ModelPool, cards: dict[str, ModelCard], research: ResearchMCP | None):
        self.cfg = cfg
        self.pool = pool
        self.cards = cards
        self.research = research

    # ------------------------------------------------------------ roles
    def role(self, name: str) -> dict:
        return self.cfg[name]

    def roles(self) -> list[dict]:
        """Non-answerer roles from workers.roles, e.g. {role: skeptic, model: Granite-4.1-3B}."""
        return [r for r in self.cfg["workers"].get("roles") or []
                if r.get("role") != "answerer" and r.get("model") in self.cards]

    def team(self) -> list[str]:
        roles = self.cfg["workers"].get("roles")
        if roles:  # role-based team: answerers are the workers
            return [r["model"] for r in roles if r.get("role") == "answerer" and r.get("model") in self.cards]
        explicit = self.cfg["workers"].get("team")
        if explicit:  # fixed team from config (used by eval configs); repeats allowed
            return [m for m in explicit if m in self.cards]
        coord, verifier = self.cfg["coordinator"]["model"], self.cfg["verifier"]["model"]
        size = int(self.cfg["workers"]["team_size"])
        picked, lineages = [], set()
        for mid in self.cfg["workers"]["pool"]:
            card = self.cards.get(mid)
            if not card or card.kind != "chat" or mid in (coord, verifier):
                continue
            if card.lineage in lineages:
                continue
            picked.append(mid)
            lineages.add(card.lineage)
            if len(picked) == size:
                break
        return picked

    def team_strategies(self) -> list[str | None]:
        """Reasoning strategy per team member (None = answer directly), aligned with team().

        workers.roles answerers may each carry `strategy`; otherwise workers.strategies is a list
        handed out in team order (cycled), or workers.strategy applies to everyone."""
        w, team = self.cfg["workers"], self.team()
        if w.get("roles"):
            got = [r.get("strategy") for r in w["roles"]
                   if r.get("role") == "answerer" and r.get("model") in self.cards]
        elif w.get("strategies"):
            lst = list(w["strategies"])
            got = [lst[i % len(lst)] for i in range(len(team))]
        else:
            got = [w.get("strategy")] * len(team)
        return [s if s in strat.STRATEGIES and s != "direct" else None for s in got]

    def team_slots(self) -> list[tuple[str, str]]:
        """(label, model) per team member. A worker with a reasoning strategy is labelled
        'Model / Strategy'; repeated labels get '#2', '#3'."""
        team, strategies = self.team(), self.team_strategies()
        bases = [m if not s else f"{m} / {strat.label(s)}" for m, s in zip(team, strategies)]
        seen, out = {}, []
        self._slot_strategy = {}
        for base, m, s in zip(bases, team, strategies):
            seen[base] = seen.get(base, 0) + 1
            label = f"{base}#{seen[base]}" if bases.count(base) > 1 else base
            self._slot_strategy[label] = s
            out.append((label, m))
        return out

    def mode(self) -> str:
        return self.cfg.get("mode", "swarm")

    def check_roster(self) -> list[str]:
        problems = []
        for role in ("coordinator", "verifier"):
            if self.cfg[role]["model"] not in self.cards:
                problems.append(f"{role} model '{self.cfg[role]['model']}' not found in Models/")
        if self.mode() == "swarm" and not self.team():
            problems.append("no usable worker models found (check workers.pool in config/swarm.yaml)")
        return problems

    # ------------------------------------------------------------ run
    async def prepare(self, question: str, emit: Emit | None = None) -> dict:
        """Plan + gather only. Returns {'plan', 'docs'} that run(prepared=...) can reuse, so every
        configuration in an evaluation sees exactly the same sub-questions and sources."""
        async def noop(e: dict) -> None:
            pass
        send = emit or noop
        self.pool.emit = send
        plan = await self._plan(question, force_research=True)
        docs = await self._gather(plan["search_queries"], send)
        return {"plan": plan, "docs": [d.__dict__ for d in docs]}

    async def _plan(self, question: str, force_research: bool) -> dict:
        coord = self.role("coordinator")
        async with self.pool.use(coord["model"], coord["ctx_per_slot"], coord["parallel"], pin=True) as url:
            plan_res = await llm.chat_json(url, [
                {"role": "system", "content": PLAN_SYSTEM.format(today=_today())},
                {"role": "user", "content": question},
            ], PLAN_SCHEMA, max_tokens=400)
        plan = plan_res.data or {}
        mode = "research" if force_research else plan.get("mode", "research")
        subqs = [s.strip() for s in plan.get("subquestions", []) if s.strip()][:4] or [question]
        queries = [q.strip() for q in plan.get("search_queries", []) if q.strip()]
        queries = queries[: self.cfg["research"]["max_search_queries"]] or [question]
        return {"mode": mode, "subquestions": subqs, "search_queries": queries, "seconds": round(plan_res.seconds, 2)}

    async def run(self, question: str, emit: Emit, force_research: bool = False,
                  prepared: dict | None = None, save_dir=None) -> dict:
        trace: dict = {"question": question, "started": dt.datetime.now().isoformat(timespec="seconds"),
                       "mode": self.mode(),
                       "config": {k: self.cfg[k] for k in ("coordinator", "workers", "verifier", "research")},
                       "events": []}
        self._save_dir = save_dir
        llm.start_usage()  # counts every token read and written during this run
        bud = self.cfg.get("budget") or {}
        # normalized-budget runs: hard ceilings on tokens written and wall time for the whole run
        llm.start_budget(bud.get("max_output_tokens"), bud.get("max_seconds"),
                         bud.get("reserve_tokens", 900), bud.get("reserve_seconds", 45))
        t_start = time.time()
        stage_times: dict[str, float] = {}

        async def send(e: dict) -> None:
            e.setdefault("t", round(time.time() - t_start, 2))
            trace["events"].append(e)
            await emit(e)

        async def stage(name: str, label: str) -> None:
            stage_times[name] = time.time()
            await send({"type": "stage", "stage": name, "label": label})

        self.pool.emit = send
        coord = self.role("coordinator")
        today = _today()
        if self.mode() == "swarm":
            self.pool.plan_ahead([coord["model"], *[m for _, m in self.team_slots()], self.cfg["verifier"]["model"]])
        else:
            self.pool.plan_ahead([coord["model"]])
        await send({"type": "run_start", "question": question})
        try:
            # ---------------- 1. plan
            await stage("plan", "Coordinator is planning")
            if prepared:
                plan = dict(prepared["plan"], mode="research", reused=True)
            else:
                plan = await self._plan(question, force_research)
            mode, subqs, queries = plan["mode"], plan["subquestions"], plan["search_queries"]
            trace["plan"] = plan
            await send({"type": "plan", **plan})

            if mode == "direct":
                return await self._finish_direct(question, send, stage, trace, t_start, today)

            # ---------------- 2. gather evidence
            await stage("gather", "Searching and reading sources")
            k = self.cfg["research"]["passages_per_subquestion"]
            split = (not prepared and self.mode() == "swarm" and len(subqs) > 1
                     and bool(self.cfg["research"].get("split_by_subquestion")))
            if prepared:
                docs = [Doc(**d) for d in prepared["docs"]]
            else:
                docs = await self._gather(queries, send)
            if split:
                # swarm-style research: besides the shared search, every part of the question gets its
                # own searches and reading, in parallel (more ground covered than one searcher)
                await send({"type": "stage_note", "message": f"researching {len(subqs)} parts separately"})
                have = {d.url for d in docs}
                per = await asyncio.gather(*(self._gather_one(sq, question, send, have, delay=1.5 * i)
                                             for i, sq in enumerate(subqs)))
                size = self.cfg["research"]["passage_chars"]
                shared = ev.build_passages(docs, size=size)
                groups = []
                for sq, own in zip(subqs, per):
                    pool_i = shared + ev.build_passages(own, size=size)
                    groups.append(await self._pick(pool_i, [sq, question], k, send))
                seen_urls = {d.url for d in docs}
                docs = docs + [d for own in per for d in own if d.url not in seen_urls and not seen_urls.add(d.url)]
            else:
                passages = ev.build_passages(docs, size=self.cfg["research"]["passage_chars"])
                groups = [await self._pick(passages, [sq, question], k, send) for sq in subqs]
            evidence = ev.assign_ids(groups)
            trace["evidence"] = [p.to_dict() for p in evidence]
            trace["sources_fetched"] = [{"url": d.url, "title": d.title, "source": d.source,
                                         "error": d.error, "chars": len(d.text)} for d in docs]
            await send({"type": "evidence", "passages": [
                {"id": p.id, "title": p.title, "url": p.url, "snippet": p.text[:220]} for p in evidence]})
            if not evidence:
                await send({"type": "warning", "message": "No usable sources were found; answering without evidence."})
                return await self._finish_direct(question, send, stage, trace, t_start, today, no_sources=True)

            if self.mode() == "solo":  # baseline: the coordinator alone reads the evidence and answers
                return await self._finish_solo(question, subqs, groups, evidence, send, stage, trace,
                                               t_start, stage_times, today)

            # ---------------- 3. workers
            slots = self.team_slots()
            team = [label for label, _ in slots]
            trace["team"] = team
            await send({"type": "team", "coordinator": coord["model"], "verifier": self.cfg["verifier"]["model"],
                        "workers": [{"model": label, "lab": self.cards[m].lab, "lineage": self.cards[m].lineage,
                                     "strategy": self._slot_strategy.get(label)}
                                    for label, m in slots]})
            await stage("work", f"{len(team)} models answering {len(subqs)} sub-question(s)")
            # One GPU lease per model: it loads once and answers every sub-question.
            # The pool is told what comes next (workers -> verifier -> coordinator) so it evicts the
            # right models and loads the verifier in the background as soon as there is room.
            by_id = {p.id: p for p in evidence}
            v = self.role("verifier")
            copies = {m: sum(1 for _, x in slots if x == m) for _, m in slots}
            worker_models = list(copies)
            extra = self.roles()
            role_models = [r["model"] for r in extra if r["model"] not in worker_models
                           and r["model"] not in (v["model"], coord["model"])]
            running_workers, finished = list(dict.fromkeys(worker_models + role_models)), []
            if extra:
                await send({"type": "roles", "roles": [{"role": r["role"], "model": r["model"]} for r in extra]})
            role_out: dict[str, dict] = {}
            role_passages = _interleave(groups, 10)  # small models have a 4k context: keep the best 10
            early_roles = [asyncio.create_task(self._run_role(r, question, subqs, role_passages, [], copies, send, role_out))
                           for r in extra if r["role"] in ("facts", "premise")]

            def replan() -> None:
                self.pool.plan_ahead([*running_workers, v["model"], coord["model"], *finished])

            replan()
            self.pool.prefetch(v["model"], v["ctx_per_slot"], v["parallel"])
            verify_tasks: list[asyncio.Task] = []

            async def work_then_verify(label: str, m: str) -> list[dict]:
                rs = await self._work_model(label, m, copies[m], subqs, groups, question, send)
                # this worker is done: it is not needed again until the next question,
                # and its answers can be fact-checked while the others are still working
                done_labels.add(label)
                if all(lab in done_labels for lab, mm in slots if mm == m) and m in running_workers:
                    running_workers.remove(m)
                    finished.append(m)
                    replan()
                verify_tasks.extend(asyncio.create_task(self._verify(r, groups[r["subq"]], by_id, send))
                                    for r in rs if not r.get("error"))
                return rs

            done_labels: set[str] = set()
            per_model = await asyncio.gather(*(work_then_verify(label, m) for label, m in slots))
            results = [r for rs in per_model for r in rs]
            await asyncio.gather(*early_roles)

            # ---------------- 4. verify (already started for workers that finished early)
            await stage("verify", "Fact-checking every claim")
            self.pool.plan_ahead([v["model"], coord["model"], *worker_models])
            await asyncio.gather(*verify_tasks)
            trace["worker_results"] = results
            if self.cfg["workers"].get("screen"):
                return await self._finish_screen(question, subqs, results, by_id, send, trace, t_start, stage_times)
            # the skeptic reviews the (verified) claims for overstatement
            claims = [c for r in results for c in r.get("claims", [])
                      if c.get("verdict") in ("supported", "partial", "unchecked")]
            await asyncio.gather(*(self._run_role(r, question, subqs, evidence, claims, copies, send, role_out)
                                   for r in extra if r["role"] == "skeptic"))
            trace["roles"] = role_out

            # ---------------- 5. synthesize
            await stage("synthesize", "Coordinator is writing the final answer")
            self.pool.plan_ahead([coord["model"], *worker_models, v["model"]])
            digest = self._digest(subqs, results)
            used_ids = sorted({p.id for g in groups for p in g}, key=lambda x: int(x[1:]))
            used = [by_id[i] for i in used_ids]
            extras_txt = self._roles_digest(role_out)
            msgs = [
                {"role": "system", "content": SYNTH_SYSTEM.format(today=today) + (ROLE_EXTRA_RULES if role_out else "")},
                {"role": "user", "content": f"User question: {question}\n\n{extras_txt}=== Team answers ===\n{digest}\n\n"
                                            f"=== Evidence ===\n{_fmt_passages(used, limit=900)}"},  # same as solo
            ]

            async def delta(txt: str) -> None:
                await send({"type": "answer_delta", "text": txt})

            async with self.pool.use(coord["model"], coord["ctx_per_slot"], coord["parallel"], pin=True) as url:
                final = await llm.chat(url, msgs, max_tokens=900, temperature=0.2, on_delta=delta, final=True)
            answer, sources = self._cite(final.text, by_id)
            trace["final"] = {"answer": answer, "sources": sources, "seconds": round(final.seconds, 2),
                              "tokens_per_second": round(final.tokens_per_second, 1)}
            # keep the team warm for the next question: reload workers in the background
            # (this pushes out the verifier, which is needed last)
            w = self.role("workers")
            for m in worker_models:
                self.pool.prefetch(m, w["ctx_per_slot"], w["parallel"] * copies[m])
            stats = self._stats(results, t_start, stage_times)
            trace["stats"] = stats
            path = _save(trace, getattr(self, '_save_dir', None))
            await send({"type": "final", "answer": answer, "sources": sources, "stats": stats,
                        "trace": path.name})
            return trace
        except asyncio.CancelledError:
            trace["cancelled"] = True
            _save(trace, getattr(self, '_save_dir', None))
            raise
        except Exception as e:  # report, save, and keep the server alive
            trace["error"] = f"{type(e).__name__}: {e}"
            _save(trace, getattr(self, '_save_dir', None))
            await send({"type": "error", "message": trace["error"]})
            return trace

    # ------------------------------------------------------------ steps
    async def _finish_direct(self, question, send, stage, trace, t_start, today, no_sources=False) -> dict:
        coord = self.role("coordinator")
        await stage("synthesize", "Coordinator is answering directly")
        system = DIRECT_SYSTEM.format(today=today)
        if no_sources:
            system += "\nNo web sources could be found for this question. Say that your answer is from memory and may be out of date."

        async def delta(txt: str) -> None:
            await send({"type": "answer_delta", "text": txt})

        async with self.pool.use(coord["model"], coord["ctx_per_slot"], coord["parallel"], pin=True) as url:
            res = await llm.chat(url, [{"role": "system", "content": system},
                                       {"role": "user", "content": question}],
                                 max_tokens=900, temperature=0.4, on_delta=delta, final=True)
        trace["final"] = {"answer": res.text, "sources": [], "seconds": round(res.seconds, 2)}
        trace["stats"] = {"total_seconds": round(time.time() - t_start, 1), "mode": "direct"}
        path = _save(trace, getattr(self, '_save_dir', None))
        await send({"type": "final", "answer": res.text, "sources": [], "stats": trace["stats"], "trace": path.name})
        return trace

    async def _finish_solo(self, question, subqs, groups, evidence, send, stage, trace, t_start,
                           stage_times, today) -> dict:
        coord = self.role("coordinator")
        await stage("synthesize", "Coordinator is answering alone from the evidence")
        by_id = {p.id: p for p in evidence}
        parts = "\n".join(f"- {sq}" for sq in subqs)
        msgs = [{"role": "system", "content": SOLO_SYSTEM.format(today=today)},
                {"role": "user", "content": f"User question: {question}\n\nParts to cover:\n{parts}\n\n"
                                            f"=== Evidence ===\n{_fmt_passages(evidence, limit=900)}"}]

        async def delta(txt: str) -> None:
            await send({"type": "answer_delta", "text": txt})

        n = int(self.cfg.get("solo_samples", 1) or 1)
        async with self.pool.use(coord["model"], coord["ctx_per_slot"], coord["parallel"], pin=True) as url:
            if n > 1:
                # equal-compute baseline: the same single model spends a swarm-sized budget by writing
                # several independent drafts, then merging them (self-consistency)
                drafts = []
                for i in range(n):
                    try:
                        d = await llm.chat(url, msgs, max_tokens=700, temperature=0.8)
                    except llm.BudgetExhausted:  # normalized budget: merge the drafts written so far
                        break
                    drafts.append(d.text)
                    await send({"type": "draft", "n": i + 1, "of": n, "seconds": round(d.seconds, 1)})
                if len(drafts) <= 1:  # nothing to merge: answer once
                    drafts = []
            if n > 1 and drafts:
                merge = [{"role": "system", "content": SOLO_MERGE_SYSTEM.format(today=today)},
                         {"role": "user", "content": f"User question: {question}\n\n"
                          + "\n\n".join(f"=== Draft {i + 1} ===\n{t}" for i, t in enumerate(drafts))
                          + f"\n\n=== Evidence ===\n{_fmt_passages(evidence, limit=900)}"}]
                final = await llm.chat(url, merge, max_tokens=900, temperature=0.2, on_delta=delta, final=True)
                trace["drafts"] = drafts
            else:
                final = await llm.chat(url, msgs, max_tokens=900, temperature=0.2, on_delta=delta, final=True)
        answer, sources = self._cite(final.text, by_id)
        trace["final"] = {"answer": answer, "sources": sources, "seconds": round(final.seconds, 2),
                          "tokens_per_second": round(final.tokens_per_second, 1)}
        trace["worker_results"] = []
        trace["stats"] = self._stats([], t_start, stage_times)
        trace["stats"]["mode"] = "solo"
        path = _save(trace, self._save_dir)
        await send({"type": "final", "answer": answer, "sources": sources, "stats": trace["stats"], "trace": path.name})
        return trace

    async def _finish_screen(self, question, subqs, results, by_id, send, trace, t_start, stage_times) -> dict:
        """Strategy screen: no coordinator synthesis. The graded answer is simply what the worker(s)
        wrote for each part of the question, so the grade measures the worker, not the coordinator."""
        parts = []
        for i, sq in enumerate(subqs):
            for r in results:
                if r["subq"] == i:
                    body = r.get("answer") or ("(no answer: " + str(r.get("error"))[:120] + ")" if r.get("error") else "(no answer)")
                    parts.append(f"{sq}\n{body}")
        answer, sources = self._cite("\n\n".join(parts), by_id)
        trace["final"] = {"answer": answer, "sources": sources, "seconds": 0.0, "screen": True}
        if results and all(r.get("error") for r in results):  # nothing was answered: a failed run, not an answer
            trace["error"] = "every worker failed: " + str(results[0].get("error"))[:300]
        stats = self._stats(results, t_start, stage_times)
        stats["mode"] = "screen"
        trace["stats"] = stats
        path = _save(trace, getattr(self, '_save_dir', None))
        await send({"type": "final", "answer": answer, "sources": sources, "stats": stats, "trace": path.name})
        return trace

    async def _pick(self, passages: list[ev.Passage], queries: list[str], k: int, send: Emit) -> list[ev.Passage]:
        """The k passages the models will read. By default keyword ranking (BM25). With
        research.reranker set, a reranker model re-orders the best ~40 keyword candidates plus every
        article's opening, reading each passage against the question (it catches passages that
        answer the question in different words, which keyword ranking misses)."""
        model = self.cfg["research"].get("reranker")
        if not model or model not in self.cards or len(passages) <= k:
            return ev.select(passages, queries, k)
        cands = ev.select(passages, queries, int(self.cfg["research"].get("rerank_candidates", 40)), per_source=8)
        have = {(p.url, p.pos) for p in cands}
        cands += [p for p in passages if p.pos == 0 and (p.url, p.pos) not in have]
        query = " ".join(q.strip() for q in reversed(queries) if q.strip())  # whole question, then this part
        try:
            async with self.pool.use(model, 8192, 1) as url:
                async with httpx.AsyncClient(timeout=httpx.Timeout(120, connect=10)) as c:
                    r = await c.post(url.rstrip("/") + "/v1/rerank",
                                     json={"query": query, "documents": [f"{p.title}\n{p.text}" for p in cands],
                                           "top_n": len(cands)})
                    r.raise_for_status()
                    res = r.json().get("results", [])
            scores = {int(x["index"]): float(x.get("relevance_score", x.get("score", 0.0))) for x in res}
            if not scores or max(scores.values()) < 1e-4:  # a broken reranker GGUF gives ~0 for everything
                raise ValueError("reranker returned no usable scores")
        except Exception as e:
            await send({"type": "warning", "message": f"reranker {model} failed ({e}); using keyword ranking"[:300]})
            return ev.select(passages, queries, k)
        order = sorted(range(len(cands)), key=lambda i: -scores.get(i, 0.0))
        n_urls = len({p.url for p in cands})
        per_source = k if n_urls <= 3 else max(2, k // 2)
        picked, per = [], {}
        for i in order:
            p = cands[i]
            if per.get(p.url, 0) >= per_source:
                continue
            per[p.url] = per.get(p.url, 0) + 1
            picked.append(ev.Passage(**{**p.to_dict(), "score": round(scores.get(i, 0.0), 4)}))
            if len(picked) >= k:
                break
        return picked

    async def _gather(self, queries: list[str], send: Emit, max_pages: int | None = None,
                      scholarly: bool = True, skip_urls: set | None = None) -> list[Doc]:
        rc = self.cfg["research"]
        docs: list[Doc] = []

        async def web(q: str, delay: float = 0.0) -> list[dict]:
            """Search; if it errors or comes back empty (search engines rate-limit bursts),
            wait and retry, then try a simpler version of the query."""
            if not self.research:
                return []
            await asyncio.sleep(delay)  # stagger queries instead of firing them all at once
            attempts = [q, q, _simplify_query(q)]
            err = ""
            for n, attempt in enumerate(attempts):
                if n:
                    await asyncio.sleep(2.0 * n)
                try:
                    hits = await self.research.search(attempt, rc["results_per_query"])
                except Exception as e:
                    hits, err = [], str(e)[:200]
                if hits:
                    await send({"type": "search", "query": attempt, "backend": "web", "attempt": n + 1,
                                "results": [{"title": h.get("title", ""), "url": h["url"]} for h in hits]})
                    return hits
            await send({"type": "search", "query": q, "backend": "web", "results": [],
                        "error": err or "no results after 3 attempts"})
            return []

        async def news(q: str, delay: float = 0.0) -> list[dict]:
            """DuckDuckGo News: recent articles (best for new discoveries)."""
            n = int(rc.get("news_results_per_query", 0) or 0)
            if not self.research or not n or not hasattr(self.research, "news"):
                return []
            await asyncio.sleep(delay)
            q2 = _simplify_query(q) or q
            for attempt in (q, q2):
                try:
                    hits = await self.research.news(attempt, n)
                except Exception as e:
                    hits = []
                    err = str(e)[:200]
                else:
                    err = ""
                if hits:
                    await send({"type": "search", "query": attempt, "backend": "news",
                                "results": [{"title": h.get("title", ""), "url": h["url"]} for h in hits]})
                    return hits
                await asyncio.sleep(1.5)
            await send({"type": "search", "query": q, "backend": "news", "results": [], "error": err or "no results"})
            return []

        async def papers(q: str) -> list[Doc]:
            """Scholarly records (journal, date, peer-reviewed or preprint, abstract)."""
            if not self.research or not rc.get("scholarly", True):
                return []
            q2 = _simplify_query(q) or q
            try:
                got = await asyncio.wait_for(scholar.search_all(q2, int(rc.get("scholarly_results", 2)),
                                                                rc.get("scholarly_sources"), since=scholar.recent_since(q)),
                                             60)
            except asyncio.TimeoutError:
                await send({"type": "search", "query": q2, "backend": "scholarly", "results": [],
                            "error": "scholarly sources gave no answer within 60s"})
                return []
            out = []
            for name, res in got.items():
                if isinstance(res, Exception):
                    await send({"type": "search", "query": q2, "backend": name, "results": [],
                                "error": f"{type(res).__name__}: {res}"[:200]})
                    continue
                await send({"type": "search", "query": q2, "backend": name,
                            "results": [{"title": d.title, "url": d.url} for d in res]})
                out.extend(res)
            return out

        async def wiki(q: str) -> list[Doc]:
            try:
                ds = await asyncio.wait_for(wikipedia(q, rc["wikipedia_results"]), 45)
            except Exception as e:
                await send({"type": "search", "query": q, "backend": "wikipedia", "error": str(e)[:200], "results": []})
                return []
            await send({"type": "search", "query": q, "backend": "wikipedia",
                        "results": [{"title": d.title, "url": d.url} for d in ds]})
            return ds

        web_hits, news_hits, wiki_docs, paper_docs = await asyncio.gather(
            asyncio.gather(*(web(q, delay=0.8 * i) for i, q in enumerate(queries))),
            asyncio.gather(*(news(q, delay=0.4 + 0.8 * i) for i, q in enumerate(queries[:2]))),
            asyncio.gather(*(wiki(q) for q in queries[:2])),
            asyncio.gather(*(papers(q) for q in (queries[: int(rc.get("scholarly_queries", 1))] if scholarly else []))),
        )
        seen = set(skip_urls or ())
        for group in wiki_docs:
            for d in group:
                if d.url not in seen:
                    seen.add(d.url)
                    docs.append(d)
        n_papers = 0
        for group in paper_docs:
            for d in group:
                key = d.url.lower().replace("https://doi.org/", "").replace("http://dx.doi.org/", "")
                if key not in seen and n_papers < int(rc.get("max_papers", 6)):
                    seen.add(key)
                    seen.add(d.url)
                    n_papers += 1
                    docs.append(d)
        # news articles first at each rank: they are the freshest reports of new findings
        web_hits = [*news_hits, *web_hits]
        # round-robin across queries so each query contributes its best hits; limit per domain
        urls, per_domain = [], {}
        for rank in range(rc["results_per_query"]):
            for hits in web_hits:
                if rank < len(hits):
                    u = hits[rank]["url"]
                    dom = urlparse(u).netloc.lower().removeprefix("www.")
                    if (u in seen or per_domain.get(dom, 0) >= 2 or dom.endswith("wikipedia.org")
                            or _blocked(dom, rc.get("block_domains"))):
                        continue
                    seen.add(u)
                    per_domain[dom] = per_domain.get(dom, 0) + 1
                    urls.append(u)
        urls = urls[: max_pages or rc["max_pages"]]

        async def fetch(u: str) -> Doc:
            d = await self.research.fetch(u)
            await send({"type": "fetch", "url": u, "title": d.title, "ok": not d.error and bool(d.text),
                        "error": d.error[:160], "chars": len(d.text)})
            return d

        if urls and self.research:
            docs.extend(await asyncio.gather(*(fetch(u) for u in urls)))
        return docs

    async def _gather_one(self, subq: str, question: str, send: Emit, have: set, delay: float = 0.0) -> list[Doc]:
        """One sub-question's own research: its own web + news search, a few pages, no scholarly
        (the shared search already covered papers)."""
        await asyncio.sleep(delay)
        q = _simplify_query(subq) or subq
        return await self._gather([q], send, max_pages=int(self.cfg["research"].get("split_max_pages", 4)),
                                  scholarly=False, skip_urls=have)

    async def _work_model(self, label: str, model: str, copies: int, subqs: list[str],
                          groups: list[list[ev.Passage]], question: str, send: Emit) -> list[dict]:
        w = self.role("workers")
        try:
            async with self.pool.use(model, w["ctx_per_slot"], w["parallel"] * copies) as url:
                return list(await asyncio.gather(*(
                    self._work(url, label, model, i, sq, groups[i], question, send) for i, sq in enumerate(subqs))))
        except Exception as e:  # the model itself could not be loaded
            out = []
            for i, sq in enumerate(subqs):
                rec = {"model": label, "base_model": model, "lab": self.cards[model].lab, "subq": i, "subquestion": sq,
                       "error": f"{type(e).__name__}: {e}"[:400]}
                await send({"type": "worker_result", **rec})
                out.append(rec)
            return out

    async def _work(self, url: str, label: str, model: str, i: int, subq: str, passages: list[ev.Passage],
                    question: str, send: Emit) -> dict:
        how = getattr(self, "_slot_strategy", {}).get(label)
        rec = {"model": label, "base_model": model, "lab": self.cards[model].lab, "subq": i, "subquestion": subq,
               "strategy": how}
        await send({"type": "worker_start", "model": label, "subq": i})
        user = (f"Question: {subq}\n(This is part of the larger question: {question})\n\n"
                f"Evidence passages:\n{_fmt_passages(passages)}")
        native = how == strat.NATIVE
        temp = float(self.role("workers").get("temperature", 0.2))
        try:
            if native:
                # the model's own thinking mode: think first (hidden), then the JSON. No grammar, so the
                # thinking is not cut off; the JSON is parsed from the reply.
                res = await llm.chat_json(url, [{"role": "system", "content": WORKER_SYSTEM + NATIVE_FORMAT},
                                                {"role": "user", "content": user}],
                                          WORKER_SCHEMA, max_tokens=int(self.role("workers").get("think_tokens", 3000)),
                                          temperature=max(temp, 0.6), think=True, grammar=False, timeout=600)
            else:
                res = await llm.chat_json(url, [{"role": "system", "content": WORKER_SYSTEM + strat.instruction(how)},
                                                {"role": "user", "content": user}],
                                          WORKER_SCHEMA_REASONED if how else WORKER_SCHEMA,
                                          max_tokens=950 if how else 600, temperature=temp)
            data = res.data if isinstance(res.data, dict) else {}
            claims = []
            for c in data.get("claims", [])[:5]:
                if not isinstance(c, dict) or not str(c.get("claim", "")).strip():
                    continue
                ids = _evidence_ids(c.get("evidence", []))
                claims.append({"claim": c["claim"].strip(), "evidence": ids})
            rec.update({
                "answer": str(data.get("answer", "")).strip(),
                "claims": claims,
                "confidence": _clamp(data.get("confidence", 0.5)),
                "missing": str(data.get("missing", "") or ""),
                "reasoning": (res.reasoning[:1500] if native else str(data.get("reasoning", "") or "")[:1500]) if how else "",
                "thought_chars": len(res.reasoning or "") if native else len(str(data.get("reasoning", "") or "")),
                "completion_tokens": res.completion_tokens,
                "seconds": round(res.seconds, 2),
                "tokens_per_second": round(res.tokens_per_second, 1),
            })
        except Exception as e:
            rec["error"] = f"{type(e).__name__}: {e}"[:600]
        await send({"type": "worker_result", **rec})
        return rec

    async def _verify(self, rec: dict, passages: list[ev.Passage], by_id: dict, send: Emit) -> None:
        allowed = {p.id for p in passages}
        to_check, verdicts = [], []
        for n, c in enumerate(rec.get("claims", []), 1):
            ids = [i for i in c["evidence"] if i in allowed and i in by_id]
            if not ids:
                verdicts.append({"n": n, "verdict": "uncited", "reason": "no valid evidence cited"})
            else:
                c["evidence"] = ids
                to_check.append((n, c))
        if to_check:
            cited = sorted({i for _, c in to_check for i in c["evidence"]}, key=lambda x: int(x[1:]))
            claims_txt = "\n".join(f"{n}. {c['claim']}  (cites {', '.join(c['evidence'])})" for n, c in to_check)
            user = f"Passages:\n{_fmt_passages([by_id[i] for i in cited])}\n\nClaims to check:\n{claims_txt}"
            v = self.role("verifier")
            try:
                async with self.pool.use(v["model"], v["ctx_per_slot"], v["parallel"]) as url:
                    if v.get("style") == "guardian":
                        got = await self._guardian_verdicts(url, to_check, by_id)
                    else:
                        res = await llm.chat_json(url, [{"role": "system", "content": VERIFY_SYSTEM},
                                                        {"role": "user", "content": user}],
                                                  VERIFY_SCHEMA, max_tokens=500)
                        got = {int(x.get("n", -1)): x for x in (res.data or {}).get("verdicts", [])
                               if isinstance(x, dict)}
                for n, _ in to_check:
                    x = got.get(n)
                    verdicts.append({"n": n, "verdict": x["verdict"] if x else "unsupported",
                                     "reason": (x or {}).get("reason", "verifier gave no verdict")})
            except Exception as e:
                for n, _ in to_check:
                    verdicts.append({"n": n, "verdict": "unchecked", "reason": f"verifier error: {e}"[:200]})
        verdicts.sort(key=lambda x: x["n"])
        for vd in verdicts:
            rec["claims"][vd["n"] - 1]["verdict"] = vd["verdict"]
            rec["claims"][vd["n"] - 1]["reason"] = vd["reason"]
        scored = [VERDICT_WEIGHT[vd["verdict"]] for vd in verdicts if vd["verdict"] in VERDICT_WEIGHT]
        rec["support_rate"] = round(sum(scored) / len(scored), 2) if scored else None
        await send({"type": "verdicts", "model": rec["model"], "subq": rec["subq"],
                    "claims": rec["claims"], "support_rate": rec["support_rate"]})

    async def _guardian_verdicts(self, url: str, to_check: list, by_id: dict) -> dict:
        """IBM Granite Guardian as the fact checker. It is trained for one job: a yes/no judgement of
        a text against a criterion, here 'is this claim fully supported by these passages'. It is
        asked once per claim in its own prompt format (a <guardian> block, <score>yes|no</score>)."""
        async def one(n: int, c: dict) -> tuple[int, dict]:
            passages = _fmt_passages([by_id[i] for i in c["evidence"] if i in by_id])
            msgs = [{"role": "user", "content": f"Passages:\n{passages}\n\nState one fact from these passages."},
                    {"role": "assistant", "content": c["claim"]},
                    {"role": "user", "content": GUARDIAN_BLOCK}]
            res = await llm.chat(url, msgs, max_tokens=40, temperature=0.0)
            m = re.search(r"<score>\s*(yes|no)\s*</score>", (res.text or "") + (res.reasoning or ""), re.I)
            if not m:
                return n, {"verdict": "unchecked", "reason": f"guardian gave no score: {res.text[:80]!r}"}
            ok = m.group(1).lower() == "yes"
            return n, {"verdict": "supported" if ok else "unsupported",
                       "reason": "guardian: supported by the cited passages" if ok else "guardian: not supported"}
        return dict(await asyncio.gather(*(one(n, c) for n, c in to_check)))

    def _lease_params(self, model: str, copies: dict[str, int]) -> tuple[int, int]:
        """Use the same context/slots a model already runs with, so a role never forces a restart."""
        c, v, w = self.role("coordinator"), self.role("verifier"), self.role("workers")
        if model == c["model"]:
            return c["ctx_per_slot"], c["parallel"]
        if model == v["model"]:
            return v["ctx_per_slot"], v["parallel"]
        return w["ctx_per_slot"], w["parallel"] * copies.get(model, 1)

    async def _run_role(self, spec: dict, question: str, subqs: list[str], evidence: list[ev.Passage],
                        claims: list[dict], copies: dict, send: Emit, out: dict) -> None:
        role, model = spec["role"], spec["model"]
        by_id = {p.id: p for p in evidence}
        if role == "facts":
            system, schema = FACTS_SYSTEM, FACTS_SCHEMA
            user = (f"Question: {question}\nParts: {'; '.join(subqs)}\n\n"
                    f"Passages:\n{_fmt_passages(evidence, limit=550)}")
        elif role == "premise":
            system, schema = PREMISE_SYSTEM, PREMISE_SCHEMA
            user = f"Question: {question}\n\nPassages:\n{_fmt_passages(evidence, limit=450)}"
        elif role == "skeptic":
            if not claims:
                return
            seen, uniq = set(), []
            for c in claims:
                key = c["claim"].strip().lower()
                if key not in seen:
                    seen.add(key)
                    uniq.append(c)
            uniq = uniq[:12]
            cited = sorted({i for c in uniq for i in c.get("evidence", []) if i in by_id}, key=lambda x: int(x[1:]))[:12]
            claims_txt = "\n".join(f"{n}. {c['claim']} (cites {', '.join(c.get('evidence', []))})"
                                   for n, c in enumerate(uniq, 1))
            system, schema = SKEPTIC_SYSTEM, SKEPTIC_SCHEMA
            user = f"Passages:\n{_fmt_passages([by_id[i] for i in cited], limit=500)}\n\nClaims:\n{claims_txt}"
        else:
            return
        rec = {"role": role, "model": model}
        await send({"type": "role_start", "role": role, "model": model})
        try:
            ctx, par = self._lease_params(model, copies)
            async with self.pool.use(model, ctx, par) as url:
                res = await llm.chat_json(url, [{"role": "system", "content": system},
                                                {"role": "user", "content": user}], schema, max_tokens=700)
            data = res.data if isinstance(res.data, dict) else {}
            if role == "skeptic":
                flags = []
                for x in data.get("reviews", []):
                    try:
                        n = int(x.get("n", 0))
                    except (TypeError, ValueError):
                        continue
                    if 1 <= n <= len(uniq) and x.get("issue") not in (None, "none"):
                        flags.append({"claim": uniq[n - 1]["claim"], "issue": x["issue"], "fix": str(x.get("fix", ""))})
                data = {"flags": flags, "reviewed": len(uniq)}
            elif role == "premise" and data.get("premise_ok") is False and not _quote_found(
                    str(data.get("quote", "")), evidence):
                # small models cry "false premise" far too often (20 of 20 questions in the roles study):
                # only believe it when the contradicting sentence is really in the evidence
                data = {**data, "premise_ok": True, "overruled": "the quoted contradiction is not in the passages"}
            elif role == "facts":
                for f in data.get("facts", []):
                    if isinstance(f, dict):
                        f["evidence"] = [i for i in _evidence_ids(f.get("evidence", [])) if i in by_id]
            rec.update({"data": data, "seconds": round(res.seconds, 2)})
        except Exception as e:
            rec["error"] = f"{type(e).__name__}: {e}"[:300]
        out[role] = rec
        await send({"type": "role_result", **rec})

    @staticmethod
    def _roles_digest(out: dict) -> str:
        parts = []
        f = (out.get("facts") or {}).get("data")
        if f and f.get("facts"):
            lines = [f"- {x.get('fact', '')} {' '.join('[' + i + ']' for i in x.get('evidence', []))}"
                     for x in f["facts"] if isinstance(x, dict)]
            if f.get("not_to_confuse"):
                lines.append("Do not confuse with: " + "; ".join(map(str, f["not_to_confuse"])))
            parts.append("=== FACT SHEET (exact names and numbers from the evidence) ===\n" + "\n".join(lines))
        pr = (out.get("premise") or {}).get("data")
        if pr and pr.get("premise_ok") is False:
            parts.append(f"=== PREMISE CHECK ===\nThe question's premise looks wrong: {pr.get('problem', '')} "
                         f"{' '.join('[' + i + ']' for i in _evidence_ids(pr.get('evidence', [])))}")
        sk = (out.get("skeptic") or {}).get("data")
        if sk and sk.get("flags"):
            parts.append("=== SKEPTIC'S CAUTIONS ===\n" + "\n".join(
                f"- \"{x['claim']}\" -> {x['issue']}: {x['fix']}" for x in sk["flags"]))
        return ("\n\n".join(parts) + "\n\n") if parts else ""

    def _digest(self, subqs: list[str], results: list[dict]) -> str:
        parts = []
        for i, sq in enumerate(subqs):
            parts.append(f"## Sub-question {i + 1}: {sq}")
            for r in (r for r in results if r["subq"] == i):
                if r.get("error"):
                    parts.append(f"- {r['model']}: (failed)")
                    continue
                rate = r.get("support_rate")
                parts.append(f"- {r['model']} (support {'?' if rate is None else f'{rate:.0%}'}): {r.get('answer', '')}")
                for c in r.get("claims", []):
                    tag = c.get("verdict", "unchecked").upper()
                    parts.append(f"    * [{tag}] {c['claim']} {' '.join('[' + e + ']' for e in c['evidence'])}")
        return "\n".join(parts)

    @staticmethod
    def _cite(text: str, by_id: dict) -> tuple[str, list[dict]]:
        """Remove citations to ids that don't exist; list the sources actually cited."""
        cited: list[str] = []

        def fix(m: re.Match) -> str:
            ids = [x.strip() for x in re.split(r"[,\s]+", m.group(1)) if x.strip()]
            good = [i for i in ids if i in by_id]
            for g in good:
                if g not in cited:
                    cited.append(g)
            if not good:
                return ""
            lead = m.group(0)[0] if m.group(0)[0].isspace() else ""
            return lead + "[" + ", ".join(good) + "]"

        text = re.sub(r"\s?\[((?:E\d+[,\s]*)+)\]", fix, text)
        sources = [{"id": i, "title": by_id[i].title, "url": by_id[i].url, "snippet": by_id[i].text[:300]}
                   for i in cited]
        return text.strip(), sources

    @staticmethod
    def _stats(results: list[dict], t_start: float, stage_times: dict) -> dict:
        per_model: dict[str, dict] = {}
        for r in results:
            m = per_model.setdefault(r["model"], {"answers": 0, "failed": 0, "support": []})
            if r.get("error"):
                m["failed"] += 1
            else:
                m["answers"] += 1
                if r.get("support_rate") is not None:
                    m["support"].append(r["support_rate"])
        for m in per_model.values():
            s = m.pop("support")
            m["avg_support"] = round(sum(s) / len(s), 2) if s else None
        order = sorted(stage_times.items(), key=lambda kv: kv[1])
        end = time.time()
        stages = {name: round((order[i + 1][1] if i + 1 < len(order) else end) - t, 1)
                  for i, (name, t) in enumerate(order)}
        return {"total_seconds": round(end - t_start, 1), "stages": stages, "models": per_model, "mode": "research"}


_FILLER = re.compile(r"\b(19|20)\d\d\b|\b(new|newest|latest|recent|breakthrough|discovery|reported|study)\b", re.I)


def _blocked(domain: str, blocked) -> bool:
    """Benchmark runs block the sites where the answer keys are published (e.g. huggingface.co)."""
    return any(domain == b or domain.endswith("." + b) for b in (blocked or []))


def _simplify_query(q: str) -> str:
    """Drop years and news filler words that make search engines return nothing."""
    s = re.sub(r"\s+", " ", _FILLER.sub(" ", q)).strip()
    return s if len(s.split()) >= 2 else q


def _evidence_ids(raw) -> list[str]:
    """Pull E-ids out of whatever a small model wrote: 'E3', '[E3]', ':E3', 'see [E1], [E5'..."""
    if isinstance(raw, str):
        raw = [raw]
    out: list[str] = []
    for x in raw if isinstance(raw, list) else []:
        for m in re.findall(r"E\d+", str(x)):
            if m not in out:
                out.append(m)
    return out


def _clamp(x) -> float:
    try:
        return max(0.0, min(1.0, float(x)))
    except (TypeError, ValueError):
        return 0.5


def _save(trace: dict, save_dir=None):
    folder = save_dir or RUNS
    folder.mkdir(parents=True, exist_ok=True)
    name = dt.datetime.now().strftime("%Y%m%d-%H%M%S-%f")[:-3] + ".json"
    path = folder / name
    trace["trace_file"] = name
    tokens = llm.usage_snapshot()
    if tokens is not None and isinstance(trace.get("stats"), dict):
        trace["stats"]["tokens"] = tokens
    budget = llm.budget_snapshot()
    if budget is not None and isinstance(trace.get("stats"), dict):
        trace["stats"]["budget"] = budget  # the same dict is sent to the UI with the final answer
    path.write_text(json.dumps(trace, indent=2, default=str), encoding="utf-8")
    return path
