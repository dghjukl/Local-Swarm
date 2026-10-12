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
        if progress:
            progress("blind", mid, rec)
    return {"ran": done, "failed": failed}
