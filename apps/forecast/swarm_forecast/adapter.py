"""The single boundary between this application and the swarm.

`forecast(question, mode, config)` is the stable synchronous entry point (config["session"] is a
SwarmSession). `SwarmSession` owns the swarm pieces (model pool, model cards, research client) for one
cycle, so models stay warm across questions, and maps a swarm run onto the forecast contract:

    {"probability": float, "reasons": [str], "key_uncertainty": str, "market_may_be_missing": str,
     "trace_file": str, "swarm_stamp": dict, "seconds": float, "error": str | None, ...}
"""
from __future__ import annotations

import asyncio
import copy
import re
import time
from pathlib import Path
from typing import Any, Awaitable, Callable

from swarm_forecast import prompts
from swarm_forecast.questions import find_leaks


def deep_merge(base: dict, over: dict) -> dict:
    out = copy.deepcopy(base)
    for k, v in (over or {}).items():
        out[k] = deep_merge(out[k], v) if isinstance(v, dict) and isinstance(out.get(k), dict) else copy.deepcopy(v)
    return out


def validate_question(question: dict, mode: str) -> None:
    if mode not in {"blind", "informed"}:
        raise ValueError("mode must be 'blind' or 'informed'")
    if mode == "blind":
        leaked = find_leaks(question)
        if leaked:
            raise ValueError(f"blind question contains market fields: {sorted(leaked)}")
    elif not question.get("market_state"):
        raise ValueError("informed question needs market_state")


def parse_probability(text: str) -> float | None:
    """Fallback: the last 'NN%' or 'probability: 0.NN' in a free-text answer."""
    m = re.findall(r"(?:probability|chance|likelihood)[^0-9]{0,40}(\d{1,3}(?:\.\d+)?)\s*%", text or "", re.I)
    if m:
        return min(0.99, max(0.01, float(m[-1]) / 100))
    m = re.findall(r"(\d{1,3}(?:\.\d+)?)\s*%", text or "")
    return min(0.99, max(0.01, float(m[-1]) / 100)) if m else None


def explicit_yes_probability(text: str) -> float | None:
    """Read an explicit estimate of the market question resolving YES from research prose."""
    patterns = (
        r"(?:probability|chance|likelihood|estimate)[^\n]{0,80}?([0-9]{1,3}(?:\.\d+)?)\s*%[^\n]{0,30}\bYES\b",
        r"([0-9]{1,3}(?:\.\d+)?)\s*%\s*(?:probability|chance|likelihood)\s+of\s+YES\b",
    )
    for pattern in patterns:
        found = re.findall(pattern, text or "", re.I)
        if found:
            return clamp(float(found[-1]) / 100)
    return None


def clamp(p: float, lo: float = 0.01, hi: float = 0.99) -> float:
    return min(hi, max(lo, float(p)))


def normalize_forecast(raw: dict | None, answer: str) -> tuple[float | None, dict]:
    d = raw if isinstance(raw, dict) else {}
    p = d.get("probability")
    try:
        p = float(p)
        if p > 1.0:  # a model that answered in percent
            p = p / 100.0
    except (TypeError, ValueError):
        p = parse_probability(answer)
    reasons = [str(x)[:300] for x in (d.get("reasons") or []) if str(x).strip()][:4]
    return (clamp(p) if p is not None else None), {
        "reasons": reasons, "key_uncertainty": str(d.get("key_uncertainty", ""))[:300],
        "market_may_be_missing": str(d.get("market_may_be_missing", ""))[:400]}


Factory = Callable[[dict], Awaitable[Any]]


