"""Manager mode: the coordinator works like a person directing two (or more) assistants.

How a question is answered (mode: manager):

  The coordinator starts with the same evidence a solo model reads. Then, cycle by cycle, it looks
  at the shared workspace (notes with their sources, and a log of every step so far) and decides
  ONE next step: which teammate, what task, and optionally a web search to run first. The
  teammate does the task on the passages it is given (fresh search results, or the most relevant
  passages already found) and posts notes to the workspace. If a teammate comes back empty or
  doubtful, the coordinator can give the same task to another teammate, or try a different search.
  It stops when it judges the workspace answers the question (or after `max_cycles`), then writes
  the answer from its own evidence plus the workspace.

  manager.reports: true -> teammates send a structured report (what the passages said, the answer,
  what's missing and why, a suggested next step and search, confidence and why) instead of a bare result.
  manager.expert: {model, ctx_per_slot, max_calls, followup_searches, auto} -> a bigger "expert" teammate
  (letter X) the coordinator can call when a step is stuck. It reads more passages and may run its own
  follow-up search. With auto, a blocked repeat of a failed step goes to the expert instead of being skipped.

  workers.team: [] or the coordinator itself -> the coordinator does every step itself (the
  "same loop, no team" baseline).

Everything (decisions, tasks, searches, results, who was picked) is kept in the trace.
"""
from __future__ import annotations

import asyncio
import re
import time

from swarm import evidence as ev
from swarm import llm
from swarm.notebook import Notebook, clean_citations

MANAGER_SYSTEM = """You lead a small research team answering one question. Today is {today}.
You already have some evidence passages. Your teammates can search the web and read sources for you,
one task at a time. Each turn, look at the workspace (facts found so far, with their sources) and the
steps taken, then decide the single most useful next step:
- Each task asks for ONE fact (one step), never the whole question. Questions often need several steps
  (find X, then a fact about X, then calculate): ask for the first missing piece, and use what comes
  back to ask for the next.
- Put a short web search in `search` when the fact is probably not in the sources found so far. Searches
  work best as 2-6 key words for that one fact (e.g. "Jane Eyre Dewey Decimal", "Mary Pierce born").
  Do not put guessed answers or numbers into a search.
- Never repeat a task or search that already came back NOT found: search a different angle (another
  name for the thing, a related page), or move on.
- If a teammate came back empty, vague or doubtful, you may give the same task to another teammate, or
  try a different search.
- Ask a teammate to double-check an important fact when only one source supports it.
{both_note}
- Set done = true only when the evidence and workspace together answer every part of the question
  (or further steps would not help). Then the other fields are ignored.
Output the JSON only."""

WORKER_SYSTEM = """You are a research assistant. Your team lead gives you one task about a larger question.
Do the task using ONLY the passages below.
- notes: the specific facts from the passages that the task needs (a name, number, date, place...),
  each a short self-contained sentence with the ids of the passages that state it, like ["E12"].
- result: your answer to the task in one or two sentences (or what is missing).
- found: true only if the passages really answer the task.
Never add facts from your own memory. Output the JSON only."""

WORKER_SCHEMA = {
    "type": "object",
    "properties": {
        "found": {"type": "boolean"},
        "result": {"type": "string", "maxLength": 500},
        "notes": {"type": "array", "maxItems": 6, "items": {
            "type": "object",
            "properties": {"fact": {"type": "string", "maxLength": 300},
                           "sources": {"type": "array", "items": {"type": "string"}, "maxItems": 4}},
            "required": ["fact", "sources"]}},
    },
    "required": ["found", "result", "notes"],
}

REPORT_SYSTEM = """You are a research assistant. Your team lead gives you one task about a larger question.
Do the task using ONLY the passages below, then report back so the lead can decide the next step well.
- said: what the relevant passages actually say about the task, briefly, with their ids like [E12]
  ("none of the passages mention X" is a useful report).
- notes: the specific facts the task needs (a name, number, date, place...), each a short self-contained
  sentence with the ids of the passages that state it, like ["E12"].
- result: your answer to the task in one or two sentences.
- found: true only if the passages really answer the task.
- missing: what the task still needs that the passages don't give ("" if nothing).
- why_missing: why (the passages are about something else, the page is cut off, the name is ambiguous,
  the sources disagree, ...).
- next_step: the step you would take next to get it (e.g. which page, name or angle to look up).
- next_search: a 2-6 word web search for that next step ("" if none is needed).
- confidence: high, medium or low; confidence_reason: why, in one sentence.
Saying "it is not in these passages" is far better than guessing. Never add facts from your own memory.
Output the JSON only."""

REPORT_SCHEMA = {
    "type": "object",
    "properties": {
        "said": {"type": "string", "maxLength": 700},
        "notes": WORKER_SCHEMA["properties"]["notes"],
        "result": {"type": "string", "maxLength": 500},
        "found": {"type": "boolean"},
        "missing": {"type": "string", "maxLength": 300},
        "why_missing": {"type": "string", "maxLength": 300},
        "next_step": {"type": "string", "maxLength": 250},
        "next_search": {"type": "string", "maxLength": 120},
        "confidence": {"type": "string", "enum": ["high", "medium", "low"]},
        "confidence_reason": {"type": "string", "maxLength": 200},
    },
    "required": ["said", "notes", "result", "found", "missing", "why_missing", "next_step", "next_search",
                 "confidence", "confidence_reason"],
}
REPORT_FIELDS = ("said", "missing", "why_missing", "next_step", "next_search", "confidence", "confidence_reason")

WRITE_SYSTEM = """You write the final answer to the user's question. Today is {today}.
You have your own evidence passages, the team's workspace (facts your teammates found by searching and
reading more sources, each with the passage ids that state it) and the extra passages they found.
- Answer the question directly in the first sentence (a name, number, date...), then the key steps.
- Multi-step questions: go through each step and say which fact answers it.
- Use only facts the passages state. If the question rests on something false, say so. If it truly
  cannot be determined, say so; otherwise give your best-supported answer.
- Cite passage ids after each fact, like [E3]. Only E-numbers are citations. Keep it under 200 words."""


STEP_BACK_DECIDE = """
How to think (write it in `thought`, under 120 words): first step back. What kind of question is this,
and what chain of facts does the answer need (e.g. identify X -> find a fact about X -> calculate)?
Which links of that chain are already established by the evidence or workspace, and which one is next?"""

