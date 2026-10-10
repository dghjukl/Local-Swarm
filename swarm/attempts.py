"""Several independent attempts at one question, then a vote (manager mode, `manager.attempts`).

The experts run showed most of the remaining headroom is variance: 71/100 FRAMES questions were
answered right by at least one manager setup but only 21 by all six, and a plain majority vote over
three setups' answers scored 56-57% vs 52% for the best single one. So instead of one deeper attempt,
run the manager loop a few times independently (different temperatures, optionally different worker
pairs) and let the coordinator compare the answers.

  manager.attempts:
    runs: [{temperature: 0.2}, {temperature: 0.7}, {temperature: 0.7, team: [Qwen3.5-4B, Qwen3.5-4B]}]
    adaptive: true    # stop after 2 attempts when they agree; run the rest only on disagreement

The vote: the coordinator reads each attempt's answer (and the facts it rests on), writes each one's
short final answer, says whether they all agree, and picks the best-supported answer (the majority,
unless the majority's support is clearly weaker). The chosen attempt's answer and citations are used
as they are, so every citation still points at a passage that attempt read.
"""
from __future__ import annotations

import copy
import time

from swarm import llm

VOTE_SYSTEM = """Several independent research attempts answered the same question. Compare them.
- For each attempt, write its short final answer (a name, number, date... or "no answer").
- same: true only if every attempt gives the same final answer (wording aside).
- best: the attempt whose answer is best supported. Prefer the answer most attempts agree on, unless
  their support is clearly weaker (a missing step, a wrong calculation, a fact no passage states).
  An attempt that answers is better than one that says it cannot tell, if its support is sound.
- reason: one or two sentences.
Output the JSON only."""


def vote_schema(n: int) -> dict:
    return {
        "type": "object",
        "properties": {
            "answers": {"type": "array", "minItems": n, "maxItems": n, "items": {
                "type": "object",
                "properties": {"attempt": {"type": "integer"}, "short": {"type": "string", "maxLength": 120}},
                "required": ["attempt", "short"]}},
            "same": {"type": "boolean"},
            "best": {"type": "integer", "enum": list(range(1, n + 1))},
            "reason": {"type": "string", "maxLength": 400},
        },
        "required": ["answers", "same", "best", "reason"],
    }


def _attempt_text(i: int, t: dict) -> str:
    notes = [n for n in (t.get("manager") or {}).get("notes", []) if n.get("status") != "unsupported"][:8]
    facts = "\n".join(f"   - {n.get('fact', '')}" for n in notes) or "   (none)"
    ans = " ".join(str((t.get("final") or {}).get("answer", "")).split())[:1500]
    return f"=== Attempt {i} ===\nAnswer: {ans}\nFacts its team found:\n{facts}"


