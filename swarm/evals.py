"""Evaluation harness: run the test questions through real model configurations, record
everything, grade every answer with a local judge model, and write a report.

    python -m swarm.evals                         # all questions x default configs
    python -m swarm.evals --configs swarm-mixed --questions lz-2026 --repeats 2
    python -m swarm.evals --reuse-evidence runtime/evals/20260926-1700   # identical sources as a past run
    python -m swarm.evals --regrade runtime/evals/20260926-1700          # judge + report again, no new runs

Output folder runtime/evals/<timestamp>/:
    evidence/<question>.json   plan + fetched sources shared by every configuration
    traces/*.json              full swarm trace of every run (same format as runtime/runs)
    results.jsonl              one line per run: answer, timings, VRAM, worker stats, grade
    events.log                 model loads/unloads, stages, warnings, errors
    report.html / report.md    leaderboard, per-question grades, per-model stats, judge reasoning
"""
from __future__ import annotations

import argparse
import asyncio
import copy
import hashlib
import datetime as dt
import html
import json
import re
import socket
import statistics
import sys
import time
import webbrowser
from pathlib import Path

import yaml

from swarm import benchmarks, llm, procs
from swarm.config import _merge, load_config
from swarm.orchestrator import Swarm
from swarm.paths import REPO, RUNTIME, repo_path
from swarm.pool import ModelPool
from swarm.registry import scan_models
from swarm.tools import DirectResearch, ResearchMCP, research_mcp_available

JUDGE_SYSTEM = """You grade an answer to a research question against a checklist written by an expert
who knows the correct answer.
For each MUST item decide:
  "met"      the answer clearly states it (wording may differ, meaning must match)
  "partial"  the answer gets part of it, or states it vaguely
  "missing"  the answer does not state it, or states something different
For each MUST NOT item decide:
  "violated" the answer itself plainly makes that error
  "ok"       it does not
A MUST NOT item is "violated" ONLY if a sentence in the answer states the error. Hedged or correctly
limited statements ("may", "suggests", "in mice", "hypothesized", "not yet tested in patients") are "ok",
and so is a related but different claim. When you mark "violated", copy that exact sentence from the
answer into "quote".
Grade only what the answer says. Be strict about numbers, names and certainty
(e.g. "may explain" is not the same as "explains").
Grade each item on its main point only. Do not demand extra specifics the item does not ask for:
an item met in substance with different wording, or with a correct but less detailed phrasing, is "met".
Keep reasons short."""

JUDGE_SCHEMA = {
    "type": "object",
    "properties": {
        "must": {"type": "array", "items": {"type": "object", "properties": {
            "n": {"type": "integer"}, "status": {"type": "string", "enum": ["met", "partial", "missing"]},
            "reason": {"type": "string"}}, "required": ["n", "status", "reason"]}},
        "must_not": {"type": "array", "items": {"type": "object", "properties": {
            "n": {"type": "integer"}, "status": {"type": "string", "enum": ["ok", "violated"]},
            "quote": {"type": "string"}, "reason": {"type": "string"}}, "required": ["n", "status", "reason"]}},
    },
    "required": ["must", "must_not"],
}

# Established benchmarks (FRAMES, GAIA) come with one reference answer instead of a checklist.
REF_JUDGE_SYSTEM = """You check a response to a question against the reference answer, which is correct.
1. Copy the response's final answer to the question into "extracted_answer": only the answer itself
   (a name, number, date, short phrase or list), in the format the question asks for, with no
   explanation. Use "" if the response gives no answer.
2. Decide the verdict:
   "correct"        the response's final answer means the same as the reference answer (spelling,
                    wording, rounding or units may differ only as far as the question allows)
   "incorrect"      it gives a different answer, or several answers that disagree
   "not_attempted"  it gives no answer (e.g. says it could not find out)
Judge only the final answer, not the reasoning around it. Keep the reason short."""

REF_JUDGE_SCHEMA = {
    "type": "object",
    "properties": {"extracted_answer": {"type": "string"},
                   "verdict": {"type": "string", "enum": ["correct", "incorrect", "not_attempted"]},
                   "reason": {"type": "string"}},
    "required": ["extracted_answer", "verdict", "reason"],
}

MUST_POINTS = {"met": 1.0, "partial": 0.5, "missing": 0.0}
ESSENTIAL_WEIGHT, DETAIL_WEIGHT = 2, 1
VIOLATION_PENALTY = 0.25


def _item(x) -> str:
    """Rubric items are plain text; YAML turns 'a: b' into a dict, so flatten that back."""
    if isinstance(x, dict):
        return "; ".join(f"{k}: {v}" for k, v in x.items())
    return str(x)


def letter(score: float | None) -> str:
    if score is None:
        return "–"
    for cut, g in ((0.9, "A"), (0.75, "B"), (0.6, "C"), (0.4, "D")):
        if score >= cut:
            return g
    return "F"


# ---------------------------------------------------------------------- helpers

class Recorder:
    """Console + events.log output, and peak GPU memory sampling."""

    def __init__(self, out: Path):
        self.log = open(out / "events.log", "a", encoding="utf-8")
        self.peak_mb = 0
        self.peak_ram_mb = 0      # system RAM in use (all programs), MB
        self.min_free_ram_mb = None
        self._task: asyncio.Task | None = None

    def say(self, msg: str) -> None:
        line = f"{dt.datetime.now():%H:%M:%S}  {msg}"
        print(line, flush=True)
        self.log.write(line + "\n")
        self.log.flush()

    async def emit(self, e: dict) -> None:
        t = e.get("type")
        if t == "model":
            if e["event"] == "ready":
                self.say(f"    model {e['model']} ready in {e['seconds']}s ({e['vram_mb'] / 1024:.1f} GB)")
            elif e["event"] == "failed":
                self.say(f"    model {e['model']} FAILED to load: {e.get('error', '')[:200]}")
            elif e["event"] == "unloaded":
                self.log.write(f"    unloaded {e['model']} ({e.get('reason')})\n")
        elif t in ("warning", "error"):
            self.say(f"    {t}: {e.get('message', '')[:300]}")
        elif t == "stage":
            self.log.write(f"    stage {e['stage']} at {e.get('t')}s\n")
        elif t == "search":
            n = len(e.get("results") or [])
            msg = f"    search [{e.get('backend')}] '{e.get('query', '')[:60]}': {n} results"
            if e.get("error"):
                msg += f" ({e['error'][:120]})"
            (self.say if e.get("error") else self.log.write)(msg if e.get("error") else msg + "\n")
        elif t == "worker_result" and e.get("error"):
            self.say(f"    worker {e['model']} q{e['subq'] + 1} failed: {e['error'][:160]}")

    async def _sample(self) -> None:
        warned = 0.0
        while True:
            await self.sample_once()
            ram = await asyncio.to_thread(procs.system_ram_mb)
            if ram and ram[0] < 1200 and time.time() - warned > 60:
                warned = time.time()
                self.say(f"    WARNING: system RAM almost full ({ram[0]} MB free) - close other programs")
            await asyncio.sleep(1.0)

    def start(self) -> None:
        self._task = asyncio.create_task(self._sample())

    async def reset_peak(self) -> None:
        self.peak_mb = 0
        self.peak_ram_mb = 0
        self.min_free_ram_mb = None
        await self.sample_once()

    async def sample_once(self) -> None:
        g = await asyncio.to_thread(procs.gpu_memory_mb)
        if g:
            self.peak_mb = max(self.peak_mb, g[0])
        ram = await asyncio.to_thread(procs.system_ram_mb)
        if ram:
            self.peak_ram_mb = max(self.peak_ram_mb, ram[1] - ram[0])
            self.min_free_ram_mb = ram[0] if self.min_free_ram_mb is None else min(self.min_free_ram_mb, ram[0])

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
        self.log.close()


def swarm_already_running(cfg: dict) -> bool:
    with socket.socket() as s:
        s.settimeout(0.5)
        return s.connect_ex((cfg["server"]["host"], int(cfg["server"]["port"]))) == 0


def load_set(path: Path, only: list[str] | None = None) -> tuple[list[dict], dict]:
    """A question file is either a list of questions or {meta: {...}, questions: [...]} (benchmarks)."""
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or []
    meta = {}
    if isinstance(data, dict):
        meta, data = data.get("meta") or {}, data.get("questions") or []
    if only:
        data = [q for q in data if q["id"] in only]
    return data, meta


def load_questions(path: Path, only: list[str] | None) -> list[dict]:
    return load_set(path, only)[0]


def expand_configs(econf: dict) -> dict:
    """Turn `matrices` into ordinary configs plus a group of the same name.

    A matrix is a template filled in once per model, e.g.
      solo-tournament: {name: "solo {model}", description: "...", models: [...],
                        overrides: {mode: solo, coordinator: {model: "{model}"}}}

    A matrix with BOTH `models` and `values` is a grid: one config per (model, value) pair,
    model-major (all values for the first model, then the next model).
    """
    def fill(v, model, value):
        if isinstance(v, str):
            return v.replace("{model}", model).replace("{value}", value)
        if isinstance(v, dict):
            return {k: fill(x, model, value) for k, x in v.items()}
        if isinstance(v, list):
            return [fill(x, model, value) for x in v]
        return v
    econf.setdefault("configs", {})
    econf.setdefault("groups", {})
    for mname, m in (econf.get("matrices") or {}).items():
        names = []
        if m.get("models") and m.get("values"):
            pairs = [(mo, va) for mo in m["models"] for va in m["values"]]
        else:
            pairs = [(x, x) for x in m.get("values", m.get("models", []))]
        for model, value in pairs:
            name = fill(m.get("name", mname + " {model}"), model, value)
            econf["configs"][name] = {"description": fill(m.get("description", ""), model, value),
                                      "overrides": fill(m.get("overrides") or {}, model, value)}
            names.append(name)
        econf["groups"][mname] = names
    # groups may contain other groups
    def flat(n, seen=()):
        if n in econf["groups"] and n not in seen:
            return [x for g in econf["groups"][n] for x in flat(g, seen + (n,))]
        return [n]
    econf["groups"] = {g: list(dict.fromkeys(flat(g))) for g in econf["groups"]}
    return econf