STEP_BACK_WRITE = """
How to think: first step back and name the chain of facts the answer needs. Check each link against the
passages and the workspace (and redo any arithmetic), then give the answer."""


TRUST_SYSTEM = """You are the lead of a research team, and a partner who can be trusted. A partner who can be
trusted always tells the truth; to be believed, it shows its work; because it shows its work, it is reliable.
Before the answer is final, check it the way such a partner would. Today is {today}.
- answer: the answer you would give now, in one short line (or "cannot tell yet").
- steps: the chain of facts the answer rests on, in order. For each step:
  claim: one short fact or calculation;
  sources: the passage ids (like "E12") that state it - only ids that appear in the evidence or workspace;
  status: "supported" (a cited passage states it), "inferred" (it follows from earlier steps by reasoning or
  arithmetic), "unsupported" (no passage states it), or "conflict" (passages disagree about it).
- calc_expression: if the answer needs arithmetic (dates, ages, differences, totals), the calculation using only
  numbers and + - * / ( ), e.g. "2024 - 1987"; otherwise "". calc_result: the result you get, or "".
- parts_answered: true only if every part of the question is answered.
- gaps: what is missing, doubtful or in conflict, in one or two sentences ("" if nothing).
- ready: true only if every step is supported or inferred, nothing conflicts, the calculation is right and every
  part is answered.
Mark a step supported only if a passage really states it. Saying a step is unsupported is better than guessing.
Output the JSON only."""

CHARTER_WORKER = """You are a partner your team can trust. A partner tells the truth, so you report only what the
passages say, and say plainly when they don't say it. A partner shows its work, so every fact carries the ids
of the passages that state it. Because you do both, your team can rely on you: an honest "not found" is worth
more than a guess.

"""

CHARTER_LEAD = """You and your team are partners who can be trusted: tell the truth, show your work, and so be
reliable. Treat a fact as settled only when a passage states it; when the facts are uncertain, say so.

"""

TRUST_SCHEMA = {
    "type": "object",
    "properties": {
        "answer": {"type": "string", "maxLength": 200},
        "steps": {"type": "array", "maxItems": 8, "items": {
            "type": "object",
            "properties": {"claim": {"type": "string", "maxLength": 250},
                           "sources": {"type": "array", "maxItems": 4, "items": {"type": "string"}},
                           "status": {"type": "string", "enum": ["supported", "inferred", "unsupported", "conflict"]}},
            "required": ["claim", "sources", "status"]}},
        "calc_expression": {"type": "string", "maxLength": 150},
        "calc_result": {"type": "string", "maxLength": 40},
        "parts_answered": {"type": "boolean"},
        "gaps": {"type": "string", "maxLength": 400},
        "ready": {"type": "boolean"},
    },
    "required": ["answer", "steps", "calc_expression", "calc_result", "parts_answered", "gaps", "ready"],
}

TRUST_WRITE = """
You are a partner who can be trusted: tell the truth and show your work. A check of the answer's chain found
gaps (below). Do not state an unsupported or conflicting step as fact: say what is uncertain and why, and give
your best-supported answer."""


def check_calc(expr: str, result: str) -> bool | None:
    """Recompute a plain arithmetic expression. None when there is nothing (checkable) to check."""
    expr = (expr or "").replace(",", "").replace("\u00d7", "*").strip()
    if not expr or not re.fullmatch(r"[\d\s.+\-*/()]+", expr) or "**" in expr:
        return None
    m = re.search(r"-?\d+(?:\.\d+)?", (result or "").replace(",", ""))
    if not m:
        return None
    try:
        val = eval(compile(expr, "<calc>", "eval"), {"__builtins__": {}}, {})  # digits and + - * / ( ) only
    except Exception:
        return None
    got = float(m.group())
    return abs(val - got) <= max(0.005 * abs(val), 0.01)


def decision_schema(letters: list[str], thought_len: int = 300) -> dict:
    return {
        "type": "object",
        "properties": {
            "thought": {"type": "string", "maxLength": thought_len},
            "done": {"type": "boolean"},
            "worker": {"type": "string", "enum": letters},
            "task": {"type": "string", "maxLength": 300},
            "search": {"type": "string", "maxLength": 120},
        },
        "required": ["thought", "done", "worker", "task", "search"],
    }


def agree(results: list[dict]) -> bool:
    """Rough check that teammates' independent answers say the same thing: same numbers, or mostly
    the same words. Both must have found something."""
    found = [r for r in results if r["found"]]
    if len(found) < 2:
        return False
    nums = [set(re.findall(r"\d+(?:[.,]\d+)?", r["result"])) for r in found]
    if all(nums) and all(n == nums[0] for n in nums):
        return True
    words = [set(w for w in re.findall(r"[a-z0-9]+", r["result"].lower()) if len(w) > 3) for r in found]
    return all(words) and all(len(w & words[0]) / len(w | words[0]) >= 0.5 for w in words[1:])


def _similar(a: str, b: str, at: float = 0.6) -> bool:
    wa = set(re.findall(r"[a-z0-9]+", a.lower()))
    wb = set(re.findall(r"[a-z0-9]+", b.lower()))
    return bool(wa and wb) and len(wa & wb) / len(wa | wb) >= at


def _report(data: dict) -> dict:
    """The structured-report fields of a teammate's reply (cleaned, empty ones dropped)."""
    out = {}
    for f in REPORT_FIELDS:
        v = " ".join(str(data.get(f, "") or "").split())
        if v:
            out[f] = v
    return out


def _report_lines(rep_: dict, indent: str = "      ") -> str:
    lines = []
    if rep_.get("said"):
        lines.append(f"passages say: {rep_['said']}")
    if rep_.get("missing"):
        lines.append(f"missing: {rep_['missing']}" + (f" (why: {rep_['why_missing']})" if rep_.get("why_missing") else ""))
    if rep_.get("next_step") or rep_.get("next_search"):
        lines.append("suggests: " + rep_.get("next_step", "")
                     + (f' [search: "{rep_["next_search"]}"]' if rep_.get("next_search") else ""))
    if rep_.get("confidence"):
        lines.append(f"confidence: {rep_['confidence']}"
                     + (f" ({rep_['confidence_reason']})" if rep_.get("confidence_reason") else ""))
    return "".join(f"\n{indent}{x}" for x in lines)