class SwarmSession:
    """One cycle's connection to the swarm for one stage configuration.

    factory(overrides) -> object with .swarm (has .run, .pool, .role), .close(), .stamp (dict).
    Tests inject a fake factory; the real one is `real_factory`.
    """

    def __init__(self, overrides: dict | None = None, factory: Factory | None = None, extractor=None,
                 save_dir: str | Path = "data/traces", stamp_args: dict | None = None):
        self.overrides = overrides or {}
        self.factory = factory or real_factory
        self.extractor = extractor            # async (handle, question, mode, answer, notes) -> raw dict
        self.save_dir = Path(save_dir)
        self.stamp_args = stamp_args or {}
        self.handle = None

    async def start(self) -> None:
        if self.handle is None:
            self.handle = await self.factory(self.overrides)

    async def close(self) -> None:
        if self.handle is not None:
            await self.handle.close()
            self.handle = None

    async def forecast(self, question: dict, mode: str) -> dict:
        validate_question(question, mode)
        await self.start()
        t0 = time.time()
        out: dict = {"market_id": question.get("market_id"), "mode": mode, "probability": None, "reasons": [],
                     "key_uncertainty": "", "market_may_be_missing": "", "trace_file": "",
                     "swarm_stamp": dict(getattr(self.handle, "stamp", {}) or {}), "error": None}
        try:
            self.save_dir.mkdir(parents=True, exist_ok=True)
            events: list = []

            async def emit(e):  # the swarm streams events; the app only keeps the final trace
                events.append(e)

            trace = await self.handle.swarm.run(prompts.research_question(question, mode), emit,
                                                force_research=True, save_dir=self.save_dir)
            if not isinstance(trace, dict) or trace.get("error"):
                raise RuntimeError((trace or {}).get("error") if isinstance(trace, dict) else "no trace")
            answer = ((trace.get("final") or {}).get("answer")) or ""
            notes = [n.get("fact", "") for n in ((trace.get("manager") or {}).get("notes") or [])
                     if n.get("status") != "unsupported"][:15]
            extract = self.extractor or default_extractor
            raw = await extract(self.handle, question, mode, answer, notes)
            p, parts = normalize_forecast(raw, answer)
            explicit = explicit_yes_probability(answer)
            if explicit is not None and p is not None and abs(p - explicit) > 0.20:
                retry = await extract(self.handle, question, mode, answer,
                                      notes + [f"The research text explicitly estimates {explicit:.0%} probability of YES. Reconcile the JSON probability with that estimate."])
                p, parts = normalize_forecast(retry, answer)
                if p is None or abs(p - explicit) > 0.20:
                    p = None
                    parts["inconsistent"] = True
                    parts["inconsistent_reason"] = f"extracted probability disagreed with explicit YES estimate {explicit:.0%}"
            if not notes:
                p = None
                parts["no_forecast"] = True
                parts["no_forecast_reason"] = "no research findings were recorded"
            out.update(parts)
            out["probability"] = p
            out["trace_file"] = str(trace.get("trace_file") or (trace.get("final") or {}).get("trace") or "")
            out["research_summary"] = answer[:1200]
            out["swarm_seconds"] = ((trace.get("stats") or {}).get("total_seconds"))
            if p is None:
                out["error"] = "no probability could be extracted"
        except asyncio.CancelledError:
            raise
        except Exception as e:  # a failed question is data, never a crash of the cycle
            out["error"] = f"{type(e).__name__}: {e}"[:300]
        out["seconds"] = round(time.time() - t0, 1)
        return out


def forecast(question: dict, mode: str, config: dict) -> dict:
    """Stable synchronous entry point; config['session'] is a SwarmSession."""
    validate_question(question, mode)
    session = config.get("session")
    if session is None:
        raise RuntimeError("config['session'] must be a SwarmSession")
    return asyncio.run(session.forecast(question, mode))


async def coordinator_json(handle, system: str, user: str, schema: dict, max_tokens: int = 600) -> dict:
    """One grammar-constrained JSON call to the session's coordinator model."""
    from swarm import llm
    sw = handle.swarm
    coord = sw.role("coordinator")
    msgs = [{"role": "system", "content": system}, {"role": "user", "content": user}]
    async with sw.pool.use(coord["model"], coord["ctx_per_slot"], coord["parallel"], pin=False) as url:
        res = await llm.chat_json(url, msgs, schema, max_tokens=max_tokens, temperature=0.0)
    return res.data if isinstance(res.data, dict) else {}


async def default_extractor(handle, question: dict, mode: str, answer: str, notes: list[str]) -> dict:
    """The coordinator turns the swarm's findings into the JSON forecast."""
    return await coordinator_json(handle, prompts.FORECAST_SYSTEM,
                                  prompts.extraction_user(question, mode, answer, notes), prompts.FORECAST_SCHEMA)


class _RealHandle:
    def __init__(self, swarm, pool, research, stamp):
        self.swarm, self.pool, self.research, self.stamp = swarm, pool, research, stamp

    async def close(self) -> None:
        try:
            await self.pool.shutdown()
        finally:
            closer = getattr(self.research, "close", None)
            if closer:
                r = closer()
                if asyncio.iscoroutine(r):
                    await r


async def real_factory(overrides: dict) -> _RealHandle:
    """Builds the real swarm the way the eval runner does (swarm package from the pinned checkout)."""
    from swarm.config import load_config
    from swarm.orchestrator import Swarm
    from swarm.pool import ModelPool
    from swarm.registry import scan_models
    from swarm.tools import DirectResearch

    cfg = deep_merge(load_config(), {k: v for k, v in overrides.items() if not k.startswith("_")})
    cards = scan_models()

    async def quiet(e):
        pass

    pool = ModelPool(cfg, cards, emit=quiet)
    pool.set_remote(dict((cfg.get("gpu") or {}).get("remote_models") or {}))
    research = DirectResearch()
    sw = Swarm(cfg, pool, cards, research)
    problems = sw.check_roster()
    if problems:
        await pool.shutdown()
        raise RuntimeError("swarm roster problems: " + "; ".join(problems))
    from swarm_forecast.versioning import swarm_stamp
    import swarm as _swarm_pkg
    root = Path(_swarm_pkg.__file__).resolve().parent.parent
    stamp = swarm_stamp(root, config_name=str(overrides.get("_name", "custom")),
                        model_paths=[], app_version="0.1.0")
    return _RealHandle(sw, pool, research, stamp)