def _in_answer(quote: str, answer: str) -> bool:
    norm = lambda t: re.sub(r"[^a-z0-9]+", " ", (t or "").lower()).strip()
    q, a = norm(quote), norm(answer)
    if len(q) < 12:
        return False
    words = q.split()
    return q in a or any(" ".join(words[i:i + 6]) in a for i in range(0, max(1, len(words) - 5), 3))


REF_RECHECK_SYSTEM = """Two short answers to the same question: the reference answer (correct) and a candidate.
Decide only whether the candidate names the same thing as the reference. Allow differences in spelling,
wording, abbreviation, extra words, a fuller or shorter form of a name, units and rounding, as far as the
question allows. "same" is false if it names a different thing or a different number (beyond rounding),
or gives several alternatives. Ignore any reasoning; compare the answers only."""

REF_RECHECK_SCHEMA = {
    "type": "object",
    "properties": {"same": {"type": "boolean"}, "reason": {"type": "string", "maxLength": 200}},
    "required": ["same", "reason"],
}

# judge options for this run (evals/configs.yaml `judge:`), set in run()
#   recheck: when the judge says "incorrect", compare the extracted answer with the reference alone, so a
#   right final answer isn't marked wrong for its reasoning (the 2026-10-08 grader audit found ~1-3 such
#   cases per 100 answers, e.g. 'Game Freak' / 'Eli Capilouto' marked wrong while matching the reference)
JUDGE_OPTS = {"recheck": False}


def rubric_key(q: dict) -> str:
    """Changes when the question's checklist or the judge instructions change."""
    if "answer" in q:  # reference-answer question (benchmark)
        parts = [REF_JUDGE_SYSTEM, q["answer"], q.get("grading", "")]
        if JUDGE_OPTS.get("recheck"):
            parts.append(REF_RECHECK_SYSTEM)
        blob = json.dumps(parts, sort_keys=True, default=str)
        return hashlib.sha1(blob.encode("utf-8")).hexdigest()[:12]
    blob = json.dumps([JUDGE_SYSTEM, q.get("must"), q.get("details"), q.get("must_not")], sort_keys=True, default=str)
    return hashlib.sha1(blob.encode("utf-8")).hexdigest()[:12]


def write_results(path: Path, results: list[dict]) -> None:
    tmp = path.with_suffix(".tmp")
    tmp.write_text("\n".join(json.dumps(r, default=str) for r in results) + "\n", encoding="utf-8")
    tmp.replace(path)


def summarize_run(name: str, desc: str, q: dict, rep: int, trace: dict, peak_mb: int, trace_path: str) -> dict:
    final = trace.get("final") or {}
    workers = []
    for r in trace.get("worker_results", []):
        workers.append({k: r.get(k) for k in ("model", "base_model", "lab", "subq", "error", "support_rate",
                                                "seconds", "tokens_per_second", "confidence", "strategy",
                                                "thought_chars", "completion_tokens")}
                       | {"claims": len(r.get("claims", []) or []),
                          "verdicts": [c.get("verdict") for c in r.get("claims", []) or []]})
    return {
        "config": name, "config_description": desc, "question_id": q["id"], "question": q["question"],
        "repeat": rep, "mode": trace.get("mode"),
        "error": trace.get("error"), "answer": final.get("answer", ""),
        "sources": [s["url"] for s in final.get("sources", [])],
        "n_citations": len(final.get("sources", [])),
        "stats": trace.get("stats", {}), "total_seconds": (trace.get("stats") or {}).get("total_seconds"),
        "peak_vram_mb": peak_mb or None, "coordinator": trace["config"]["coordinator"]["model"],
        "team": trace.get("team", []), "verifier": trace["config"]["verifier"]["model"]
        if trace.get("mode") == "swarm" else None,
        "workers": workers, "trace": trace_path,
        "evidence_web_pages": sum(1 for s in trace.get("sources_fetched", [])
                                  if s.get("source") == "web" and not s.get("error") and s.get("chars")),
    }


# ---------------------------------------------------------------------- judge

async def judge_all(results: list[dict], questions: dict, pool: ModelPool, jcfg: dict, rec: Recorder,
                    force: bool = True, save=None, key: str = "grade") -> None:
    """Grade answers. With force=False, answers already graded by this judge against the same
    checklist are kept, so an interrupted grading pass continues where it stopped."""
    model = jcfg["model"]
    if model not in pool.cards:
        rec.say(f"judge model '{model}' not found in Models/ - skipping grading")
        return
    todo = [r for r in results if force or not _graded(r, questions, model, key)]
    if not todo:
        rec.say("All answers already graded")
        return
    await pool.unload_all()
    rec.say(f"Grading {len(todo)} answers with judge {model}"
            + (f" ({len(results) - len(todo)} already graded)" if len(todo) < len(results) else ""))
    try:
        await _judge_loop(todo, questions, pool, jcfg, rec, model, save, key)
    except Exception as e:  # never lose the finished runs because grading broke
        rec.say(f"grading stopped: {type(e).__name__}: {e}. Runs are saved; grade later with --regrade last")


def _graded(r: dict, questions: dict, model: str, key: str = "grade") -> bool:
    g, q = r.get(key) or {}, questions.get(r["question_id"])
    return bool(q) and g.get("judge") == model and g.get("score") is not None and g.get("rubric") == rubric_key(q)


async def _judge_loop(results, questions, pool, jcfg, rec, model, save=None, key: str = "grade") -> None:
    async with pool.use(model, jcfg.get("ctx_per_slot", 8192), jcfg.get("parallel", 1), pin=True) as url:
        for i, r in enumerate(results, 1):
            if save and i % 10 == 0:
                save()  # a power cut during a long grading pass loses at most 10 grades
            q = questions.get(r["question_id"])
            if not q:
                continue
            if "answer" in q:
                await _judge_reference(url, r, q, model, rec, i, len(results), key)
                continue
            # essential facts count double, supporting details count once
            must = [_item(m) for m in q.get("must", [])] + [_item(m) for m in q.get("details", [])]
            weights = [ESSENTIAL_WEIGHT] * len(q.get("must", [])) + [DETAIL_WEIGHT] * len(q.get("details", []))
            must_not = [_item(m) for m in q.get("must_not", [])]
            if r.get("error") or not r.get("answer"):
                r[key] = {"score": 0.0, "letter": "F", "note": "run failed or gave no answer", "judge": model,
                              "rubric": rubric_key(q)}
                continue
            user = (f"Question: {q['question']}\n\nAnswer to grade:\n{r['answer']}\n\n"
                    "MUST items:\n" + "\n".join(f"{n}. {m}" for n, m in enumerate(must, 1)) + "\n\n"
                    "MUST NOT items:\n" + ("\n".join(f"{n}. {m}" for n, m in enumerate(must_not, 1)) or "(none)"))
            try:
                for attempt in range(2):  # retry once if the judge skips an item
                    res = await llm.chat_json(url, [{"role": "system", "content": JUDGE_SYSTEM},
                                                    {"role": "user", "content": user}],
                                              JUDGE_SCHEMA, max_tokens=1200, temperature=0.0 if attempt == 0 else 0.3)
                    data = res.data or {}
                    got = {int(x["n"]) for x in data.get("must", []) if isinstance(x, dict) and "n" in x}
                    got_not = {int(x["n"]) for x in data.get("must_not", []) if isinstance(x, dict) and "n" in x}
                    if got >= set(range(1, len(must) + 1)) and got_not >= set(range(1, len(must_not) + 1)):
                        break
                got_m = {int(x["n"]): x for x in data.get("must", []) if isinstance(x, dict) and "n" in x}
                got_n = {int(x["n"]): x for x in data.get("must_not", []) if isinstance(x, dict) and "n" in x}
                items = [{"item": m, "status": (got_m.get(n) or {}).get("status", "missing"),
                          "reason": (got_m.get(n) or {}).get("reason", "judge gave no verdict"),
                          "weight": weights[n - 1], "essential": weights[n - 1] == ESSENTIAL_WEIGHT}
                         for n, m in enumerate(must, 1)]
                bad = [{"item": m, "status": (got_n.get(n) or {}).get("status", "ok"),
                        "reason": (got_n.get(n) or {}).get("reason", ""),
                        "quote": str((got_n.get(n) or {}).get("quote", "") or "")}
                       for n, m in enumerate(must_not, 1)]
                # A hand audit found most "violated" verdicts were wrong (the judge penalised hedged
                # or correct sentences). Only count one when the quoted offending sentence is really
                # in the answer; otherwise keep the verdict for inspection but don't penalise.
                for x in bad:
                    if x["status"] == "violated" and not _in_answer(x["quote"], r["answer"]):
                        x["status"], x["overruled"] = "ok", "judge gave no matching quote from the answer"
                total_w = sum(x["weight"] for x in items)
                base = sum(MUST_POINTS[x["status"]] * x["weight"] for x in items) / total_w if total_w else 1.0
                score = max(0.0, base - VIOLATION_PENALTY * sum(x["status"] == "violated" for x in bad))
                ess = [x for x in items if x["essential"]]
                ess_score = sum(MUST_POINTS[x["status"]] for x in ess) / len(ess) if ess else None
                r[key] = {"score": round(score, 3), "letter": letter(score), "must": items,
                              "essentials": None if ess_score is None else round(ess_score, 3),
                              "violations": sum(x["status"] == "violated" for x in bad),
                              "must_not": bad, "judge": model, "judge_seconds": round(res.seconds, 1),
                              "rubric": rubric_key(q)}
                rec.say(f"  [{i}/{len(results)}] {r['config']:<18} {r['question_id']:<22} "
                        f"{letter(score)} ({score:.0%})")
            except Exception as e:
                r[key] = {"score": None, "letter": "–", "note": f"judge error: {e}"[:300], "judge": model}
                rec.say(f"  [{i}/{len(results)}] judge error: {e}"[:200])


