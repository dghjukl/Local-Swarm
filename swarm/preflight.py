"""Preflight: try every model an evaluation will use BEFORE the long run starts.

Each model is loaded the way the swarm loads it and asked two small things: a JSON answer (the
format the coordinator, workers and verifier must return) and a plain-text answer (the final
answer). A model that cannot load, whose chat template this llama.cpp build rejects, whose replies
the server cannot parse, or that will not produce JSON is caught here in about a minute instead of
failing 63 questions in a row in the middle of the night (HyperCLOVAX, Apriel, ERNIE, 2026-09-30).

The evaluation runs it automatically (skip with --no-preflight); configurations that use a model
that failed are skipped with the reason. Models that passed before are not tested again until the
model file, the llama-server program or the swarm's model-handling code changes
(runtime/preflight.json).

    python -m swarm.preflight --configs coordinator-bakeoff,round2-screen
    python -m swarm.preflight --models Olmo-3-7B-Instruct,NVIDIA-Nemotron-Nano-9B-v2
"""
from __future__ import annotations

import argparse
import asyncio
import copy
import datetime as dt
import hashlib
import json
import sys
import time
from pathlib import Path

from swarm import llm
from swarm.paths import REPO, RUNTIME

CACHE = RUNTIME / "preflight.json"
SCHEMA = {"type": "object", "properties": {"answer": {"type": "string"}}, "required": ["answer"]}
JSON_MSGS = [{"role": "system", "content": "You answer questions. Reply with a JSON object {\"answer\": ...}."},
             {"role": "user", "content": "What is the capital of France?"}]
TEXT_MSGS = [{"role": "user", "content": "What is the capital of France? Answer in one short sentence."}]


def models_for(variant: dict, cards: dict, econf: dict | None = None, judge2: bool = False) -> list[str]:
    """Every model a (resolved) configuration will load, in the order it first needs them."""
    from swarm.orchestrator import Swarm
    sw = Swarm(variant, None, cards, None)
    out = [] if sw.leaderless() else [variant["coordinator"]["model"]]
    if sw.mode() in ("swarm", "notebook", "manager"):
        out += sw.team() + [r["model"] for r in sw.roles()]
    out.append(variant["verifier"]["model"])
    expert = ((variant.get("manager") or {}).get("expert") or {}).get("model") if sw.mode() == "manager" else None
    if expert:
        out.append(expert)
    if sw.mode() == "manager":  # worker pairs of extra attempts (manager.attempts.runs[].team)
        for r in (((variant.get("manager") or {}).get("attempts") or {}).get("runs") or []):
            out += list(r.get("team") or [])
    if (variant.get("research") or {}).get("reranker"):
        out.append(variant["research"]["reranker"])
    return [m for m in dict.fromkeys(out) if m in cards]


def judge_models(econf: dict, judge2: bool) -> list[str]:
    js = [(econf.get("judge") or {}).get("model")]
    if judge2:
        js.append((econf.get("judge2") or {}).get("model"))
    return [j for j in js if j]


def _sig(card, pool) -> str:
    """Changes when anything that decides how the model is served changes."""
    p = Path(card.path)
    st = p.stat() if p.exists() else None
    code = b"".join((REPO / "swarm" / f).read_bytes() for f in ("llm.py", "pool.py"))
    tmpl = b"".join(t.read_bytes() for t in sorted((REPO / "config" / "templates").glob("*.jinja")))
    exe = Path(str(pool._exe_for(card)))
    parts = [card.path, st.st_size if st else 0, int(st.st_mtime) if st else 0,
             str(exe), int(exe.stat().st_mtime) if exe.exists() else 0,
             hashlib.sha256(code + tmpl).hexdigest()]
    return hashlib.sha256(json.dumps(parts, default=str).encode()).hexdigest()[:16]


def _load_cache() -> dict:
    try:
        return json.loads(CACHE.read_text(encoding="utf-8"))
    except Exception:
        return {}


