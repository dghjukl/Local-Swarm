"""Stage 'bets': paper bets from confirmed deep forecasts, settlement, and honest summaries. Paper only."""
from __future__ import annotations

import random
from math import prod


def decide_bets(deep: list[dict], margin: float = 0.10, fee: float = 0.0, stake: float = 1.0) -> list[dict]:
    """One flat bet per confirmed pick when the swarm's probability for a side beats that side's ask by `margin`."""
    bets = []
    for r in deep:
        if not r.get("confirmed") or r.get("side") is None or r.get("side_ask") in (None, 0):
            continue
        if r["side_probability"] - r["side_ask"] >= margin:
            bets.append({"market_id": str(r["market_id"]), "side": r["side"], "entry_price": float(r["side_ask"]),
                         "swarm_probability": float(r["side_probability"]), "stake": stake, "fee": fee,
                         "forecast_time": r.get("forecast_time"), "entry_fetched_at": (r.get("entry") or {}).get("fetched_at"),
                         "reason": ((r.get("pick") or {}).get("reason") or "")[:300]})
    return bets


def settle(bets: list[dict], outcomes: dict[str, str]) -> list[dict]:
    """outcomes: market_id -> 'yes' | 'no' | 'void' | None. Void and unresolved bets are not settled."""
    out = []
    for b in bets:
        o = outcomes.get(b["market_id"])
        if o not in ("yes", "no"):
            continue
        won = (o == b["side"])
        pnl = b["stake"] * (((1 - b["fee"]) / b["entry_price"] - 1) if won else -1.0)
        out.append({**b, "outcome": o, "won": won, "pnl": pnl})
    return out


def prob_at_least(hits: int, probs: list[float]) -> float:
    """P(number of wins >= hits) when each bet wins independently with the market-implied chance (exact DP)."""
    dist = [1.0]
    for p in probs:
        nxt = [0.0] * (len(dist) + 1)
        for k, v in enumerate(dist):
            nxt[k] += v * (1 - p)
            nxt[k + 1] += v * p
        dist = nxt
    return sum(dist[hits:]) if hits < len(dist) else 0.0


def summarize(settled: list[dict], draws: int = 10000, seed: int = 0) -> dict:
    n = len(settled)
    if n == 0:
        return {"bets": 0}
    rets = [s["pnl"] / s["stake"] for s in settled]
    rng = random.Random(seed)
    means = sorted(sum(rng.choice(rets) for _ in rets) / n for _ in range(draws))
    hits = sum(1 for s in settled if s["won"])
    implied = [s["entry_price"] for s in settled]
    cheap = [s for s in settled if s["entry_price"] < 0.5]
    return {
        "bets": n, "hits": hits, "hit_rate": hits / n, "roi": sum(rets) / n,
        "roi_ci95": (means[int(draws * 0.025)], means[int(draws * 0.975) - 1]),
        "avg_price_paid": sum(implied) / n,
        "expected_hits_at_market_odds": sum(implied),
        "p_hits_at_least_this_by_luck": prob_at_least(hits, implied),
        "under_50c": {"bets": len(cheap), "hits": sum(1 for s in cheap if s["won"]),
                      "roi": (sum(s["pnl"] / s["stake"] for s in cheap) / len(cheap)) if cheap else None},
    }


def baseline_roi(markets: dict[str, dict], ids: list[str], outcomes: dict[str, str], side_rule: str = "cheaper",
                 fee: float = 0.0, seed: int = 0) -> dict:
    """Flat $1 on the same count of questions by a mindless rule: 'cheaper' side, or a random side."""
    rng = random.Random(seed)
    bets = []
    for i in ids:
        m = markets.get(i)
        if not m or m.get("yes_ask") is None or m.get("no_ask") is None:
            continue
        side = ("yes" if m["yes_ask"] <= m["no_ask"] else "no") if side_rule == "cheaper" else rng.choice(["yes", "no"])
        bets.append({"market_id": i, "side": side, "entry_price": float(m[f"{side}_ask"]), "stake": 1.0, "fee": fee})
    s = summarize(settle(bets, outcomes), draws=2000, seed=seed)
    return {"rule": side_rule, **s}