async def _judge_reference(url: str, r: dict, q: dict, model: str, rec, i: int, total: int, key: str = "grade") -> None:
    """Benchmark grading. grading 'exact' (GAIA): the extracted final answer must match the reference
    quasi-exactly. grading 'judge' (FRAMES): the judge's verdict counts. Both are always recorded,
    plus whether the reference answer appears word-for-word in the response, as cross-checks."""
    mode = q.get("grading", "judge")
    base = {"judge": model, "rubric": rubric_key(q), "reference": q["answer"], "grading": mode}
    if r.get("error") or not r.get("answer"):
        r[key] = {**base, "score": 0.0, "letter": "F", "verdict": "not_attempted", "note": "run failed or gave no answer"}
        return
    user = f"Question: {q['question']}\n\nReference answer: {q['answer']}\n\nResponse:\n{r['answer']}"
    try:
        res = await llm.chat_json(url, [{"role": "system", "content": REF_JUDGE_SYSTEM},
                                        {"role": "user", "content": user}], REF_JUDGE_SCHEMA,
                                  max_tokens=400, temperature=0.0)
        d = res.data or {}
        extracted = str(d.get("extracted_answer", "") or "")
        verdict = d.get("verdict") if d.get("verdict") in ("correct", "incorrect", "not_attempted") else "incorrect"
        exact = benchmarks.answers_match(extracted, q["answer"])
        first_verdict, recheck = verdict, None
        if mode == "judge" and JUDGE_OPTS.get("recheck") and verdict == "incorrect" and extracted.strip():
            rr = await llm.chat_json(url, [{"role": "system", "content": REF_RECHECK_SYSTEM},
                                           {"role": "user", "content": f"Question: {q['question']}\n\n"
                                            f"Reference answer: {q['answer']}\n\nCandidate answer: {extracted}"}],
                                     REF_RECHECK_SCHEMA, max_tokens=200, temperature=0.0)
            rd = rr.data if isinstance(rr.data, dict) else {}
            recheck = {"same": bool(rd.get("same")), "reason": str(rd.get("reason", ""))[:200]}
            if recheck["same"]:
                verdict = "correct"
        ok = exact if mode == "exact" else verdict == "correct"
        r[key] = {**base, "score": 1.0 if ok else 0.0, "letter": "A" if ok else "F", "verdict": verdict,
                      "first_verdict": first_verdict, "recheck": recheck,
                      "extracted": extracted, "exact_match": exact,
                      "gold_in_text": benchmarks.gold_in_text(r["answer"], q["answer"]),
                      "reason": str(d.get("reason", ""))[:300], "judge_seconds": round(res.seconds, 1)}
        rec.say(f"  [{i}/{total}] {r['config']:<18} {r['question_id']:<22} {'RIGHT' if ok else 'wrong'}"
                f" ({verdict}; extracted {extracted[:40]!r})")
    except Exception as e:
        r[key] = {**base, "score": None, "letter": "–", "note": f"judge error: {e}"[:300]}
        rec.say(f"  [{i}/{total}] judge error: {e}"[:200])


async def grade_attempts(out: Path, results: list[dict], questions: dict, pool: ModelPool, jcfg: dict,
                         rec: Recorder, save=None) -> int:
    """Runs with several attempts per question (manager.attempts): grade EVERY attempt's answer, not just
    the one the vote chose, so the oracle (any attempt right), the vote's hit rate and any other way of
    choosing can be measured offline. Grades land in r["attempt_grades"] (one per attempt, in order) with
    r["attempt_info"] (each attempt's config, trust-check verdict, time). An attempt whose answer is the
    chosen answer reuses that grade; grades already made by the same judge are kept, so it resumes."""
    model = jcfg.get("model")
    if not model or model not in pool.cards:
        return 0
    todo = []
    for r in results:
        q = questions.get(r["question_id"])
        tp = out / str(r.get("trace") or "")
        if not q or not r.get("trace") or not tp.is_file():
            continue
        try:
            atts = json.loads(tp.read_text(encoding="utf-8")).get("attempts") or []
        except (OSError, json.JSONDecodeError):
            continue
        if len(atts) < 2:
            continue
        key = rubric_key(q)
        ok = lambda g: bool(g) and g.get("judge") == model and g.get("score") is not None and g.get("rubric") == key
        old = r.get("attempt_grades") or []
        grades = []
        for k, a in enumerate(atts):
            ans = str(a.get("answer") or "")
            if k < len(old) and ok(old[k]):
                grades.append(old[k])
            elif ans and ans == r.get("answer") and ok(r.get("grade")):
                grades.append({**r["grade"], "copied": True})
            else:
                grades.append(None)
                todo.append((r, k, {"config": r["config"], "question_id": r["question_id"], "answer": ans,
                                    "error": None if ans else "attempt gave no answer"}))
        r["attempt_grades"] = grades
        r["attempt_info"] = [{"config": a.get("config"),
                              "trust_ready": ((a.get("stats") or {}).get("manager") or {}).get("trust_final_ready"),
                              "seconds": (a.get("stats") or {}).get("total_seconds")} for a in atts]
    if not todo:
        if save:
            save()
        return 0

    def sync_save() -> None:
        for r, k, p in todo:
            if p.get("grade"):
                r["attempt_grades"][k] = p["grade"]
        if save:
            save()

    await pool.unload_all()
    rec.say(f"Grading {len(todo)} individual attempts with judge {model} (for the oracle and vote analysis)")
    try:
        await _judge_loop([p for _, _, p in todo], questions, pool, jcfg, rec, model, sync_save, "grade")
    except Exception as e:
        rec.say(f"attempt grading stopped: {type(e).__name__}: {e}. Run --regrade <folder> --attempts-only to finish")
    sync_save()
    return len(todo)


def attempts_section(results: list[dict], configs: list[str]) -> tuple[list[str], str]:
    """Several attempts per question: how good one attempt is, how often ANY attempt was right (the
    oracle), what a plain most-common-answer vote and the coordinator's vote got, and the vote's hit rate
    when the attempts disagreed."""
    import itertools
    rows = []
    for c in configs:
        rs = [r for r in results if r["config"] == c and r.get("attempt_grades")
              and all(g and g.get("score") is not None for g in r["attempt_grades"])]
        if not rs:
            continue
        n_att = max(len(r["attempt_grades"]) for r in rs)
        right = lambda g: g["score"] >= 0.5
        each = sum(sum(right(g) for g in r["attempt_grades"]) / len(r["attempt_grades"]) for r in rs) / len(rs)
        oracle = sum(any(right(g) for g in r["attempt_grades"]) for r in rs) / len(rs)
        vote = sum((r.get("grade") or {}).get("score", 0) >= 0.5 for r in rs) / len(rs)
        maj = 0
        for r in rs:  # most common extracted answer (judge's extraction, normalised); ties -> first attempt
            ks = [" ".join(str(g.get("extracted", "")).lower().split()) for g in r["attempt_grades"]]
            best = max(range(len(ks)), key=lambda i: (ks.count(ks[i]) if ks[i] else 0, -i))
            maj += right(r["attempt_grades"][best])
        split = [r for r in rs if 0 < sum(right(g) for g in r["attempt_grades"]) < len(r["attempt_grades"])]
        hit = sum((r.get("grade") or {}).get("score", 0) >= 0.5 for r in split)
        # oracle by number of attempts: average over every subset of that size
        curve = []
        for k in range(1, n_att + 1):
            tot = cnt = 0
            for r in rs:
                gs = [right(g) for g in r["attempt_grades"]]
                if len(gs) < k:
                    continue
                subs = list(itertools.combinations(range(len(gs)), k))[:200]
                tot += sum(any(gs[i] for i in sub) for sub in subs) / len(subs)
                cnt += 1
            curve.append(tot / cnt if cnt else None)
        rows.append({"c": c, "n": len(rs), "k": n_att, "each": each, "oracle": oracle, "vote": vote,
                     "maj": maj / len(rs), "split": len(split), "hit": hit, "curve": curve})
    if not rows:
        return [], ""
    fmt = lambda v: "–" if v is None else f"{v:.0%}"
    md = ["", "## Attempts (every attempt graded)", "",
          "| Config | Questions | Attempts | One attempt (avg) | Most-common answer | Coordinator's vote | Any attempt right (oracle) | Vote right when attempts split |",
          "|---|---|---|---|---|---|---|---|"]
    trs = ""
    for x in rows:
        md.append(f"| {x['c']} | {x['n']} | {x['k']} | {x['each']:.0%} | {x['maj']:.0%} | {x['vote']:.0%} | "
                  f"{x['oracle']:.0%} | {x['hit']}/{x['split']} |")
        trs += (f"<tr><td>{html.escape(x['c'])}</td><td>{x['n']}</td><td>{x['k']}</td><td>{x['each']:.0%}</td>"
                f"<td>{x['maj']:.0%}</td><td><b>{x['vote']:.0%}</b></td><td>{x['oracle']:.0%}</td>"
                f"<td>{x['hit']}/{x['split']}</td></tr>")
    md += ["", "Oracle by number of attempts (share of questions where at least one of N attempts is right, "
              "averaged over every set of N attempts):", ""]
    for x in rows:
        md.append(f"- {x['c']}: " + ", ".join(f"{i + 1}: {fmt(v)}" for i, v in enumerate(x["curve"])))
    md.append("")
    page = ("<h2>Attempts</h2><p class=m>Every attempt graded separately. The oracle is the share of questions where "
            "at least one attempt was right: the ceiling for any way of choosing.</p>"
            "<div class=card><table><tr><th>Config</th><th>Questions</th><th>Attempts</th><th>One attempt</th>"
            "<th>Most-common answer</th><th>Coordinator's vote</th><th>Oracle</th><th>Vote right when split</th></tr>"
            f"{trs}</table></div>"
            + "".join(f"<p class=m>{html.escape(x['c'])} oracle by attempts: "
                      + ", ".join(f"{i + 1}: {fmt(v)}" for i, v in enumerate(x["curve"])) + "</p>" for x in rows))
    return md, page