async def check_model(pool, card, keep_reasoning: list[str]) -> tuple[bool, str, float]:
    """(ok, what went wrong or what it answered, seconds)."""
    t0 = time.time()
    pool.keep_reasoning = keep_reasoning
    try:
        await pool.unload_all()
        async with pool.use(card.id, 4096, 1, pin=True) as url:
            if card.kind in ("embedding", "reranker"):
                return True, "loads", time.time() - t0
            if card.kind == "guard" or "guardian" in card.id.lower():
                res = await llm.chat(url, TEXT_MSGS, max_tokens=60, temperature=0.0, timeout=180)
                return True, f"loads, replies ({res.text[:40]!r})", time.time() - t0
            res = await llm.chat_json(url, JSON_MSGS, SCHEMA, max_tokens=300, temperature=0.0, timeout=240)
            if not isinstance(res.data, dict) or not str(res.data.get("answer", "")).strip():
                return False, f"JSON reply without an answer: {res.text[:120]!r}", time.time() - t0
            txt = await llm.chat(url, TEXT_MSGS, max_tokens=300, temperature=0.0, timeout=240, final=True)
            if not txt.text.strip():
                return False, "empty plain-text reply (everything went into hidden thinking?)", time.time() - t0
            warn = ""
            if card.id.lower() not in " ".join(keep_reasoning) and (res.reasoning or txt.reasoning):
                # it thought although thinking was switched off: long questions may run out of tokens
                warn = f" WARNING: thinks anyway ({len(res.reasoning) + len(txt.reasoning)} chars)"
            return True, f"JSON {res.data['answer'][:30]!r}, text {txt.text.strip()[:40]!r}{warn}", time.time() - t0
    except Exception as e:
        msg = f"{type(e).__name__}: {e}"
        # llama-server's load errors are long: keep the line that says what went wrong
        for key in ("unknown model architecture", "chat template parsing error", "does not match the expected",
                    "grammar", "out of memory", "exited while loading"):
            i = msg.find(key)
            if i >= 0 and key != "exited while loading":
                msg = msg[max(0, i - 20):i + 200]
                break
        return False, " ".join(msg.split())[:300], time.time() - t0
    finally:
        try:
            await pool.unload_all()
        except Exception:
            pass


async def preflight(models: list[str], pool, cards: dict, keep_reasoning: list[str], say=print,
                    force: bool = False) -> dict[str, str]:
    """Checks the models; returns {model: reason} for the ones that FAILED (empty dict = all good)."""
    cache = _load_cache()
    bad: dict[str, str] = {}
    todo = []
    for m in models:
        if cards[m].size_mb > pool.budget_mb:  # would load partly into RAM: slow, and it restarted this PC
            say(f"Preflight: {m} not tested (bigger than the GPU budget)")
            continue
        sig = _sig(cards[m], pool) + ("-cpu" if pool.on_cpu(cards[m]) else "")  # CPU and GPU runs differ
        if pool.is_remote(m):  # served by another machine: what matters is where
            sig = "remote:" + pool.remote_models[m]["url"]
        hit = cache.get(m)
        if not force and hit and hit.get("sig") == sig and hit.get("ok"):
            continue
        todo.append((m, sig))
    if not todo:
        say(f"Preflight: all {len(models)} models passed before (nothing changed since)")
        return bad
    say(f"Preflight: trying {len(todo)} of {len(models)} models before the run (about 30 s each) ...")
    for m, sig in todo:
        ok, why, secs = await check_model(pool, cards[m], keep_reasoning)
        say(f"  {'ok  ' if ok else 'FAIL'} {m} ({secs:.0f}s): {why}")
        cache[m] = {"sig": sig, "ok": ok, "detail": why, "checked": dt.datetime.now().strftime("%Y-%m-%d %H:%M")}
        CACHE.parent.mkdir(parents=True, exist_ok=True)
        CACHE.write_text(json.dumps(cache, indent=1), encoding="utf-8")
        if not ok:
            bad[m] = why
    return bad


def main(argv: list[str] | None = None) -> int:
    import yaml
    from swarm.config import load_config
    from swarm.evals import _merge, expand_configs
    from swarm.pool import ModelPool
    from swarm.registry import scan_models
    ap = argparse.ArgumentParser(prog="python -m swarm.preflight")
    ap.add_argument("--configs", help="config or group names from evals/configs.yaml")
    ap.add_argument("--models", help="model names (instead of --configs)")
    ap.add_argument("--judge2", action="store_true", help="also check the second judge")
    ap.add_argument("--force", action="store_true", help="test again even if a model passed before")
    a = ap.parse_args(argv)
    cfg, cards = load_config(), scan_models()
    econf = expand_configs(yaml.safe_load((REPO / "evals" / "configs.yaml").read_text(encoding="utf-8")))
    models: list[str] = []
    if a.models:
        models = [m.strip() for m in a.models.split(",") if m.strip()]
    for n in (a.configs or "").split(","):
        for name in econf.get("groups", {}).get(n.strip(), [n.strip()] if n.strip() else []):
            variant = _merge(copy.deepcopy(cfg), econf["configs"][name].get("overrides") or {})
            models += models_for(variant, cards)
    if a.configs:
        models += judge_models(econf, a.judge2)
    missing = [m for m in models if m not in cards]
    models = [m for m in dict.fromkeys(models) if m in cards]
    if missing:
        print(f"Not in Models/ (download with Sync-Models): {', '.join(dict.fromkeys(missing))}")
    keep = [m.lower() for m in cfg["gpu"].get("keep_reasoning_models", ["gpt-oss"])]

    async def go():
        pool = ModelPool(cfg, cards)
        try:
            return await preflight(models, pool, cards, keep, force=a.force)
        finally:
            await pool.shutdown()
    bad = asyncio.run(go())
    print("\nAll models passed." if not bad else f"\n{len(bad)} model(s) failed: {', '.join(bad)}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