async def run_attempts(sw, question: str, subqs: list[str], groups, evidence, send, stage, trace: dict,
                       t_start: float, stage_times: dict, today: str) -> dict:
    from swarm.manager import run_manager
    from swarm.orchestrator import _save
    ac = (sw.cfg.get("manager") or {}).get("attempts") or {}
    runs = list(ac.get("runs") or [{}, {}, {}])
    adaptive = bool(ac.get("adaptive", False))
    coord = sw.role("coordinator")
    base_cfg = sw.cfg

    async def quiet(e: dict) -> None:  # attempts don't stream their own answers
        if e.get("type") not in ("answer_delta", "final"):
            await send(e)

    attempts: list[dict] = []
    votes: list[dict] = []
    vote_seconds = 0.0

    async def vote() -> dict:
        nonlocal vote_seconds
        t0 = time.time()
        n = len(attempts)
        user = (f"Question: {question}\n\n" + "\n\n".join(_attempt_text(i + 1, t) for i, t in enumerate(attempts))
                + f"\n\nCompare the {n} attempts.")
        try:
            async with sw.pool.use(coord["model"], coord["ctx_per_slot"], coord["parallel"],
                                   pin=bool((sw.cfg.get("manager") or {}).get("pin_coordinator", True))) as url:
                r = await llm.chat_json(url, [{"role": "system", "content": VOTE_SYSTEM},
                                              {"role": "user", "content": user}], vote_schema(n),
                                        max_tokens=700, temperature=0.0)
            d = r.data if isinstance(r.data, dict) else {}
        except llm.BudgetExhausted:
            raise
        except Exception as e:
            d = {"error": type(e).__name__}
        vote_seconds += time.time() - t0
        best = d.get("best") if isinstance(d.get("best"), int) and 1 <= d.get("best") <= n else 1
        out = {"n": n, "same": bool(d.get("same")), "best": best, "reason": str(d.get("reason", ""))[:400],
               "short": [str(a.get("short", "")) for a in d.get("answers", []) if isinstance(a, dict)][:n],
               "error": d.get("error")}
        votes.append(out)
        return out

    try:
        for k, over in enumerate(runs):
            await stage("work", f"Attempt {k + 1} of {len(runs)}")
            cfg = copy.deepcopy(base_cfg)
            cfg["manager"] = {**(cfg.get("manager") or {}),
                              **{x: v for x, v in over.items() if x not in ("team",)}}
            if over.get("team"):
                cfg["workers"] = {**cfg["workers"], "team": list(over["team"])}
            sw.cfg = cfg
            t = dict(trace)  # the shared prefix (question, plan, evidence); each attempt adds its own parts
            t = await run_manager(sw, question, subqs, groups, evidence, quiet, stage, t, t_start, stage_times,
                                  today, publish=False)
            t["attempt_config"] = over
            attempts.append(t)
            if adaptive and len(attempts) == 2 and len(runs) > 2:
                v = await vote()
                if v["same"]:
                    break
    finally:
        sw.cfg = base_cfg

    v = await vote() if len(attempts) > 1 and (not votes or votes[-1]["n"] != len(attempts)) else (
        votes[-1] if votes else {"n": 1, "same": True, "best": 1, "reason": "one attempt", "short": []})
    chosen = attempts[v["best"] - 1]
    answer, sources = chosen["final"]["answer"], chosen["final"]["sources"]
    resolved = await resolve_if_stuck(sw, question, trace, attempts, v, ac.get("resolver"), stage)
    if resolved.get("used"):
        answer = resolved["answer"]
        sources = _all_sources(attempts)
    await send({"type": "answer_delta", "text": answer})
    trace.update({k: chosen[k] for k in ("team", "manager", "evidence_found", "worker_results", "final") if k in chosen})
    trace["attempts"] = [{"config": a.get("attempt_config"), "answer": a["final"]["answer"],
                          "sources": a["final"]["sources"], "stats": a.get("stats"),
                          "manager": a.get("manager")} for a in attempts]
    trace["votes"] = votes
    trace["resolver"] = resolved
    if resolved.get("used"):
        trace["final"] = {**(trace.get("final") or {}), "answer": answer, "sources": sources}
    stats = copy.deepcopy(chosen["stats"])
    stats["total_seconds"] = round(time.time() - t_start, 1)
    stats["attempts"] = {"runs": len(attempts), "planned": len(runs), "adaptive": adaptive, "chosen": v["best"],
                         "same": v["same"], "short": v["short"], "first2_same": votes[0]["same"] if votes else None,
                         "vote_seconds": round(vote_seconds, 1), "vote_errors": sum(1 for x in votes if x.get("error")),
                         "answers": [a["final"]["answer"] for a in attempts],
                         "vote_answer": chosen["final"]["answer"],
                         "resolver": {k: resolved.get(k) for k in ("used", "reason", "model", "seconds", "error", "skipped")}}
    trace["stats"] = stats
    path = _save(trace, getattr(sw, "_save_dir", None))
    await send({"type": "final", "answer": answer, "sources": sources, "stats": stats, "trace": path.name})
    return trace