# ---------------------------------------------------------------------- report

def paired_ci(a: dict, b: dict, n: int = 4000, seed: int = 7) -> tuple[float, float, float] | None:
    """Mean of (a - b) over the questions both have, with a 90% paired-bootstrap interval.
    a, b: question_id -> score."""
    import random
    qs = [q for q in a if q in b and a[q] is not None and b[q] is not None]
    if len(qs) < 3:
        return None
    d = [a[q] - b[q] for q in qs]
    rnd = random.Random(seed)
    means = sorted(sum(rnd.choice(d) for _ in d) / len(d) for _ in range(n))
    return sum(d) / len(d), means[int(0.05 * n)], means[int(0.95 * n) - 1]


def strategy_screen(results: list[dict], weak: set) -> tuple[list[str], str]:
    """Report section for strategy-screen runs: per worker model, each way of thinking vs answering
    directly, on the same questions and the same evidence (paired)."""
    rows: dict[str, dict[str, list[dict]]] = {}
    for r in results:
        if (r.get("stats") or {}).get("mode") != "screen" or not r.get("workers"):
            continue
        w = r["workers"][0]
        rows.setdefault(w.get("base_model") or w["model"], {}).setdefault(w.get("strategy") or "direct", []).append(r)
    if not rows:
        return [], ""
    from swarm import strategies as strat

    def per_q(rs):
        by: dict[str, list[float]] = {}
        for r in rs:
            sc = (r.get("grade") or {}).get("score")
            if sc is not None and r["question_id"] not in weak:
                by.setdefault(r["question_id"], []).append(sc)
        return {q: sum(v) / len(v) for q, v in by.items()}

    def mean(xs):
        xs = [x for x in xs if x is not None]
        return sum(xs) / len(xs) if xs else None

    md = ["", "## Strategy screen (worker answers graded directly, no coordinator)", "",
          "Δ = difference from the same model answering directly, on the same questions and evidence, "
          "with a 90% interval. If the interval includes 0, the difference may be luck.", ""]
    html_parts = ["<h2>Strategy screen</h2><p class=m>Each worker's own answers graded directly (no coordinator). "
                  "Δ = change vs the same model answering directly, same questions and evidence, 90% interval; "
                  "an interval that includes 0 may be luck.</p>"]
    for model, strats in sorted(rows.items()):
        base = per_q(strats.get("direct", []))
        table = []
        for sname, rs in strats.items():
            ws = [w for r in rs for w in r.get("workers", [])]
            ok = [w for w in ws if not w.get("error")]
            sc = mean(list(per_q(rs).values()))
            ci = None if sname == "direct" else paired_ci(per_q(rs), base)
            table.append({
                "s": sname, "label": strat.label(sname) if sname != "direct" else "Direct (no method)",
                "score": sc, "ci": ci,
                "ess": mean([(r.get("grade") or {}).get("essentials") for r in rs if r["question_id"] not in weak]),
                "support": mean([w.get("support_rate") for w in ok]),
                "claims": mean([w.get("claims") for w in ok]),
                "failed": len(ws) - len(ok), "parts": len(ws),
                "sec": mean([r.get("total_seconds") for r in rs]),
                "thought": mean([w.get("thought_chars") for w in ok]),
            })
        table.sort(key=lambda t: -(t["score"] if t["score"] is not None else -1))
        best = table[0]["s"] if table else ""
        pct = lambda x: "–" if x is None else f"{x:.0%}"
        dlt = lambda c: "–" if not c else f"{c[0] * 100:+.1f} ({c[1] * 100:+.1f} to {c[2] * 100:+.1f})"
        md += [f"### {model}", "", "| Way of thinking | Score | Δ vs direct (90% interval) | Essentials | Claims supported | Claims per part | Failed parts | Avg time | Thinking chars |",
               "|---|---|---|---|---|---|---|---|---|"]
        trs = ""
        for t in table:
            thought = "–" if t["thought"] is None else f"{t['thought']:.0f}"
            if t["s"] == strat.NATIVE and (t["thought"] or 0) < 50:
                thought += " (did not think)"
            md.append(f"| {'**' if t['s'] == best else ''}{t['label']}{'**' if t['s'] == best else ''} | {pct(t['score'])} | {dlt(t['ci'])} | "
                      f"{pct(t['ess'])} | {pct(t['support'])} | {'–' if t['claims'] is None else round(t['claims'], 1)} | "
                      f"{t['failed']}/{t['parts']} | {'–' if t['sec'] is None else str(round(t['sec'])) + 's'} | {thought} |")
            trs += (f"<tr><td>{'<b>' if t['s'] == best else ''}{html.escape(t['label'])}{'</b>' if t['s'] == best else ''}</td>"
                    f"<td>{pct(t['score'])}</td><td>{dlt(t['ci'])}</td><td>{pct(t['ess'])}</td><td>{pct(t['support'])}</td>"
                    f"<td>{'–' if t['claims'] is None else round(t['claims'], 1)}</td><td>{t['failed']}/{t['parts']}</td>"
                    f"<td>{'–' if t['sec'] is None else round(t['sec'])}s</td><td>{html.escape(thought)}</td></tr>")
        md.append("")
        html_parts.append(f"<h3>{html.escape(model)}</h3><div class=card><table><tr><th>Way of thinking</th><th>Score</th>"
                          f"<th>Δ vs direct</th><th>Essentials</th><th>Claims supported</th><th>Claims per part</th>"
                          f"<th>Failed parts</th><th>Avg time</th><th>Thinking chars</th></tr>{trs}</table></div>")
    return md, "".join(html_parts)


def reference_section(results: list[dict], configs: list[str]) -> tuple[list[str], str]:
    """Benchmark runs (reference answers): accuracy with a 90% interval, what the wrong answers were,
    and how often the cross-checks agree with the score."""
    import random
    rows = []
    for c in configs:
        gs = [(r.get("grade") or {}) for r in results if r["config"] == c and "reference" in (r.get("grade") or {})]
        gs = [g for g in gs if g.get("score") is not None]
        if not gs:
            continue
        sc = [g["score"] for g in gs]
        rnd = random.Random(11)
        boots = sorted(sum(rnd.choice(sc) for _ in sc) / len(sc) for _ in range(2000))
        rows.append({"c": c, "n": len(gs), "acc": sum(sc) / len(sc), "lo": boots[100], "hi": boots[1899],
                     "wrong": sum(g.get("verdict") == "incorrect" for g in gs),
                     "none": sum(g.get("verdict") == "not_attempted" for g in gs),
                     "judge_ok": sum(g.get("verdict") == "correct" for g in gs),
                     "exact": sum(bool(g.get("exact_match")) for g in gs),
                     "in_text": sum(bool(g.get("gold_in_text")) for g in gs)})
    if not rows:
        return [], ""
    rows.sort(key=lambda x: -x["acc"])
    md = ["", "## Benchmark accuracy (reference answers)", "",
          "| Config | Accuracy | 90% interval | Wrong answer | No answer | Judge says right | Exact match | Answer appears in text |",
          "|---|---|---|---|---|---|---|---|"]
    trs = ""
    for x in rows:
        md.append(f"| {x['c']} | {x['acc']:.0%} | {x['lo']:.0%}–{x['hi']:.0%} | {x['wrong']} | {x['none']} | "
                  f"{x['judge_ok']}/{x['n']} | {x['exact']}/{x['n']} | {x['in_text']}/{x['n']} |")
        trs += (f"<tr><td>{html.escape(x['c'])}</td><td><b>{x['acc']:.0%}</b></td><td>{x['lo']:.0%}–{x['hi']:.0%}</td>"
                f"<td>{x['wrong']}</td><td>{x['none']}</td><td>{x['judge_ok']}/{x['n']}</td><td>{x['exact']}/{x['n']}</td>"
                f"<td>{x['in_text']}/{x['n']}</td></tr>")
    md.append("")
    page = ("<h2>Benchmark accuracy</h2><p class=m>Reference-answer grading. The last three columns are cross-checks "
            "of the grade (judge verdict, exact match of the extracted answer, reference answer found word-for-word).</p>"
            "<div class=card><table><tr><th>Config</th><th>Accuracy</th><th>90% interval</th><th>Wrong answer</th>"
            f"<th>No answer</th><th>Judge says right</th><th>Exact match</th><th>In text</th></tr>{trs}</table></div>")
    return md, page


