"""Verifier bench: which model is the best fact checker?

The verifier's job is one narrow decision: is this claim supported by the passages it cites? This
bench takes real claims that workers made in an earlier evaluation (with the exact passages they
cited), and asks every candidate verifier about each claim, one claim at a time.

There is no hand-made answer key, so the reference is two strong judges from different families
(by default Ministral-3-14B and gpt-oss-20b): only claims on which both agree are scored, and each
candidate is measured against that agreed label.

    python -m swarm.verifier_bench                          # latest eval with worker claims, 400 claims
    python -m swarm.verifier_bench --from runtime/evals/20260928-1323 --n 300
    python -m swarm.verifier_bench --verifiers Granite-4.1-3B,Granite-4.2-3B,Granite-Guardian-4.1-8B

Report: runtime/evals/verifier-bench-<time>/report.md (accuracy, how often it catches unsupported
claims, how often it wrongly rejects supported ones, speed).
"""
from __future__ import annotations

import argparse
import asyncio
import copy
import datetime as dt
import json
import random
import re
import sys
import time
from pathlib import Path

from swarm import llm
from swarm.json_gbnf import schema_to_gbnf
from swarm.config import load_config
from swarm.orchestrator import GUARDIAN_BLOCK, VERIFY_SCHEMA, VERIFY_SYSTEM, _fmt_passages
from swarm import evidence as ev
from swarm.paths import RUNTIME, repo_path
from swarm.pool import ModelPool
from swarm.registry import scan_models

DEFAULT_VERIFIERS = ["Granite-4.1-3B", "Granite-4.2-3B", "Granite-Guardian-4.1-8B", "Granite-4.2-8B",
                     "Qwen3.5-4B", "Ministral-3-3B-Instruct", "Gemma-4-E4B-it"]
DEFAULT_REFS = ["Ministral-3-14B-Instruct", "gpt-oss-20b"]

# One claim at a time, so exactly one verdict with a short reason. Without these limits a model
# can keep writing (long reasons, or extra made-up verdicts) until it runs out of tokens and gives
# no usable answer: Ministral-14B did that on 337 of 400 claims in the first run (2026-10-01).
# Ministral-3's chat format also allows a [THINK]...[/THINK] block before the JSON (llama.cpp puts
# it in the grammar), and it uses it: so every model gets the generous room (2400
# tokens), otherwise the thinkers run out before they reach the verdict (second run, 2026-10-02).
BENCH_SCHEMA = copy.deepcopy(VERIFY_SCHEMA)
BENCH_SCHEMA["properties"]["verdicts"].update(minItems=1, maxItems=1)
BENCH_SCHEMA["properties"]["verdicts"]["items"]["properties"]["reason"]["maxLength"] = 240
BENCH_SCHEMA["required"] = ["verdicts"]
ERRORS: dict[str, list[str]] = {}
# Ministral-3's chat template lets llama.cpp put an optional [THINK]...[/THINK] block before the
# JSON in its grammar, and in this bench Ministral-14B used it to think past 2400 tokens on most
# claims (third run, 2026-10-02). These models get a plain JSON grammar instead, so they answer
# straight away like the other candidates.
PLAIN_GRAMMAR_MODELS = ("Ministral",)
BENCH_GBNF = schema_to_gbnf(BENCH_SCHEMA)


def load_claims(folder: Path, n: int, seed: int = 7) -> list[dict]:
    """Claims from the traces of an earlier evaluation, each with the passages it cited."""
    items = []
    for f in sorted((folder / "traces").glob("*.json")):
        try:
            t = json.loads(f.read_text(encoding="utf-8"))
        except Exception:
            continue
        by_id = {p["id"]: p for p in t.get("evidence", []) or []}
        for w in t.get("worker_results", []) or []:
            for c in w.get("claims", []) or []:
                ids = [i for i in c.get("evidence", []) if i in by_id]
                if ids and c.get("claim"):
                    items.append({"claim": c["claim"], "passages": [by_id[i] for i in ids],
                                  "question": t.get("question", ""), "worker": w.get("base_model") or w.get("model"),
                                  "original_verdict": c.get("verdict")})
    uniq = {}
    for it in items:  # the same claim text over the same passages only once
        uniq.setdefault((it["claim"].strip().lower(), tuple(p["id"] for p in it["passages"]), it["question"]), it)
    items = list(uniq.values())
    random.Random(seed).shuffle(items)
    return items[:n]