# ------------------------------------------------------------------ escalation to a resolver
# Resolver tests J4 and J6 (2026-10-09/10): when the attempts disagree, a bigger model reading the research
# packet (evidence plus every attempt's answer and facts) picks or derives the answer better than the vote.
# On this PC only models that fit entirely on the GPU are safe (split GPU+RAM ones ran 16 GB RAM out).
#   manager.attempts.resolver: {model: Qwen3.8-27B, ctx: 16384, max_tokens: 1500, when: split,
#                               min_free_ram_mb: 1500}
# when: "split" = only when the attempts' short answers disagree; "stuck" = also when no attempt passed the
# trust check (only meaningful with manager.trust_check on).

def _all_sources(attempts: list[dict]) -> list[dict]:
    seen, out = set(), []
    for a in attempts:
        for s in (a.get("final") or {}).get("sources") or []:
            key = s.get("url") or s.get("id")
            if key in seen:
                continue
            seen.add(key)
            out.append(s)
    return out


async def resolve_if_stuck(sw, question: str, trace: dict, attempts: list[dict], vote: dict, rc: dict | None,
                           stage) -> dict:
    """Escalate a stuck question to the resolver model. Returns a record for the trace; `used` is True
    only when the resolver gave an answer that replaces the vote's."""
    if not rc or not rc.get("model") or len(attempts) < 2:
        return {"used": False, "skipped": "no resolver configured"}
    from swarm import procs
    from swarm.resolver_bench import RESOLVER_SYSTEM, build_packet, stuck_reason
    from swarm.selector_bench import short_answers
    view = {"question": question, "evidence": trace.get("evidence") or [],
            "evidence_found": [p for a in attempts for p in (a.get("evidence_found") or [])],
            "attempts": [{"answer": (a.get("final") or {}).get("answer", ""),
                          "sources": (a.get("final") or {}).get("sources") or [],
                          "manager": a.get("manager") or {}} for a in attempts],
            "votes": [vote]}
    shorts = short_answers(view["attempts"], view["votes"])
    ready = [((a.get("manager") or {}).get("trust") or [{}])[-1].get("ready") for a in attempts]
    if rc.get("when", "split") == "split":
        ready = [None] * len(ready)          # agreement alone decides
    reason = stuck_reason(shorts, ready)
    rec = {"used": False, "reason": reason, "model": rc["model"]}
    if reason is None:
        rec["skipped"] = "not stuck"
        return rec
    guard = int(rc.get("min_free_ram_mb", 1500))
    ram = procs.system_ram_mb()
    if guard and ram is not None and ram[0] < guard:
        rec["skipped"] = f"low RAM ({ram[0]} MB available)"
        return rec
    packet, info = build_packet(view, len(attempts), max_chars=int(rc.get("max_chars", 60000)))
    rec["packet"] = info
    await stage("work", f"Escalating to {rc['model']} ({reason})")
    t0 = time.time()
    try:
        await sw.pool.unload_all()           # the resolver runs alone on the GPU
        async with sw.pool.use(rc["model"], int(rc.get("ctx", 16384)), 1) as url:
            r = await llm.chat(url, [{"role": "system", "content": RESOLVER_SYSTEM},
                                     {"role": "user", "content": packet}],
                               max_tokens=int(rc.get("max_tokens", 1500)), temperature=0.2,
                               think=bool(rc.get("think", False)), timeout=float(rc.get("timeout", 600)), final=True)
        text = llm.strip_think(r.text).strip()
        if text:
            rec.update({"used": True, "answer": text})
        else:
            rec["error"] = "resolver gave no answer"
    except llm.BudgetExhausted:
        raise
    except Exception as e:  # keep the vote's answer
        rec["error"] = f"{type(e).__name__}: {e}"[:300]
    finally:
        try:
            await sw.pool.unload_all()       # free the GPU for the swarm again
        except Exception:
            pass
    rec["seconds"] = round(time.time() - t0, 1)
    return rec