def build_report(out: Path, results: list[dict], meta: dict) -> None:
    configs = list(dict.fromkeys(r["config"] for r in results))
    qids = list(dict.fromkeys(r["question_id"] for r in results))
    desc = {r["config"]: r.get("config_description", "") for r in results}

    def cell(cfg: str, qid: str) -> list[dict]:
        return [r for r in results if r["config"] == cfg and r["question_id"] == qid]

    def avg(xs):
        xs = [x for x in xs if x is not None]
        return sum(xs) / len(xs) if xs else None

    # with shared evidence, a question where search found almost nothing measures search luck, not
    # the models; in a live study finding sources IS part of the test, so nothing is left out
    weak = set() if meta.get("live") else {r["question_id"] for r in results if r.get("evidence_web_pages", 99) < 2}
    target = meta.get("time_target") or 90
    board = []
    for c in configs:
        rs = [r for r in results if r["config"] == c]
        scores = [(r.get("grade") or {}).get("score") for r in rs if r["question_id"] not in weak]
        board.append({
            "config": c, "desc": desc[c], "runs": len(rs),
            "score": avg(scores), "seconds": avg([r.get("total_seconds") for r in rs]),
            "score2": avg([(r.get("grade2") or {}).get("score") for r in rs if r["question_id"] not in weak]),
            "peak": max([r.get("peak_vram_mb") or 0 for r in rs] or [0]),
            "peak_ram": max([r.get("peak_ram_mb") or 0 for r in rs] or [0]),
            "tok_out": avg([((r.get("stats") or {}).get("tokens") or {}).get("completion_tokens") for r in rs]),
            "tok_in": avg([((r.get("stats") or {}).get("tokens") or {}).get("prompt_tokens") for r in rs]),
            "failed": sum(1 for r in rs if r.get("error")),
            "on_time": sum(1 for r in rs if (r.get("total_seconds") or 1e9) <= target) / len(rs) if rs else None,
            "essentials": avg([(r.get("grade") or {}).get("essentials") for r in rs if r["question_id"] not in weak]),
            "violations": sum((r.get("grade") or {}).get("violations") or 0 for r in rs),
        })
    board.sort(key=lambda b: -(b["score"] if b["score"] is not None else -1))

    models: dict[str, dict] = {}
    for r in results:
        for w in r.get("workers", []):
            m = models.setdefault(w.get("base_model") or w["model"], {"answers": 0, "failed": 0, "support": [], "tps": []})
            if w.get("error"):
                m["failed"] += 1
            else:
                m["answers"] += 1
                if w.get("support_rate") is not None:
                    m["support"].append(w["support_rate"])
                if w.get("tokens_per_second"):
                    m["tps"].append(w["tokens_per_second"])

    pct = lambda x: "–" if x is None else f"{x:.0%}"
    tps = lambda v: "–" if not v["tps"] else "%.0f" % statistics.mean(v["tps"])
    sec = lambda x: "–" if x is None else f"{x:.0f}s"
    ram = lambda b: f"{b['peak_ram'] / 1024:.1f} GB" if b.get("peak_ram") else "–"
    tok = lambda b: "–" if not b.get("tok_out") else f"{b['tok_in'] / 1000:.1f}k / {b['tok_out'] / 1000:.1f}k"

    # ---------------- markdown
    md = [f"# Local Swarm evaluation — {meta['started']}", "",
          f"Questions: {len(qids)} · Configurations: {len(configs)} · Repeats: {meta['repeats']} · "
          f"Judge: {meta.get('judge') or 'none'} · Evidence: {meta['evidence']}", "",
          "## Leaderboard", "", f"| Config | Score | Grade | Essentials | Mistakes | Avg time | Under {target}s | Tokens read / written | Peak GPU | Peak RAM | Failed runs | What it is |",
          "|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for b in board:
        md.append(f"| {b['config']} | {pct(b['score'])} | {letter(b['score'])} | {pct(b['essentials'])} | {b['violations']} | {sec(b['seconds'])} | "
                  f"{pct(b['on_time'])} | {tok(b)} | {b['peak'] / 1024:.1f} GB | {ram(b)} | {b['failed']} | {b['desc']} |")
    if weak:
        md += ["", f"**Left out of the leaderboard (fewer than 2 web pages were found, so it tests search luck, "
                   f"not the models):** {', '.join(sorted(weak))}"]
    wide = len(configs) > 10
    if any(b.get("score2") is not None for b in board):
        md += ["", f"## Cross-check: second judge ({meta.get('judge2') or 'second judge'})", "",
               "| Config | Score (main judge) | Score (second judge) | Difference |", "|---|---|---|---|"]
        for b in board:
            if b.get("score2") is not None and b.get("score") is not None:
                md.append(f"| {b['config']} | {pct(b['score'])} | {pct(b['score2'])} | {(b['score'] - b['score2']) * 100:+.1f} |")
    md += ["", "## By question", ""] + (["(Too many configurations for one table; see results.jsonl.)"] if wide else
                                        ["| Question | " + " | ".join(configs) + " |", "|---|" + "---|" * len(configs)])
    for q in ([] if wide else qids):
        row = []
        for c in configs:
            rs = cell(c, q)
            s = avg([(r.get("grade") or {}).get("score") for r in rs])
            row.append(f"{letter(s)} {pct(s)} · {sec(avg([r.get('total_seconds') for r in rs]))}")
        md.append(f"| {q} | " + " | ".join(row) + " |")
    md += ["", "## Worker models (swarm configs)", "", "| Model | Answers | Failed | Avg claim support | Avg tok/s |",
           "|---|---|---|---|---|"]
    for m, v in sorted(models.items()):
        md.append(f"| {m} | {v['answers']} | {v['failed']} | {pct(avg(v['support']))} | {tps(v)} |")
    screen_md, screen_html = strategy_screen(results, weak)
    md += screen_md
    ref_md, ref_html = reference_section(results, configs)
    md += ref_md
    screen_html += ref_html
    att_md, att_html = attempts_section(results, configs)
    md += att_md
    screen_html += att_html
    if any(b.get("score2") is not None for b in board):
        screen_html += ("<h2>Cross-check: second judge</h2><p class=m>Every answer graded again by "
                        + html.escape(str(meta.get("judge2") or "a second judge")) + ", a different model family.</p>"
                        "<div class=card><table><tr><th>Config</th><th>Main judge</th><th>Second judge</th><th>Difference</th></tr>"
                        + "".join(f"<tr><td>{html.escape(b['config'])}</td><td>{pct(b['score'])}</td><td>{pct(b['score2'])}</td>"
                                  f"<td>{(b['score'] - b['score2']) * 100:+.1f}</td></tr>"
                                  for b in board if b.get("score2") is not None and b.get("score") is not None)
                        + "</table></div>")
    md += ["", "_Grades come from a small local judge model. Spot-check the reasons below before trusting a ranking._", ""]
    (out / "report.md").write_text("\n".join(md), encoding="utf-8")

    # ---------------- html
    e = html.escape
    grade_cls = lambda g: {"A": "a", "B": "b", "C": "c", "D": "d", "F": "f"}.get(g, "")

    rows = "".join(
        f"<tr><td><b>{e(b['config'])}</b><div class=m>{e(b['desc'])}</div></td>"
        f"<td class='g {grade_cls(letter(b['score']))}'>{letter(b['score'])}</td><td>{pct(b['score'])}</td>"
        f"<td>{pct(b['essentials'])}</td><td>{b['violations']}</td>"
        f"<td>{sec(b['seconds'])}</td><td>{pct(b['on_time'])}</td><td>{tok(b)}</td><td>{b['peak'] / 1024:.1f} GB</td><td>{ram(b)}</td><td>{b['failed']}</td></tr>"
        for b in board)
    qrows = ""
    for q in qids:
        tds = ""
        for c in configs:
            rs = cell(c, q)
            s = avg([(r.get("grade") or {}).get("score") for r in rs])
            tds += (f"<td><span class='g {grade_cls(letter(s))}'>{letter(s)}</span> {pct(s)}"
                    f"<div class=m>{sec(avg([r.get('total_seconds') for r in rs]))}</div></td>")
        flag = " <span class=m title='fewer than 2 web pages found'>⚠ weak evidence, not in leaderboard</span>" if q in weak else ""
        qrows += f"<tr><td>{e(q)}{flag}</td>{tds}</tr>"
    mrows = "".join(
        f"<tr><td>{e(m)}</td><td>{v['answers']}</td><td>{v['failed']}</td><td>{pct(avg(v['support']))}</td>"
        f"<td>{tps(v)}</td></tr>"
        for m, v in sorted(models.items()))
    details = ""
    for r in results:
        g = r.get("grade") or {}
        items = "".join(f"<li><span class='s {x['status']}'>{x['status']}</span> {'<b>' if x.get('essential') else ''}{e(_item(x['item']))}{'</b>' if x.get('essential') else ''}"
                        f"<div class=m>{e(x.get('reason', ''))}</div></li>" for x in g.get("must", []))
        items += "".join(f"<li><span class='s {x['status']}'>{'VIOLATED' if x['status'] == 'violated' else 'avoided'}</span> "
                         f"{e(_item(x['item']))}<div class=m>{e(x.get('reason', ''))}</div></li>" for x in g.get("must_not", []))
        if "reference" in g:
            items += (f"<li><span class='s {'met' if g.get('score') else 'missing'}'>{e(str(g.get('verdict', '')))}</span> "
                      f"reference: <b>{e(str(g['reference']))}</b> · extracted: {e(str(g.get('extracted', '')))}"
                      f"<div class=m>{e(str(g.get('reason', '')))}</div></li>")
        workers = "".join(
            f"<li>{e(w['model'])}: {('failed — ' + e(str(w['error'])[:160])) if w.get('error') else pct(w.get('support_rate')) + ' supported'}"
            f" (q{w['subq'] + 1})</li>" for w in r.get("workers", []))
        details += (f"<details><summary><span class='g {grade_cls(g.get('letter'))}'>{g.get('letter', '–')}</span> "
                    f"<b>{e(r['config'])}</b> · {e(r['question_id'])}"
                    f"{' · repeat ' + str(r['repeat'] + 1) if meta['repeats'] > 1 else ''} · {sec(r.get('total_seconds'))}"
                    f"{' · ERROR' if r.get('error') else ''}</summary>"
                    f"<div class=ans>{e(r.get('answer') or r.get('error') or '')}</div>"
                    f"<ul class=items>{items}</ul>{('<div class=m>' + e(g['note']) + '</div>') if g.get('note') else ''}"
                    f"{'<div class=m>Workers:</div><ul class=items>' + workers + '</ul>' if workers else ''}"
                    f"<div class=m>trace: {e(r.get('trace', ''))}</div></details>")
    page = f"""<!doctype html><html><head><meta charset=utf-8><meta name=viewport content="width=device-width,initial-scale=1">
<title>Swarm evaluation {e(meta['started'])}</title><style>
:root{{--bg:#f6f7f9;--p:#fff;--ink:#1b1f24;--mu:#5f6b78;--ln:#e2e6eb;--a:#1f8a4c;--b:#5b8c1f;--c:#a86400;--d:#c05a1f;--f:#c0392b}}
@media(prefers-color-scheme:dark){{:root{{--bg:#111418;--p:#191d23;--ink:#e7eaee;--mu:#9aa5b1;--ln:#2a3038;--a:#5fd08f;--b:#a6d05f;--c:#f0b458;--d:#f09058;--f:#ff8a7a}}}}
body{{margin:0;background:var(--bg);color:var(--ink);font:15px/1.5 system-ui,Segoe UI,sans-serif}}
main{{max-width:1100px;margin:0 auto;padding:20px}} h1{{font-size:20px}} h2{{font-size:15px;text-transform:uppercase;letter-spacing:.5px;color:var(--mu);margin-top:28px}}
.card{{background:var(--p);border:1px solid var(--ln);border-radius:12px;padding:14px;overflow-x:auto}}
table{{border-collapse:collapse;width:100%}} td,th{{text-align:left;padding:7px 10px;border-top:1px solid var(--ln);vertical-align:top}}
th{{color:var(--mu);font-weight:600;font-size:13px;border-top:0}} .m{{color:var(--mu);font-size:12.5px}}
.g{{display:inline-block;min-width:22px;text-align:center;font-weight:800;border-radius:6px;padding:0 6px}}
.g.a{{color:var(--a)}} .g.b{{color:var(--b)}} .g.c{{color:var(--c)}} .g.d{{color:var(--d)}} .g.f{{color:var(--f)}}
details{{background:var(--p);border:1px solid var(--ln);border-radius:10px;padding:8px 12px;margin:8px 0}} summary{{cursor:pointer}}
.ans{{white-space:pre-wrap;margin:10px 0;padding:10px;border-left:3px solid var(--ln)}}
.items{{list-style:none;padding:0}} .items li{{padding:3px 0}}
.s{{font-size:11.5px;font-weight:700;border-radius:5px;padding:0 6px;margin-right:6px}}
.s.met,.s.ok{{color:var(--a)}} .s.partial{{color:var(--c)}} .s.missing,.s.violated{{color:var(--f)}}
</style></head><body><main>
<h1>Local Swarm evaluation — {e(meta['started'])}</h1>
<div class=m>{len(qids)} questions · {len(configs)} configurations · {meta['repeats']} repeat(s) · judge: {e(meta.get('judge') or 'none')} · evidence: {e(meta['evidence'])}</div>
<h2>Leaderboard</h2>{('<p class=m>Left out: ' + e(', '.join(sorted(weak))) + ' (fewer than 2 web pages were found, so it measures search luck, not the models).</p>') if weak else ''}<div class=card><table><tr><th>Configuration</th><th>Grade</th><th>Score</th><th>Essentials</th><th>Mistakes</th><th>Avg time</th><th>Under {target}s</th><th>Tokens read / written</th><th>Peak GPU</th><th>Peak RAM</th><th>Failed</th></tr>{rows}</table></div>
<h2>By question</h2>{'<p class=m>Too many configurations for one table; see results.jsonl.</p>' if wide else f"<div class=card><table><tr><th>Question</th>{''.join(f'<th>{e(c)}</th>' for c in configs)}</tr>{qrows}</table></div>"}
<h2>Worker models</h2><div class=card><table><tr><th>Model</th><th>Answers</th><th>Failed</th><th>Avg claim support</th><th>Avg tok/s</th></tr>{mrows or '<tr><td colspan=5 class=m>No team configurations in this run.</td></tr>'}</table></div>
{screen_html}
<h2>Every answer, with the judge's reasons</h2>{details}
<p class=m>Grades come from a small local judge model, so spot-check the reasons before trusting a ranking.
Score = weighted share of checklist items met (essential facts, in bold, count double; partial = half) minus {VIOLATION_PENALTY:.0%} for each mistake (MUST NOT violated). "Essentials" = share of essential facts only. "Mistakes" = MUST NOT violations across all runs.</p>
</main></body></html>"""
    (out / "report.html").write_text(page, encoding="utf-8")


# ---------------------------------------------------------------------- main

async def run(args) -> Path:
    args.live = getattr(args, "live", False)
    cfg = load_config()
    econf = expand_configs(yaml.safe_load((REPO / "evals" / "configs.yaml").read_text(encoding="utf-8")))
    judge_cfg = econf.get("judge") or {}
    JUDGE_OPTS["recheck"] = bool(judge_cfg.get("recheck", False))

    if args.regrade == "last":
        done = sorted(p for p in (RUNTIME / "evals").glob("*") if (p / "results.jsonl").exists())
        if not done:
            raise SystemExit("no earlier evaluation to regrade")
        args.regrade = str(done[-1])
    resume_dir = None
    if getattr(args, "resume", None):  # continue an interrupted evaluation where it stopped
        if args.resume == "last":
            started = sorted(p for p in (RUNTIME / "evals").glob("*") if (p / "meta.json").exists())
            if not started:
                raise SystemExit("no earlier evaluation to resume")
            args.resume = str(started[-1])
        resume_dir = repo_path(args.resume)
        old = json.loads((resume_dir / "meta.json").read_text(encoding="utf-8"))
        args.configs = ",".join(old["configs"])
        args.set = old["question_set"]
        args.repeats = old.get("repeats", 1)
        args.questions = ",".join(old["question_ids"]) if old.get("question_ids") else None
        args.reuse_evidence = str(resume_dir)
        args.live = bool(old.get("live")) or getattr(args, "live", False)
        args.budget_tokens = (old.get("budget") or {}).get("max_output_tokens")
        args.budget_seconds = (old.get("budget") or {}).get("max_seconds")
        args.frozen = (old.get("frozen") or {}).get("name")
        args.judge2 = bool(old.get("judge2")) or getattr(args, "judge2", False)
    if args.regrade:
        out = repo_path(args.regrade)
        results = [json.loads(l) for l in (out / "results.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
        meta = json.loads((out / "meta.json").read_text(encoding="utf-8"))
        if meta.get("question_set") and args.set == DEFAULT_SET:  # grade against the run's own question file
            args.set = meta["question_set"]
        for r in results:  # older runs: count web pages from the saved evidence
            if "evidence_web_pages" not in r and (out / "evidence" / f"{r['question_id']}.json").exists():
                docs = json.loads((out / "evidence" / f"{r['question_id']}.json").read_text(encoding="utf-8"))["docs"]
                r["evidence_web_pages"] = sum(1 for d in docs if d["source"] == "web" and not d["error"] and d["text"])
    elif resume_dir:
        out = resume_dir
        results, meta = [], {}
        for line in (out / "results.jsonl").read_text(encoding="utf-8").splitlines() if (out / "results.jsonl").exists() else []:
            try:
                results.append(json.loads(line))
            except json.JSONDecodeError:
                pass  # a line cut off by the power loss
        # a configuration whose every run failed (e.g. a model that needed a fix) is run again
        by_cfg: dict[str, list[dict]] = {}
        for r in results:
            by_cfg.setdefault(r["config"], []).append(r)
        def failed(x):  # the run failed, or every worker in it failed (a screen run has no other answer)
            ws = x.get("workers") or []
            return bool(x.get("error")) or ((x.get("stats") or {}).get("mode") == "screen"
                                            and bool(ws) and all(w.get("error") for w in ws))
        retry = {c for c, rs_ in by_cfg.items() if rs_ and all(failed(x) for x in rs_)}
        if retry:
            print(f"Retrying configurations where every run failed: {', '.join(sorted(retry))}", flush=True)
            results = [r for r in results if r["config"] not in retry]
    else:
        out = RUNTIME / "evals" / dt.datetime.now().strftime("%Y%m%d-%H%M")
        results, meta = [], {}
    if swarm_already_running(cfg):
        print("The swarm web UI is running (Start-Swarm). Close that window first so the two don't fight over the GPU.")
        raise SystemExit(2)
    out.mkdir(parents=True, exist_ok=True)
    rec = Recorder(out)
    # a native crash (e.g. in a page parser) ends Python without any error message: write where it
    # happened to crash.log so it can be found
    import faulthandler
    crash_log = open(out / "crash.log", "a", encoding="utf-8")
    faulthandler.enable(file=crash_log, all_threads=True)

    qpath = repo_path(args.set)
    questions, qmeta = load_set(qpath, args.questions.split(",") if args.questions else None)
    for q in questions:
        if "answer" in q:
            q.setdefault("grading", qmeta.get("grading", "judge"))
    qmap = {q["id"]: q for q in questions}
    cards = scan_models()
    pool = ModelPool(cfg, cards, emit=rec.emit)
    rec.start()
    research = None
    try:
        if not args.regrade:
            names = []
            for n in (args.configs.split(",") if args.configs else econf.get("default", list(econf["configs"]))):
                names += econf.get("groups", {}).get(n.strip(), [n.strip()])
            unknown = [n for n in names if n not in econf["configs"]]
            if unknown:
                raise SystemExit(f"unknown config(s): {unknown}. Known: {list(econf['configs'])}")
            frozen = None
            if getattr(args, "frozen", None):  # configurations fixed in advance: refuse to run if any changed
                frozen = check_frozen(args.frozen, names, cfg, econf)
                rec.say(f"Frozen configurations '{args.frozen}' verified ({len(names)} configs"
                        + ("; the swarm code changed since the freeze" if frozen["code_changed"] else "") + ")")
            # benchmark sets: block the sites that publish the answer keys
            if qmeta.get("block_domains"):
                cfg["research"]["block_domains"] = list(qmeta["block_domains"])
            budget = None
            if getattr(args, "budget_tokens", None) or getattr(args, "budget_seconds", None):
                budget = {"max_output_tokens": args.budget_tokens, "max_seconds": args.budget_seconds}
                cfg["budget"] = dict(budget)
            meta = {"started": (json.loads((out / "meta.json").read_text(encoding="utf-8"))["started"] + " (resumed "
                                + dt.datetime.now().strftime("%H:%M") + ")") if resume_dir
                    else dt.datetime.now().strftime("%Y-%m-%d %H:%M"), "question_set": str(qpath),
                    "configs": names, "repeats": args.repeats, "judge": None if args.no_judge else judge_cfg.get("model"),
                    "evidence": ("live: every run does its own planning and web research" if args.live
                                 else f"reused from {args.reuse_evidence}" if args.reuse_evidence else "fresh"),
                    "live": bool(args.live),
                    "time_target": econf.get("time_target_seconds", 90),
                    "benchmark": qmeta.get("benchmark"), "grading": qmeta.get("grading"),
                    "block_domains": qmeta.get("block_domains"), "budget": budget, "frozen": frozen,
                    "judge2": (econf.get("judge2") or {}).get("model") if getattr(args, "judge2", False) else None,
                    "question_ids": [q["id"] for q in questions]}
            (out / "meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
            done = {(r["config"], r["question_id"], r.get("repeat", 0)) for r in results}
            rec.say(f"Evaluation: {len(questions)} questions x {len(names)} configs x {args.repeats} repeat(s) -> {out}"
                    + (f" - resuming, {len(done)} runs already done" if resume_dir else ""))

            # 0. preflight: every model the remaining configurations need must load and answer
            bad_models: dict[str, str] = {}
            if not getattr(args, "no_preflight", False):
                from swarm import preflight as pf
                need = []
                # models served by other machines (gpu.remote_models), across all configurations
                remote_all: dict = dict(cfg["gpu"].get("remote_models") or {})
                for name in names:
                    remote_all.update((_merge(copy.deepcopy(cfg), econf["configs"][name].get("overrides") or {})
                                       .get("gpu") or {}).get("remote_models") or {})
                pool.set_remote(remote_all)
                for name in names:
                    if all((name, q["id"], n) in done for q in questions for n in range(args.repeats)):
                        continue
                    variant = _merge(copy.deepcopy(cfg), econf["configs"][name].get("overrides") or {})
                    need += pf.models_for(variant, cards)
                if not args.no_judge:
                    need += pf.judge_models(econf, bool(meta.get("judge2")))
                need = [m for m in dict.fromkeys(need) if m in cards]
                # preflight CPU-resident models the way they will run (on the CPU)
                pool.cpu_models = list(dict.fromkeys(
                    str(m).lower() for name in names for m in
                    ((_merge(copy.deepcopy(cfg), econf["configs"][name].get("overrides") or {}).get("gpu") or {})
                     .get("cpu_models") or [])))
                bad_models = await pf.preflight(
                    need, pool, cards, [m.lower() for m in cfg["gpu"].get("keep_reasoning_models", ["gpt-oss"])],
                    say=rec.say)
                if bad_models:
                    rec.say("Preflight: configurations that use " + ", ".join(bad_models) + " will be skipped "
                            "(fix the model, then Resume-Last-Eval runs them)")
                meta["preflight_failed"] = bad_models
                (out / "meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")

            # 1. shared evidence
            ev_dir = out / "evidence"
            ev_dir.mkdir(exist_ok=True)
            reuse = repo_path(args.reuse_evidence) / "evidence" if args.reuse_evidence and not args.live else None
            prepared = {}
            need_web = args.live or not reuse or any(not (reuse / f"{q['id']}.json").exists() for q in questions)
            # manager-mode configs search the web during the run (follow-up searches), even on reused sources
            need_web = need_web or any(
                _merge(copy.deepcopy(cfg), econf["configs"][n].get("overrides") or {}).get("mode") == "manager"
                for n in names)
            if need_web and research_mcp_available(cfg):
                try:
                    research = ResearchMCP(cfg["research"].get("fetch_workers", 3))
                    await research.start()
                except Exception as e:
                    rec.say(f"research-mcp did not start ({e}); using built-in web search")
                    research = DirectResearch()
            elif need_web:
                research = DirectResearch()
            base = Swarm(cfg, pool, cards, research)
            for q in ([] if args.live else questions):  # live runs research for themselves
                src = reuse / f"{q['id']}.json" if reuse else None
                if src and src.exists():
                    prepared[q["id"]] = json.loads(src.read_text(encoding="utf-8"))
                    rec.say(f"evidence {q['id']}: reused")
                else:
                    t0 = time.time()
                    for attempt in range(3):  # a question with no web sources tests nothing: try again
                        prepared[q["id"]] = await base.prepare(q["question"], rec.emit)
                        web_ok = sum(1 for d in prepared[q["id"]]["docs"]
                                      if d["source"] == "web" and not d["error"] and d["text"])
                        if web_ok >= 2:
                            break
                        rec.say(f"evidence {q['id']}: only {web_ok} web pages, retrying in 10s")
                        await asyncio.sleep(10)
                    ok = sum(1 for d in prepared[q["id"]]["docs"] if not d["error"] and d["text"])
                    rec.say(f"evidence {q['id']}: {ok} sources ({web_ok} web) in {time.time() - t0:.0f}s "
                            f"({len(prepared[q['id']]['plan']['subquestions'])} sub-questions)")
                (ev_dir / f"{q['id']}.json").write_text(json.dumps(prepared[q["id"]], indent=1), encoding="utf-8")

            # 2. every configuration on the same evidence
            traces = out / "traces"
            for name in names:
                c = econf["configs"][name]
                variant = _merge(copy.deepcopy(cfg), c.get("overrides") or {})
                sw = Swarm(variant, pool, cards, research)
                problems = sw.check_roster()
                if bad_models:
                    from swarm import preflight as pf
                    problems += [f"{m} failed the preflight ({bad_models[m]})"
                                 for m in pf.models_for(variant, cards) if m in bad_models]
                if problems:
                    rec.say(f"SKIP {name}: {'; '.join(problems)}")
                    continue
                todo = [(q, n) for q in questions for n in range(args.repeats) if (name, q["id"], n) not in done]
                if not todo:
                    rec.say(f"== {name}: already done")
                    continue
                await pool.unload_all()  # each configuration starts from an empty GPU
                # models allowed to think (llama-server started without --reasoning-budget 0)
                pool.keep_reasoning = [m.lower() for m in
                                       (variant.get("gpu") or {}).get("keep_reasoning_models", ["gpt-oss"])]
                # models this configuration runs on the CPU (e.g. a resident leader); one pool serves all
                pool.cpu_models = [str(m).lower() for m in (variant.get("gpu") or {}).get("cpu_models") or []]
                # models this configuration uses from another machine on the network
                pool.set_remote((variant.get("gpu") or {}).get("remote_models") or {})
                rec.say(f"== {name}: {c.get('description', '')}")
                fails = 0
                for q in questions:
                    for rep in range(args.repeats):
                        if (name, q["id"], rep) in done:
                            continue
                        if fails >= 3:  # e.g. a model this llama.cpp build cannot load: don't waste the night
                            r = {"config": name, "config_description": c.get("description", ""), "question_id": q["id"],
                                 "question": q["question"], "repeat": rep, "mode": None, "answer": "", "sources": [],
                                 "n_citations": 0, "stats": {}, "total_seconds": None, "peak_vram_mb": None,
                                 "workers": [], "error": "skipped: this configuration failed 3 runs in a row"}
                            results.append(r)
                            write_results(out / "results.jsonl", results)
                            continue
                        await rec.reset_peak()
                        # watchdog: one stuck question (a hung site or model) must not stall the whole night
                        limit = float(c.get("run_timeout_seconds") or econf.get("run_timeout_seconds", 1500))
                        try:
                            if args.live:
                                # the real task: this configuration plans, searches, reads and answers itself
                                trace = await asyncio.wait_for(
                                    sw.run(q["question"], rec.emit, force_research=True, save_dir=traces), limit)
                            else:
                                trace = await asyncio.wait_for(
                                    sw.run(q["question"], rec.emit, prepared=prepared[q["id"]], save_dir=traces), limit)
                        except asyncio.TimeoutError:
                            trace = {"error": f"run timed out after {limit:.0f}s", "config": variant, "mode": sw.mode(),
                                     "stats": {}, "trace_file": ""}
                            rec.say(f"  {q['id']}: gave up after {limit:.0f}s")
                        await rec.sample_once()
                        r = summarize_run(name, c.get("description", ""), q, rep, trace, rec.peak_mb,
                                          f"traces/{trace.get('trace_file', '')}")
                        r["peak_ram_mb"] = rec.peak_ram_mb or None
                        r["min_free_ram_mb"] = rec.min_free_ram_mb
                        results.append(r)
                        write_results(out / "results.jsonl", results)
                        fails = fails + 1 if r.get("error") else 0
                        status = "ERROR " + r["error"][:120] if r.get("error") else f"{r['total_seconds']}s, {r['n_citations']} sources cited"
                        rec.say(f"  {q['id']}{' #' + str(rep + 1) if args.repeats > 1 else ''}: {status}")

        # 3. grade
        pool.cpu_models = [str(m).lower() for m in cfg["gpu"].get("cpu_models") or []]
        pool.set_remote(cfg["gpu"].get("remote_models") or {})
        if not args.no_judge and results:
            if not getattr(args, "attempts_only", False):
                await judge_all(results, qmap, pool, judge_cfg, rec, force=bool(args.regrade),
                                save=lambda: write_results(out / "results.jsonl", results))
            await grade_attempts(out, results, qmap, pool, judge_cfg, rec,
                                 save=lambda: write_results(out / "results.jsonl", results))
            meta["judge"] = judge_cfg.get("model")
            # optional second judge from a different model family: a cross-check on the first judge,
            # needed when the first judge's own model is also one of the contestants
            j2 = econf.get("judge2") if (getattr(args, "judge2", False) or meta.get("judge2")) else None
            if j2:
                await judge_all(results, qmap, pool, j2, rec, force=False,
                                save=lambda: write_results(out / "results.jsonl", results), key="grade2")
                meta["judge2"] = j2.get("model")
                (out / "meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
            write_results(out / "results.jsonl", results)
        build_report(out, results, meta)
        rec.say(f"Report: {out / 'report.html'}")
        return out
    finally:
        if research:
            await research.close()
        await pool.shutdown()
        await rec.stop()


DEFAULT_SET = "evals/research_v3.yaml"
FROZEN_DIR = REPO / "evals" / "frozen"


def _resolved(name: str, cfg: dict, econf: dict) -> dict:
    return _merge(copy.deepcopy(cfg), econf["configs"][name].get("overrides") or {})


def _hash(obj) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True, default=str).encode("utf-8")).hexdigest()


def _code_hashes() -> dict:
    files = sorted((REPO / "swarm").glob("*.py"))
    return {f.name: hashlib.sha256(f.read_bytes().replace(b"\r\n", b"\n")).hexdigest()[:16] for f in files}


def freeze(name: str, names: list[str], cfg: dict, econf: dict) -> Path:
    """Record exactly which configurations will be tested BEFORE their results are seen (a
    pre-registration). Commit the file to git so its date is on record."""
    FROZEN_DIR.mkdir(parents=True, exist_ok=True)
    path = FROZEN_DIR / f"{name}.json"
    if path.exists():
        raise SystemExit(f"{path} already exists: a freeze is never overwritten. Pick a new name.")
    configs = {n: {"description": econf["configs"][n].get("description", ""),
                   "overrides": econf["configs"][n].get("overrides") or {},
                   "hash": _hash(_resolved(n, cfg, econf))} for n in names}
    code = _code_hashes()
    doc = {"name": name, "frozen_at": dt.datetime.now().astimezone().isoformat(timespec="seconds"),
           "purpose": "configurations fixed before any GAIA/FRAMES results were seen",
           "configs": configs, "code_hash": _hash(code), "code_files": code}
    doc["manifest_hash"] = _hash({k: doc[k] for k in ("name", "configs", "code_hash")})
    path.write_text(json.dumps(doc, indent=2), encoding="utf-8")
    return path


def check_frozen(name: str, names: list[str], cfg: dict, econf: dict) -> dict:
    path = FROZEN_DIR / f"{name}.json"
    if not path.exists():
        raise SystemExit(f"no frozen manifest {path}")
    doc = json.loads(path.read_text(encoding="utf-8"))
    missing = [n for n in names if n not in doc["configs"]]
    changed = [n for n in names if n in doc["configs"] and doc["configs"][n]["hash"] != _hash(_resolved(n, cfg, econf))]
    if missing or changed:
        raise SystemExit(f"configurations differ from the frozen manifest '{name}': "
                         f"not in it: {missing or 'none'}; changed since the freeze: {changed or 'none'}")
    code = _code_hashes()
    return {"name": name, "manifest_hash": doc["manifest_hash"], "frozen_at": doc["frozen_at"],
            "code_changed": _hash(code) != doc["code_hash"],
            "code_files_changed": sorted(k for k in set(code) | set(doc["code_files"])
                                         if code.get(k) != doc["code_files"].get(k))}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m swarm.evals", description="Run the swarm test questions and grade them.")
    ap.add_argument("--set", default=DEFAULT_SET, help="question file (or a benchmark set in runtime/benchmarks)")
    ap.add_argument("--configs", help="comma-separated config names from evals/configs.yaml")
    ap.add_argument("--questions", help="comma-separated question ids (default: all)")
    ap.add_argument("--repeats", type=int, default=1, help="runs per question per config")
    ap.add_argument("--reuse-evidence", help="earlier eval folder whose sources to reuse")
    ap.add_argument("--live", action="store_true",
                    help="every run does its own planning and web research (the real task; noisier)")
    ap.add_argument("--regrade", help="earlier eval folder (or 'last') to grade and report again, no new runs")
    ap.add_argument("--resume", help="interrupted eval folder (or 'last') to continue where it stopped")
    ap.add_argument("--no-judge", action="store_true", help="skip grading")
    ap.add_argument("--no-open", action="store_true", help="don't open the report in the browser")
    ap.add_argument("--budget-tokens", type=int, help="normalized run: max tokens a whole run may write")
    ap.add_argument("--budget-seconds", type=float, help="normalized run: max wall time per run")
    ap.add_argument("--freeze", help="record the --configs as a frozen manifest evals/frozen/<name>.json and exit")
    ap.add_argument("--frozen", help="only run if the configs match this frozen manifest")
    ap.add_argument("--no-preflight", action="store_true",
                    help="don't try every model before the run (see swarm/preflight.py)")
    ap.add_argument("--attempts-only", action="store_true",
                    help="with --regrade: keep the existing grades and only grade the individual attempts of "
                         "multi-attempt runs (manager.attempts)")
    ap.add_argument("--judge2", action="store_true",
                    help="also grade every answer with the second judge from evals/configs.yaml (a cross-check)")
    args = ap.parse_args(argv)
    if args.freeze:
        econf = expand_configs(yaml.safe_load((REPO / "evals" / "configs.yaml").read_text(encoding="utf-8")))
        names = []
        for n in (args.configs or "").split(","):
            if n.strip():
                names += econf.get("groups", {}).get(n.strip(), [n.strip()])
        unknown = [n for n in names if n not in econf["configs"]]
        if not names or unknown:
            raise SystemExit(f"--freeze needs --configs with known names (unknown: {unknown})")
        path = freeze(args.freeze, names, load_config(), econf)
        print(f"Frozen {len(names)} configurations -> {path}")
        return 0
    import logging
    logging.basicConfig(level=logging.WARNING)
    out = asyncio.run(run(args))
    if not args.no_open:
        webbrowser.open((out / "report.html").as_uri())
    return 0


if __name__ == "__main__":
    sys.exit(main())