def _passages(it: dict) -> str:
    ps = [ev.Passage(**({"source": "", **{k: p[k] for k in ev.Passage.__dataclass_fields__ if k in p}}))
          for p in it["passages"]]
    return _fmt_passages(ps)


async def ask(url: str, model: str, it: dict) -> tuple[str | None, float]:
    """'supported' / 'partial' / 'unsupported' (or None if the model gave nothing usable), seconds."""
    t0 = time.time()
    if "guardian" in model.lower():
        msgs = [{"role": "user", "content": f"Passages:\n{_passages(it)}\n\nState one fact from these passages."},
                {"role": "assistant", "content": it["claim"]},
                {"role": "user", "content": GUARDIAN_BLOCK}]
        res = await llm.chat(url, msgs, max_tokens=40, temperature=0.0)
        m = re.search(r"<score>\s*(yes|no)\s*</score>", (res.text or "") + (res.reasoning or ""), re.I)
        return (None if not m else "supported" if m.group(1).lower() == "yes" else "unsupported"), time.time() - t0
    user = f"Passages:\n{_passages(it)}\n\nClaims to check:\n1. {it['claim']}"
    try:
        res = await llm.chat_json(url, [{"role": "system", "content": VERIFY_SYSTEM}, {"role": "user", "content": user}],
                                  BENCH_SCHEMA, max_tokens=2400, temperature=0.0,
                                  gbnf=BENCH_GBNF if model.startswith(PLAIN_GRAMMAR_MODELS) else None)
        vs = [x for x in (res.data or {}).get("verdicts", []) if isinstance(x, dict)]
        if not vs:
            ERRORS.setdefault(model, []).append(f"empty verdict list: {res.text[:100]!r}")
        return (vs[0].get("verdict") if vs else None), time.time() - t0
    except Exception as e:
        ERRORS.setdefault(model, []).append(" ".join(f"{type(e).__name__}: {e}".split())[:200])
        return None, time.time() - t0


async def run(args) -> Path:
    cfg = load_config()
    cards = scan_models()
    if args.source:
        src = repo_path(args.source)
    else:  # the newest evaluation whose traces hold worker claims
        cands = sorted((p for p in (RUNTIME / "evals").glob("2*") if (p / "traces").exists()), reverse=True)
        src = next((p for p in cands if any('"claims"' in f.read_text(encoding="utf-8", errors="ignore")[:200000]
                                            for f in list((p / "traces").glob("*.json"))[:3])), None)
        if not src:
            raise SystemExit("no earlier evaluation with worker claims found")
    items = load_claims(src, args.n)
    out = RUNTIME / "evals" / ("verifier-bench-" + dt.datetime.now().strftime("%Y%m%d-%H%M"))
    out.mkdir(parents=True, exist_ok=True)
    models = [m for m in dict.fromkeys(args.refs + args.verifiers)]
    missing = [m for m in models if m not in cards]
    print(f"{len(items)} claims from {src}. Missing models (skipped): {missing or 'none'}", flush=True)
    pool = ModelPool(cfg, cards)
    pool.keep_reasoning = [m.lower() for m in cfg["gpu"].get("keep_reasoning_models", ["gpt-oss"])]
    answers: dict[str, list] = {}
    try:
        for m in models:
            if m not in cards:
                continue
            await pool.unload_all()
            sem = asyncio.Semaphore(2)
            t0 = time.time()
            try:
                async with pool.use(m, 8192, 2, pin=True) as url:
                    done = [0]

                    async def one(it):
                        async with sem:
                            r = await ask(url, m, it)
                        done[0] += 1
                        if done[0] % 50 == 0:  # show it is alive (each model takes minutes)
                            print(f"    {m}: {done[0]}/{len(items)} claims ({time.time() - t0:.0f}s)", flush=True)
                        return r
                    answers[m] = await asyncio.gather(*(one(it) for it in items))
            except Exception as e:  # one model that cannot load must not end the whole bench
                print(f"  {m}: FAILED ({' '.join(str(e).split())[:200]}); skipped", flush=True)
                continue
            got = sum(1 for v, _ in answers[m] if v)
            print(f"  {m}: {got}/{len(items)} verdicts in {time.time() - t0:.0f}s", flush=True)
            if ERRORS.get(m):  # show why answers were missing, so a broken run is noticed at once
                print(f"    {len(ERRORS[m])} without a verdict, e.g. {ERRORS[m][0]}", flush=True)
            (out / "answers.json").write_text(json.dumps({k: [v for v, _ in a] for k, a in answers.items()}), encoding="utf-8")
    finally:
        await pool.shutdown()
    build_report(out, items, answers, [r for r in args.refs if r in answers], src)
    print(f"Report: {out / 'report.md'}")
    return out


