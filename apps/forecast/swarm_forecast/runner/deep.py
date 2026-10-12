"""Stage 'deep': the picked questions get a full informed pass, price shown, on fresh quotes."""
from __future__ import annotations

import re
from datetime import date, datetime, timedelta

from swarm_forecast.questions import informed_question
from swarm_forecast.runner.blind import now_iso
from swarm_forecast.store import RecordLog


def side_numbers(market: dict, side: str, p_yes: float) -> tuple[float | None, float]:
    """(ask for that side, swarm probability for that side)."""
    ask = market.get("yes_ask") if side == "yes" else market.get("no_ask")
    return (None if ask is None else float(ask)), (p_yes if side == "yes" else 1.0 - p_yes)


def has_recent_dated_support(text: str, today: str, days: int = 30) -> bool:
    """Require a date in the research text no older than the guard window."""
    try:
        end = date.fromisoformat(today)
    except ValueError:
        end = date.today()
    for raw in re.findall(r"\b(20\d{2})[-/](\d{1,2})[-/](\d{1,2})\b|\b([A-Z][a-z]+) (\d{1,2}),? (20\d{2})\b", text or ""):
        try:
            if raw[0]:
                d = date(int(raw[0]), int(raw[1]), int(raw[2]))
            else:
                d = datetime.strptime(f"{raw[3]} {raw[4]} {raw[5]}", "%B %d %Y").date()
            if timedelta(days=0) <= end - d <= timedelta(days=days):
                return True
        except ValueError:
            continue
    return False


async def run_deep(picks: list[dict], markets: dict[str, dict], session, log: RecordLog, today: str,
                   refresh=None, confirm_margin: float = 0.05, progress=None) -> dict:
    done_ids = {str(r["market_id"]) for r in log.read()}
    ran = confirmed = 0
    for pk in picks:
        mid = str(pk["market_id"])
        if mid in done_ids:
            continue
        m = markets.get(mid)
        if m is None:
            continue
        fresh = await refresh(m) if refresh else m
        if fresh is None or fresh.get("closed") or fresh.get("stale"):
            log.append({"market_id": mid, "stage": "deep", "skipped": "stale_or_closed", "forecast_time": now_iso()})
            continue
        rec = await session.forecast(informed_question(fresh, today), "informed")
        side = pk.get("side")
        p = rec.get("probability")
        entry = {"yes_ask": fresh.get("yes_ask"), "no_ask": fresh.get("no_ask"), "last_price": fresh.get("last_price"),
                 "fetched_at": fresh.get("fetched_at")}
        rec.update(stage="deep", forecast_time=now_iso(), pick=pk, entry=entry, question=fresh.get("question", ""))
        if p is not None:
            # a pick keeps its side only if the deep pass still sees an edge on that side
            s = side
            if s is None:  # answerability picks carry no side: take the side with the larger deep gap
                gaps = {k: side_numbers(fresh, k, p) for k in ("yes", "no")}
                gaps = {k: (v[1] - v[0]) for k, v in gaps.items() if v[0] is not None}
                s = max(gaps, key=gaps.get) if gaps else None
            ask, ps = side_numbers(fresh, s, p) if s else (None, p)
            rec["side"] = s
            rec["side_ask"] = ask
            rec["side_probability"] = ps
            rec["confirmed"] = bool(ask is not None and ps - ask >= confirm_margin)
            extreme = ask is not None and (ask >= 0.85 or ask <= 0.15) and abs(ps - ask) > 0.40
            if extreme and not has_recent_dated_support(rec.get("research_summary", ""), today):
                rec["stale_suspect"] = True
                rec["stale_reason"] = "large disagreement with a confident market and no source dated within 30 days"
                rec["confirmed"] = False
            confirmed += int(rec["confirmed"])
        ran += 1
        log.append(rec)
        if progress:
            progress("deep", mid, rec)
    return {"ran": ran, "confirmed": confirmed}