async def run_manager(sw, question: str, subqs: list[str], groups: list[list[ev.Passage]],
                      evidence: list[ev.Passage], send, stage, trace: dict, t_start: float,
                      stage_times: dict, today: str, publish: bool = True) -> dict:
    """publish=False: one attempt among several (swarm/attempts.py) - return the trace without
    announcing the final answer or saving the trace."""
    from swarm.orchestrator import _fmt_passages, _save
    mc = sw.cfg.get("manager") or {}
    max_cycles = int(mc.get("max_cycles", 6))
    k = int(mc.get("passages_per_task", 6))
    pages = int(mc.get("pages_per_search", 3))
    temp = float(mc.get("temperature", 0.2))  # several attempts at one question use different temperatures
    charter = mc.get("charter") or {}  # the partner charter as a short nudge in prompts: {lead: bool, workers: bool}
    ch_lead = CHARTER_LEAD if charter.get("lead") else ""
    ch_work = CHARTER_WORKER if charter.get("workers") else ""
    reports = bool(mc.get("reports"))
    xc = mc.get("expert") or {}
    ex_model = xc.get("model") if xc.get("model") in sw.cards else None
    ex_ctx = int(xc.get("ctx_per_slot", 16384))
    ex_calls_max = int(xc.get("max_calls", 2)) if ex_model else 0
    ex_followups = int(xc.get("followup_searches", 1))
    ex_auto = bool(xc.get("auto", True))
    ex_label = f"{ex_model} (expert)" if ex_model else ""
    detail_steps = int(mc.get("report_detail_steps", 4))
    tc = mc.get("trust_check") or {}
    if tc is True:
        tc = {}
    trust_on = bool(mc.get("trust_check"))
    trust_rounds_max = int(tc.get("rounds", 2))         # checks that may send the team back to work
    trust_extra = int(tc.get("extra_cycles", 3))        # turns added (in total) to fix what a check finds   # full reports shown for the last N steps
    coord, w = sw.role("coordinator"), sw.role("workers")
    size = sw.cfg["research"]["passage_chars"]
    # a big coordinator (e.g. Gemma-4-12B) can't stay loaded beside the workers: it is not pinned, so the pool
    # unloads it while the workers run. worker_sets: [[0, 1], [2, 3]] runs the teammates (by position in the team)
    # one set after the other, each set side by side, so only one set sits on the GPU at a time.
    cpin = bool(mc.get("pin_coordinator", True))
    worker_sets = [[int(i) for i in grp] for grp in (mc.get("worker_sets") or [])]

    slots = sw.team_slots() if sw.team() else []
    if not slots:  # the coordinator does every step itself
        slots = [(f"{coord['model']} (itself)", coord["model"])]
    letters = [chr(ord("A") + i) for i in range(len(slots))]
    member = dict(zip(letters, slots))                     # letter -> (label, model)
    # dispatch "both": every task goes to every teammate at once (independent answers side by side)
    both = str(mc.get("dispatch", "one")) == "both" and len(slots) > 1
    copies = {m: sum(1 for _, x in slots if x == m) for _, m in slots}

    def server(model: str) -> tuple[int, int]:
        # a teammate that is the coordinator's own model shares the coordinator's server
        return (coord["ctx_per_slot"], coord["parallel"]) if model == coord["model"] else (w["ctx_per_slot"], 1)

    by_id = {p.id: p for p in evidence}
    known: list[ev.Passage] = list(evidence)               # every passage seen (ids given when first used)
    have_urls = {p.url for p in evidence}
    book = Notebook(set(by_id))
    log: list[dict] = []
    recs = {lab: {"model": lab, "base_model": m, "lab": sw.cards[m].lab, "subq": 0, "tasks": 0, "found": 0,
                  "searches": 0, "seconds": 0.0} for lab, m in slots}
    if ex_model:
        recs[ex_label] = {"model": ex_label, "base_model": ex_model, "lab": sw.cards[ex_model].lab, "subq": 0,
                          "tasks": 0, "found": 0, "searches": 0, "seconds": 0.0}
    trace["team"] = [lab for lab, _ in slots] + ([ex_label] if ex_model else [])
    await send({"type": "team", "coordinator": coord["model"], "verifier": None,
                "workers": [{"model": lab, "lab": sw.cards[m].lab, "lineage": sw.cards[m].lineage} for lab, m in slots]})

    both_note = ("- Every task goes to ALL your teammates at once; they answer independently (the `worker` field is\n"
                 f"  ignored{', except X for the expert' if ex_model else ''}). When their answers differ, check which\n"
                 "  one the passages support, or ask a follow-up.\n"
                 if both else "")
    if reports:
        both_note += ("- Teammates report what the passages said, what is missing and why, a suggested next step and\n"
                      "  search, and their confidence. Use the suggestions when they make sense; you decide.\n")
    if ex_model:
        both_note += (f"- X is an expert (a bigger, slower model). Give X a task only when a step is stuck: teammates\n"
                      f"  came back empty, disagree, or a search keeps failing. X reads more passages and can run one\n"
                      f"  follow-up search itself. It can be called at most {ex_calls_max} times per question.\n")
    if mc.get("verify"):
        both_note += ("- A fact-checker checks every fact that only ONE teammate found against its passages. Rely on\n"
                      "  verified facts and facts both teammates found; treat rejected facts as wrong.\n")
    parts = "\n".join(f"- {sq}" for sq in subqs)
    roster = "\n".join(f"- {L}: {member[L][1]}" for L in letters) + (
        f"\n- X: {ex_model} (expert, only when a step is stuck)" if ex_model else "")
    head = (f"User question: {question}\nParts to cover:\n{parts}\n\n=== Your evidence ===\n"
            f"{_fmt_passages(evidence, limit=900)}\n\n=== Teammates ===\n{roster}\n")  # stable prefix (cached)

    def give_ids(ps: list[ev.Passage]) -> None:
        for p in ps:
            if not p.id:
                p.id = f"E{len(by_id) + 1}"
                by_id[p.id] = p
                book.valid.add(p.id)

    def steps_text() -> str:
        if not log:
            return "(none yet)"
        out = []
        for i, s in enumerate(log):
            full = i >= len(log) - detail_steps   # full reports only for the most recent steps
            if s.get("trust"):
                out.append(f"{s['cycle']}. TRUST CHECK before finishing: NOT READY. {s['result']}\n"
                           "   Fix these gaps (or confirm them) before finishing.")
                continue
            if s.get("repeat"):
                out.append(f"{s['cycle']}. task: {s['task']} | search: \"{s['search']}\"\n   {s['result']}")
                continue
            line = f"{s['cycle']}. {'all teammates' if s.get('results') else s['worker'] + ' (' + s['model'] + ')'} task: {s['task']}"
            if s["search"]:
                line += f" | searched: \"{s['search']}\" ({s['new_passages']} new passages)"
            if s.get("results"):
                for x in s["results"]:
                    chk = (f" [fact-check: {x['verified']} verified, {x['rejected']} rejected, "
                           f"{x['confirmed_by_other']} also found by the other]" if "verified" in x else "")
                    line += f"\n   {x['worker']} ({'found' if x['found'] else 'NOT found'}){chk}: {x['result']}"
                    if full and x.get("report"):
                        line += _report_lines(x["report"])
                line += f"\n   -> the answers {'AGREE' if s['agree'] else 'DIFFER (check which one the passages support)'}"
            else:
                line += f"\n   result ({'found' if s['found'] else 'NOT found'}): {s['result']}"
                if s.get("expert_searches"):
                    line += f"\n   the expert also searched: " + ", ".join(f'"{q}"' for q in s["expert_searches"])
                if full and s.get("report"):
                    line += _report_lines(s["report"])
            out.append(line)
        return "\n".join(out)

    # ---------------- the loop
    await stage("work", f"Coordinator directing {len(slots)} teammate(s)")
    style = str(mc.get("coordinator_style", "plain"))     # plain | step_back | think
    verify_on = bool(mc.get("verify"))
    ver = sw.role("verifier")
    vstats = {"checked": 0, "supported": 0, "partial": 0, "unsupported": 0, "failed": 0}

    async def check_notes(notes: list) -> None:
        """The verifier model checks notes against the passages they cite, a few at a time."""
        from swarm.orchestrator import VERIFY_SCHEMA, VERIFY_SYSTEM
        if not notes:
            return
        try:
            async with sw.pool.use(ver["model"], ver["ctx_per_slot"], ver["parallel"]) as url:
                for i in range(0, len(notes), 4):
                    batch = notes[i:i + 4]
                    cited = sorted({c for n in batch for c in n.sources if c in by_id}, key=lambda x: int(x[1:]))
                    claims = "\n".join(f"{j + 1}. {n.fact}  (cites {', '.join(n.sources)})" for j, n in enumerate(batch))
                    user = f"Passages:\n{_fmt_passages([by_id[c] for c in cited], limit=900)}\n\nClaims to check:\n{claims}"
                    try:
                        res = await llm.chat_json(url, [{"role": "system", "content": VERIFY_SYSTEM},
                                                        {"role": "user", "content": user}], VERIFY_SCHEMA, max_tokens=600)
                    except llm.BudgetExhausted:
                        return
                    except Exception:
                        vstats["failed"] += len(batch)
                        continue
                    got = {}
                    for x in (res.data or {}).get("verdicts", []) if isinstance(res.data, dict) else []:
                        try:
                            got[int(x.get("n"))] = x
                        except (TypeError, ValueError, AttributeError):
                            pass
                    for j, n in enumerate(batch):
                        x = got.get(j + 1)
                        if x and x.get("verdict") in ("supported", "partial", "unsupported"):
                            n.status, n.reason = x["verdict"], str(x.get("reason", ""))[:200]
                            vstats["checked"] += 1
                            vstats[x["verdict"]] += 1
                        else:
                            vstats["failed"] += 1
        except llm.BudgetExhausted:
            return
        except Exception:
            vstats["failed"] += len(notes)
    think_tokens = int(mc.get("think_tokens", 1500))
    thought_len = 800 if style == "step_back" else 300
    sys_decide = ch_lead + MANAGER_SYSTEM.format(today=today, both_note=both_note) + (STEP_BACK_DECIDE if style == "step_back" else "")
    thinking = {"chars": 0, "calls": 0, "fallbacks": 0}

    async def decide(url: str, user: str, schema: dict):
        msgs = [{"role": "system", "content": sys_decide}, {"role": "user", "content": user}]
        if style == "think":
            # the model's own thinking (server started without --reasoning-budget 0 for it); JSON is
            # parsed from the reply after the thinking. If that fails, decide once without thinking.
            try:
                r = await llm.chat_json(url, llm.json_request(msgs, schema), schema, think=True, grammar=False,
                                        max_tokens=think_tokens + 500, temperature=temp, retries=0)
                thinking["chars"] += len(r.reasoning)
                thinking["calls"] += 1
                return r
            except llm.BudgetExhausted:
                raise
            except Exception:
                thinking["fallbacks"] += 1
        return await llm.chat_json(url, msgs, schema, max_tokens=900 if style == "step_back" else 400,
                                   temperature=temp)

    wstats = {"answers": 0, "said_found": 0, "found_unbacked": 0, "notes_offered": 0, "notes_kept": 0,
              "citations": 0, "bad_citations": 0}
    ex_used = 0
    ex_stats = {"calls": 0, "auto": 0, "found": 0, "searches": 0, "seconds": 0.0}
    w_tokens = int(mc.get("report_max_tokens", 1400)) if reports else 700
    w_system, w_schema = (REPORT_SYSTEM, REPORT_SCHEMA) if reports else (WORKER_SYSTEM, WORKER_SCHEMA)
    w_system = ch_work + w_system

    async def search_and_pick(task: str, search: str, kk: int, who: str) -> tuple[list, list]:
        """Run the search (if any), then pick the kk passages most relevant to the task: fresh results
        first, topped up with the most relevant passages already found."""
        nonlocal have_urls, known
        new = []
        if search:
            try:
                docs = await sw._gather([search], send, max_pages=pages, scholarly=False, skip_urls=have_urls)
            except Exception:
                docs = []
            have_urls |= {doc.url for doc in docs}
            new = ev.build_passages(docs, size=size)
            for p in new:
                p.id = ""
            known += new
            recs[who]["searches"] += 1
        picks = ev.select(new, [task, search, question], kk) if new else []
        if len(picks) < kk:
            seen = {(p.url, p.text[:120]) for p in picks}
            picks += [p for p in ev.select(known, [task, question], kk * 2)
                      if (p.url, p.text[:120]) not in seen][:kk - len(picks)]
        give_ids(picks)
        return new, picks

    def failed_search(q: str) -> bool:
        return any(not s["found"] and s.get("search") and s["search"].lower() == q.lower() for s in log)

    async def expert_step(cycle: int, task: str, search: str, auto: bool) -> dict:
        """The expert reads more passages; if it still lacks the fact and suggests a new search, that
        search is run and it reads again (up to `followup_searches` times)."""
        t0 = time.time()
        await send({"type": "stage_note", "message": f"turn {cycle}: expert {ex_model}: {task[:80]}"})
        new, picks = await search_and_pick(task, search, 2 * k, ex_label)
        n_new, read, searched = len(new), [p.id for p in picks], []
        got: list = []
        data: dict = {}
        earlier = ""
        for rnd in range(1 + ex_followups):
            xuser = (f"Larger question (for context): {question}\n\nYour task: {task}\n\n"
                     f"Facts the team already has:\n{book.render_for_writer(limit=10)}\n\n"
                     + (f"Your first look (at other passages): {earlier}\n\n" if earlier else "")
                     + f"Passages:\n{_fmt_passages(picks, limit=900)}")
            try:
                async with sw.pool.use(ex_model, ex_ctx, 1) as url:
                    r = await llm.chat_json(url, [{"role": "system", "content": ch_work + REPORT_SYSTEM},
                                                  {"role": "user", "content": xuser}], REPORT_SCHEMA,
                                            max_tokens=int(xc.get("max_tokens", 1600)), temperature=temp)
                data = r.data if isinstance(r.data, dict) else {}
            except llm.BudgetExhausted:
                raise
            except Exception as e:
                data = {"found": False, "result": f"(expert error: {type(e).__name__})", "notes": []}
                break
            for n in data.get("notes", []) or []:
                note = book.add(n.get("fact", ""), n.get("sources", []), ex_label, added_in=f"turn {cycle}") \
                    if isinstance(n, dict) else None
                if note is not None and all(note is not g for g in got):
                    got.append(note)
            if verify_on:
                await check_notes([n for n in got if n.status == "unchecked" and len(set(n.readers)) == 1])
            if (data.get("found") and any(n.status != "unsupported" for n in got)) or rnd == ex_followups:
                break
            q = " ".join(str(data.get("next_search", "") or "").split())[:120]
            if not q or failed_search(q) or q.lower() in (x.lower() for x in searched + [search]):
                break
            searched.append(q)
            ex_stats["searches"] += 1
            earlier = (f"result: {' '.join(str(data.get('result', '')).split())[:300]}; "
                       f"missing: {' '.join(str(data.get('missing', '')).split())[:200]}")
            new2, picks = await search_and_pick(task, q, 2 * k, ex_label)
            n_new += len(new2)
            read += [p.id for p in picks if p.id not in read]
        usable = [n for n in got if n.status != "unsupported"]
        fnd = bool(data.get("found")) and bool(usable)
        secs = round(time.time() - t0, 1)
        rec = recs[ex_label]
        rec["tasks"] += 1
        rec["found"] += int(fnd)
        rec["seconds"] = round(rec["seconds"] + secs, 1)
        ex_stats["calls"] += 1
        ex_stats["auto"] += int(auto)
        ex_stats["found"] += int(fnd)
        ex_stats["seconds"] = round(ex_stats["seconds"] + secs, 1)
        entry = {"cycle": cycle, "letter": "X", "worker": ex_label, "model": ex_model, "task": task,
                 "search": search, "found": fnd, "notes_added": len(got), "new_passages": n_new, "read": read,
                 "candidates": list(dict.fromkeys(p.url for p in new))[:40],
                 "read_urls": list(dict.fromkeys(p.url for p in picks)),
                 "result": " ".join(str(data.get("result", "")).split())[:300], "seconds": secs,
                 "reassigned": False, "expert": True, "auto": auto, "expert_searches": searched,
                 "report": _report(data)}
        if verify_on:
            entry["verified"] = sum(1 for n in got if n.status == "supported")
            entry["rejected"] = sum(1 for n in got if n.status == "unsupported")
        return entry

    # ---------------- trust check: before finishing, the coordinator lays out the chain the answer rests on;
    # citations and arithmetic are checked by code, "supported" steps by a second model.
    tstats = {"checks": 0, "said_ready": 0, "ready": 0, "sent_back": 0, "steps": 0, "said_supported": 0,
              "bad_citation": 0, "overclaimed": 0, "calc_checked": 0, "calc_wrong": 0, "unanswered_parts": 0,
              "failed": 0}
    trust_log: list[dict] = []
    tver = tc.get("verifier") or (sw.team()[0] if sw.team() else ver["model"])

    async def verify_steps(steps: list[dict]) -> list:
        """A second model checks the steps marked supported against the passages they cite."""
        from swarm.orchestrator import VERIFY_SCHEMA, VERIFY_SYSTEM
        out: list = [None] * len(steps)
        todo = [i for i, st in enumerate(steps) if st["status"] == "supported" and st["sources"]]
        if not todo or not tc.get("verify", True):
            return out
        ctx = w["ctx_per_slot"] if tver in sw.team() else 8192
        try:
            async with sw.pool.use(tver, ctx, 1) as url:
                for i in range(0, len(todo), 4):
                    batch = todo[i:i + 4]
                    cited = sorted({c for j in batch for c in steps[j]["sources"]}, key=lambda x: int(x[1:]))
                    claims = "\n".join(f"{n + 1}. {steps[j]['claim']}  (cites {', '.join(steps[j]['sources'])})"
                                       for n, j in enumerate(batch))
                    user = f"Passages:\n{_fmt_passages([by_id[c] for c in cited], limit=900)}\n\nClaims to check:\n{claims}"
                    try:
                        res = await llm.chat_json(url, [{"role": "system", "content": VERIFY_SYSTEM},
                                                        {"role": "user", "content": user}], VERIFY_SCHEMA, max_tokens=600)
                    except llm.BudgetExhausted:
                        raise
                    except Exception:
                        continue
                    for x in (res.data or {}).get("verdicts", []) if isinstance(res.data, dict) else []:
                        try:
                            n = int(x.get("n")) - 1
                        except (TypeError, ValueError, AttributeError):
                            continue
                        if 0 <= n < len(batch) and x.get("verdict") in ("supported", "partial", "unsupported"):
                            out[batch[n]] = x["verdict"]
        except llm.BudgetExhausted:
            raise
        except Exception:
            pass
        return out

    async def trust_check(cycle: int) -> dict:
        tstats["checks"] += 1
        user = (head + f"\n=== Shared workspace ===\n{book.render_for_writer(limit=30)}\n\n=== Steps so far ===\n"
                f"{steps_text()}\n\nCheck the answer before it is final.")
        msgs = [{"role": "system", "content": TRUST_SYSTEM.format(today=today)}, {"role": "user", "content": user}]
        d: dict = {}
        try:
            async with sw.pool.use(coord["model"], coord["ctx_per_slot"], coord["parallel"], pin=cpin) as url:
                if style == "think":
                    try:
                        r = await llm.chat_json(url, llm.json_request(msgs, TRUST_SCHEMA), TRUST_SCHEMA, think=True,
                                                grammar=False, max_tokens=think_tokens + 900, temperature=temp, retries=0)
                        thinking["chars"] += len(r.reasoning)
                        thinking["calls"] += 1
                    except llm.BudgetExhausted:
                        raise
                    except Exception:
                        thinking["fallbacks"] += 1
                        r = await llm.chat_json(url, msgs, TRUST_SCHEMA, max_tokens=1200, temperature=temp)
                else:
                    r = await llm.chat_json(url, msgs, TRUST_SCHEMA, max_tokens=1200, temperature=temp)
            d = r.data if isinstance(r.data, dict) else {}
        except llm.BudgetExhausted:
            raise
        except Exception as e:
            tstats["failed"] += 1
            rec = {"cycle": cycle, "error": type(e).__name__, "ready": True, "said_ready": None, "problems": []}
            trust_log.append(rec)
            return rec
        steps = []
        for st in d.get("steps", []) or []:
            if not isinstance(st, dict):
                continue
            srcs = [str(x).strip().strip("[]") for x in st.get("sources", []) or []]
            status = st.get("status") if st.get("status") in ("supported", "inferred", "unsupported", "conflict") \
                else "unsupported"
            steps.append({"claim": " ".join(str(st.get("claim", "")).split())[:250], "status": status,
                          "sources": [x for x in srcs if x in by_id], "bad_sources": [x for x in srcs if x not in by_id]})
        problems = []
        for st in steps:  # shown work: a "supported" step must cite a real passage
            tstats["steps"] += 1
            if st["status"] == "supported":
                tstats["said_supported"] += 1
                if not st["sources"]:
                    tstats["bad_citation"] += 1
                    st["check"] = "no valid citation"
                    problems.append(f"no real passage cited for: {st['claim']}")
        verdicts = await verify_steps(steps)
        for st, v in zip(steps, verdicts):
            if v:
                st["verifier"] = v
            if v == "unsupported":
                tstats["overclaimed"] += 1
                problems.append(f"the cited passages don't state: {st['claim']}")
        for st in steps:
            if st["status"] in ("unsupported", "conflict"):
                problems.append(f"{st['status']}: {st['claim']}")
        calc_ok = check_calc(str(d.get("calc_expression", "")), str(d.get("calc_result", "")))
        if calc_ok is not None:
            tstats["calc_checked"] += 1
        if calc_ok is False:
            tstats["calc_wrong"] += 1
            problems.append(f"the calculation {d.get('calc_expression')} = {d.get('calc_result')} is wrong")
        if d.get("parts_answered") is False:
            tstats["unanswered_parts"] += 1
            problems.append("not every part of the question is answered")
        if not steps:
            problems.append("no chain of facts was given")
        said = bool(d.get("ready"))
        tstats["said_ready"] += int(said)
        ready = said and not problems
        tstats["ready"] += int(ready)
        gaps = " ".join(str(d.get("gaps", "")).split())[:400]
        rec = {"cycle": cycle, "answer": " ".join(str(d.get("answer", "")).split())[:200], "steps": steps,
               "calc": {"expression": d.get("calc_expression", ""), "result": d.get("calc_result", ""), "ok": calc_ok},
               "parts_answered": d.get("parts_answered"), "gaps": gaps, "said_ready": said, "ready": ready,
               "problems": problems[:8]}
        trust_log.append(rec)
        return rec

    trust_rounds = 0
    limit = max_cycles
    cycle = 0
    while cycle < limit:
        cycle += 1
        can_x = bool(ex_model) and ex_used < ex_calls_max
        schema = decision_schema(letters + (["X"] if can_x else []), thought_len)
        user = (head + f"\n=== Shared workspace ===\n{book.render_for_writer(limit=30)}\n\n=== Steps so far ===\n"
                f"{steps_text()}\n\nThis is turn {cycle} of at most {limit}."
                + (f" Expert (X) calls left: {ex_calls_max - ex_used}." if ex_model else "")
                + " Decide the next step.")
        try:
            async with sw.pool.use(coord["model"], coord["ctx_per_slot"], coord["parallel"], pin=cpin) as url:
                res = await decide(url, user, schema)
        except llm.BudgetExhausted:
            break
        except Exception as e:
            log.append({"cycle": cycle, "worker": "-", "model": "-", "task": "", "search": "", "found": False,
                        "result": f"coordinator error: {type(e).__name__}"[:200], "new_passages": 0, "seconds": 0})
            break
        d = res.data if isinstance(res.data, dict) else {}
        if d.get("done") or not str(d.get("task", "")).strip():
            if trust_on and trust_rounds < trust_rounds_max:
                try:
                    tr = await trust_check(cycle)
                except llm.BudgetExhausted:
                    break
                room = max_cycles + trust_extra - limit
                if not tr["ready"] and tr.get("problems") and (cycle < limit or room > 0):
                    trust_rounds += 1
                    tstats["sent_back"] += 1
                    if limit - cycle < 2 and room > 0:  # make room to fix it
                        limit += min(room, max(1, -(-trust_extra // max(1, trust_rounds_max))))
                    log.append({"cycle": cycle, "worker": "-", "model": "-", "task": "(trust check)", "search": "",
                                "found": False, "trust": True, "new_passages": 0, "seconds": 0,
                                "result": ("Gaps: " + "; ".join(tr["problems"][:5])
                                           + (f" | lead's note: {tr['gaps']}" if tr.get("gaps") else ""))[:700]})
                    continue
            trace.setdefault("manager_stop", {"cycle": cycle, "thought": str(d.get("thought", ""))[:300]})
            break
        L = d.get("worker") if d.get("worker") in member else letters[0]
        want_x = can_x and d.get("worker") == "X"
        task, search = str(d["task"]).strip(), str(d.get("search", "")).strip()
        # did the coordinator take the last step's suggestion (structured reports)?
        prev_real = next((s for s in reversed(log) if not s.get("repeat")), None)
        sugs = [x.get("report") or {} for x in ((prev_real.get("results") or [prev_real]) if prev_real else [])]
        suggested = any(x.get("next_search") or x.get("next_step") for x in sugs)
        followed = suggested and any(
            (search and x.get("next_search") and _similar(search, x["next_search"], 0.5))
            or (x.get("next_step") and _similar(task, x["next_step"], 0.4)) for x in sugs)
        rep = next((s for s in log if not s["found"] and s["worker"] != "-" and
                    ((str(d.get("search", "")).strip().lower() == s["search"].lower() and s["search"])
                     or (not str(d.get("search", "")).strip() and _similar(s["task"], str(d["task"]))))), None)
        auto = False
        if rep and can_x and ex_auto and not want_x:  # stuck on a failed step: hand it to the expert
            want_x, auto = True, True
        if want_x:
            if rep and search and failed_search(search):
                search = ""  # don't rerun the search that already failed; the expert may try its own
            ex_used += 1
            try:
                entry = await expert_step(cycle, task, search, auto)
            except llm.BudgetExhausted:
                break
            entry.update({"thought": str(d.get("thought", ""))[:300], "suggested": suggested, "followed": followed})
            log.append(entry)
            continue
        if rep:  # the same step that already failed: don't spend a search on it, tell the coordinator
            log.append({"cycle": cycle, "letter": L, "worker": "-", "model": "-", "task": str(d["task"])[:300],
                        "search": str(d.get("search", ""))[:120], "found": False, "notes_added": 0,
                        "result": f"SKIPPED: same as turn {rep['cycle']}, which found nothing. Choose a different step.",
                        "new_passages": 0, "read": [], "seconds": 0, "reassigned": False, "repeat": True})
            continue
        label, model = member[L]
        t0 = time.time()
        await send({"type": "stage_note", "message": f"turn {cycle}: {label}: {task[:80]}"})
        new, picks = await search_and_pick(task, search, k, label)
        notes_txt = book.render_for_writer(limit=10)
        wuser = (f"Larger question (for context): {question}\n\nYour task: {task}\n\n"
                 f"Facts the team already has:\n{notes_txt}\n\nPassages:\n{_fmt_passages(picks, limit=900)}")

        async def do_task(lab: str, mod: str) -> dict:
            ctx, par = server(mod)
            if both and mod != coord["model"]:
                par = copies[mod]  # copies of one model answer side by side on one server
            try:
                async with sw.pool.use(mod, ctx, par, pin=(cpin and mod == coord["model"])) as url:
                    wres = await llm.chat_json(url, [{"role": "system", "content": w_system},
                                                     {"role": "user", "content": wuser}], w_schema,
                                               max_tokens=w_tokens, temperature=temp)
                return wres.data if isinstance(wres.data, dict) else {}
            except llm.BudgetExhausted:
                raise
            except Exception as e:
                return {"found": False, "result": f"(teammate error: {type(e).__name__})", "notes": []}

        who = [member[x] for x in letters] if both else [(label, model)]
        try:
            if both and worker_sets:
                # the sets answer one after the other; teammates inside a set answer side by side
                order = [[i for i in grp if 0 <= i < len(who)] for grp in worker_sets]
                order = [g for g in order if g]
                rest = [i for i in range(len(who)) if all(i not in g for g in order)]
                if rest:
                    order.append(rest)
                got_out: dict[int, dict] = {}
                for grp in order:
                    part = await asyncio.gather(*(do_task(*who[i]) for i in grp))
                    got_out.update(dict(zip(grp, part)))
                outs = [got_out[i] for i in range(len(who))]
            else:
                outs = await asyncio.gather(*(do_task(lab, mod) for lab, mod in who))
        except llm.BudgetExhausted:
            break
        secs = round(time.time() - t0, 1)
        results = []
        mine: dict[str, list] = {}
        for (lab, mod), data in zip(who, outs):  # merge in team order: notes found by both get 2 readers
            got = []
            wstats["answers"] += 1
            wstats["said_found"] += bool(data.get("found"))
            for n in data.get("notes", []) or []:
                if isinstance(n, dict):  # honesty counters: notes offered, and citations to passages that don't exist
                    wstats["notes_offered"] += 1
                    cited = re.findall(r"E\d+", " ".join(map(str, n.get("sources") or [])))
                    wstats["citations"] += len(cited)
                    wstats["bad_citations"] += sum(1 for c in cited if c not in book.valid)
                note = book.add(n.get("fact", ""), n.get("sources", []), lab, added_in=f"turn {cycle}") \
                    if isinstance(n, dict) else None
                if note is not None and all(note is not g for g in got):
                    got.append(note)
            mine[lab] = got
        if verify_on:  # fact-check the notes only ONE teammate found (two independent finds = agreement)
            seen_ids, single = set(), []
            for n in (x for g in mine.values() for x in g):
                if n.id not in seen_ids and n.status == "unchecked" and len(set(n.readers)) == 1:
                    seen_ids.add(n.id)
                    single.append(n)
            await check_notes(single)
        for (lab, mod), data in zip(who, outs):
            got = mine[lab]
            usable = [n for n in got if n.status != "unsupported"]
            fnd = bool(data.get("found")) and bool(usable)
            wstats["notes_kept"] += len(got)
            wstats["found_unbacked"] += bool(data.get("found")) and not usable  # said found, nothing usable to show
            res_ = {"worker": lab, "model": mod, "found": fnd, "notes_added": len(got),
                    "result": " ".join(str(data.get("result", "")).split())[:300]}
            if reports:
                res_["report"] = _report(data)
            if verify_on:
                res_["verified"] = sum(1 for n in got if n.status == "supported")
                res_["rejected"] = sum(1 for n in got if n.status == "unsupported")
                res_["confirmed_by_other"] = sum(1 for n in got if len(set(n.readers)) > 1)
            results.append(res_)
            r = recs[lab]
            r["tasks"] += 1
            r["found"] += int(fnd)
            r["seconds"] = round(r["seconds"] + secs, 1)
        prev = log[-1] if log else None
        entry = {"cycle": cycle, "letter": "both" if both else L, "worker": "both" if both else label,
                 "model": "+".join(m for _, m in who), "task": task, "search": search,
                 "thought": str(d.get("thought", ""))[:300], "found": any(x["found"] for x in results),
                 "result": results[0]["result"], "notes_added": sum(x["notes_added"] for x in results),
                 "new_passages": len(new), "read": [p.id for p in picks], "seconds": secs,
                 # the pages this search brought in (for checking whether the right page was found but not picked)
                 "candidates": list(dict.fromkeys(p.url for p in new))[:40],
                 "read_urls": list(dict.fromkeys(p.url for p in picks)),
                 "reassigned": bool(not both and prev and prev["worker"] != label and _similar(prev["task"], task)),
                 "suggested": suggested, "followed": followed}
        if reports and not both:
            entry["report"] = results[0].get("report", {})
        if both:
            entry["results"] = results
            entry["agree"] = agree(results)
        log.append(entry)

    # a final check (unless the last thing that happened was a check) tells the writer what is still shaky
    final_trust = trust_log[-1] if trust_log else None
    if trust_on and (not trust_log or any(not x.get("trust") and x["cycle"] > trust_log[-1]["cycle"] for x in log)):
        try:
            final_trust = await trust_check(cycle)
        except llm.BudgetExhausted:
            pass

    # ---------------- write the answer: own evidence + workspace + passages the team found
    await stage("synthesize", "Writing the answer from the evidence and the workspace")
    own = {p.id for p in evidence}
    good = [n for n in book.ordered() if n.status != "unsupported"]
    extra = [i for i in dict.fromkeys(s for n in good[:20] for s in n.sources) if i not in own][:10]
    wuser = (f"User question: {question}\nParts to cover:\n{parts}\n\n=== Your evidence ===\n"
             f"{_fmt_passages(evidence, limit=900)}\n\n=== Team workspace ===\n{book.render_for_writer(limit=30)}"
             + (f"\n\n=== Passages your teammates found ===\n{_fmt_passages([by_id[i] for i in extra], limit=900)}"
                if extra else ""))

    async def delta(txt: str) -> None:
        await send({"type": "answer_delta", "text": txt})

    async with sw.pool.use(coord["model"], coord["ctx_per_slot"], coord["parallel"], pin=cpin) as url:
        shaky = trust_on and final_trust and final_trust.get("problems")
        wmsgs = [{"role": "system", "content": ch_lead + WRITE_SYSTEM.format(today=today)
                  + (STEP_BACK_WRITE if style == "step_back" else "") + (TRUST_WRITE if shaky else "")},
                 {"role": "user", "content": wuser + (
                     f"\n\n=== Check of the answer's chain ===\nStill uncertain: {'; '.join(final_trust['problems'][:6])}"
                     + (f"\nLead's note: {final_trust['gaps']}" if final_trust.get("gaps") else "") if shaky else "")}]
        final = await llm.chat(url, wmsgs, max_tokens=900 + (think_tokens if style == "think" else 0),
                               temperature=temp, on_delta=delta, final=True, think=(style == "think"))
        if style == "think":
            thinking["chars"] += len(final.reasoning)
            thinking["calls"] += 1
    answer, sources = sw._cite(clean_citations(final.text), by_id)
    trace["manager"] = {"log": log, "notes": book.to_list(), "extra_cited": extra, "trust": trust_log,
                        "config": {"max_cycles": max_cycles, "passages_per_task": k, "pages_per_search": pages,
                   "reports": reports, "expert": xc if ex_model else None}}
    trace["evidence_found"] = [by_id[i].to_dict() for i in by_id if i not in own]
    trace["final"] = {"answer": answer, "sources": sources, "seconds": round(final.seconds, 2)}
    results = []
    for lab in recs:
        rec = recs[lab]
        mine = [n for n in book.notes if lab in n.readers]
        rec["claims"] = [{"claim": n.fact, "evidence": n.sources, "verdict": n.status} for n in mine]
        rec["support_rate"] = None
        results.append(rec)
    trace["worker_results"] = results
    stats = sw._stats(results, t_start, stage_times)
    stats["mode"] = "manager"
    stats["manager"] = {"turns": len(log), "searches": sum(1 for s in log if s["search"] and not s.get("repeat")),
                        "found": sum(1 for s in log if s["found"]),
                        "reassigned": sum(1 for s in log if s.get("reassigned")),
                        "repeats_blocked": sum(1 for s in log if s.get("repeat")),
                        "dispatch": "both" if both else "one",
                        "charter": {k: bool(charter.get(k)) for k in ("lead", "workers")},
                        **{f"worker_{k}": v for k, v in wstats.items()},
                        "coordinator_style": style, "thinking_chars": thinking["chars"],
                        "verify": verify_on, **{f"verify_{k}": v for k, v in vstats.items()},
                        "thinking_calls": thinking["calls"], "thinking_fallbacks": thinking["fallbacks"],
                        "both_found": sum(1 for s in log if s.get("results") and all(x["found"] for x in s["results"])),
                        "one_found": sum(1 for s in log if s.get("results") and sum(x["found"] for x in s["results"]) == 1),
                        "agree": sum(1 for s in log if s.get("agree")),
                        "picks": {L: sum(1 for s in log if s.get("letter") == L) for L in letters + (["X"] if ex_model else [])},
                        "new_passages": len(by_id) - len(own), "notes": len(book.notes),
                        "stopped_by_coordinator": "manager_stop" in trace,
                        "reports": reports,
                        "suggested_turns": sum(1 for s in log if s.get("suggested")),
                        "followed": sum(1 for s in log if s.get("followed")),
                        "followed_found": sum(1 for s in log if s.get("followed") and s["found"]),
                        "confidence": {c: sum(1 for s in log for x in (s.get("results") or [s])
                                              if (x.get("report") or {}).get("confidence") == c)
                                       for c in ("high", "medium", "low")},
                        "expert": ex_model, **{f"expert_{k_}": v for k_, v in ex_stats.items()},
                        "trust_check": trust_on, **{f"trust_{k_}": v for k_, v in tstats.items()},
                        "trust_final_ready": (final_trust or {}).get("ready") if trust_on else None,
                        "trust_final_said_ready": (final_trust or {}).get("said_ready") if trust_on else None}
    trace["stats"] = stats
    if not publish:
        return trace
    path = _save(trace, getattr(sw, "_save_dir", None))
    await send({"type": "final", "answer": answer, "sources": sources, "stats": stats, "trace": path.name})
    return trace
