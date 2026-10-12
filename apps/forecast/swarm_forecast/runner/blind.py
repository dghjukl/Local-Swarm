"""Stage 'blind': a forecast for each question with no price shown."""
from __future__ import annotations

import time
from datetime import datetime, timezone

from swarm_forecast.questions import blind_question
from swarm_forecast.store import RecordLog

MAX_ATTEMPTS = 2


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


async def run_blind(markets: list[dict], session, log: RecordLog, today: str, progress=None) -> dict:
    prior = log.read()
    ok = {str(r["market_id"]) for r in prior if r.get("probability") is not None}
    attempts: dict[str, int] = {}
    for r in prior:
        attempts[str(r["market_id"])] = attempts.get(str(r["market_id"]), 0) + 1
    done = failed = 0
    gate = None
    first_five_fetches = first_five_extraction_failures = 0
    for m in markets:
        mid = str(m["market_id"])
        if mid in ok or attempts.get(mid, 0) >= MAX_ATTEMPTS:
            continue
        rec = await session.forecast(blind_question(m, today), "blind")
        rec.update(stage="blind", forecast_time=now_iso(), attempt=attempts.get(mid, 0) + 1,
                   question=m.get("question", ""))
        log.append(rec)
        done += 1
        failed += int(rec.get("probability") is None)
        if done <= 5:
            fs = rec.get("fetch_stats") or {}
            first_five_fetches += int(fs.get("total", 0))
            first_five_extraction_failures += int(fs.get("extraction_failed", 0))
            if first_five_fetches and first_five_extraction_failures / first_five_fetches > 0.5:
                gate = {"stop": True, "reason": "extraction_failure_rate", "observed": done,
                        "fetches": first_five_fetches, "extraction_failures": first_five_extraction_failures,
                        "rate": first_five_extraction_failures / first_five_fetches}
                break
        if progress:
            progress("blind", mid, rec)
        observed = log.read()
        if len(observed) >= 30:
            first = observed[:30]
            no_forecasts = sum(bool(r.get("no_forecast")) for r in first)
            if no_forecasts / 30 > 0.25:
                gate = {"stop": True, "observed": 30, "no_forecast": no_forecasts,
                        "rate": no_forecasts / 30,
                        "reasons": {k: sum(1 for r in first if r.get("no_forecast_reason") == k)
                                    for k in sorted({r.get("no_forecast_reason") for r in first if r.get("no_forecast_reason")})}}
                break
    return {"ran": done, "failed": failed, "gate": gate}