def _binary(v: str | None) -> bool | None:
    return None if v is None else v == "supported"


def build_report(out: Path, items: list[dict], answers: dict, refs: list[str], src: Path) -> None:
    if len(refs) >= 2:
        ref = [(_binary(answers[refs[0]][i][0]) if _binary(answers[refs[0]][i][0]) == _binary(answers[refs[1]][i][0]) else None)
               for i in range(len(items))]
    elif refs:
        ref = [_binary(answers[refs[0]][i][0]) for i in range(len(items))]
    else:
        ref = [None] * len(items)
    keep = [i for i, r in enumerate(ref) if r is not None]
    n_bad = sum(1 for i in keep if ref[i] is False)
    md = [f"# Verifier bench — {dt.datetime.now():%Y-%m-%d %H:%M}", "",
          f"{len(items)} real worker claims from `{src.name}`, each checked against the passages it cited.",
          f"Reference: {' + '.join(refs) or 'none'} — only the {len(keep)} claims where they agree are scored "
          f"({len(keep) - n_bad} supported, {n_bad} not supported).", "",
          "| Verifier | Accuracy | Catches unsupported | Wrongly rejects supported | No verdict | Avg time |",
          "|---|---|---|---|---|---|"]
    rows = []
    for m, a in answers.items():
        tp = sum(1 for i in keep if ref[i] is False and _binary(a[i][0]) is False)
        fn = sum(1 for i in keep if ref[i] is False and _binary(a[i][0]) is not False)
        fp = sum(1 for i in keep if ref[i] is True and _binary(a[i][0]) is False)
        correct = sum(1 for i in keep if _binary(a[i][0]) == ref[i])
        none = sum(1 for v, _ in a if v is None)
        secs = sum(s for _, s in a) / max(1, len(a))
        rows.append((correct / max(1, len(keep)), m, tp / max(1, tp + fn), fp / max(1, len(keep) - n_bad), none, secs))
    for acc, m, catch, false_rej, none, secs in sorted(rows, reverse=True):
        tag = " (reference)" if m in refs else ""
        md.append(f"| {m}{tag} | {acc:.0%} | {catch:.0%} | {false_rej:.0%} | {none} | {secs:.1f}s |")
    md += ["", "_Accuracy for the reference judges is inflated (they helped define the answer key)._"]
    (out / "report.md").write_text("\n".join(md) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m swarm.verifier_bench")
    ap.add_argument("--from", dest="source", help="evaluation folder whose worker claims to use")
    ap.add_argument("--n", type=int, default=400)
    ap.add_argument("--verifiers", default=",".join(DEFAULT_VERIFIERS))
    ap.add_argument("--refs", default=",".join(DEFAULT_REFS))
    a = ap.parse_args(argv)
    a.verifiers = [x.strip() for x in a.verifiers.split(",") if x.strip()]
    a.refs = [x.strip() for x in a.refs.split(",") if x.strip()]
    asyncio.run(run(a))
    return 0


if __name__ == "__main__":
    sys.exit(main())
