"""What the forecaster may see. Blind questions carry no price of any kind."""
from __future__ import annotations

FORBIDDEN_KEYS = {"price", "prices", "yes_ask", "no_ask", "last_price", "market_state", "bestBid", "bestAsk",
                  "outcomePrices", "lastTradePrice", "spread", "volume", "liquidity", "raw", "implied_probability"}


def blind_question(market: dict, today: str) -> dict:
    return {"market_id": str(market["market_id"]), "source": market.get("source", ""),
            "question": market.get("question", ""), "rules": market.get("resolution_rule", "") or "",
            "end_date": market.get("end_date", "") or "", "today": today}


def market_state(market: dict) -> dict:
    return {k: market.get(k) for k in ("yes_ask", "no_ask", "last_price", "spread")}


def informed_question(market: dict, today: str) -> dict:
    q = blind_question(market, today)
    q["market_state"] = market_state(market)
    return q


def find_leaks(obj, path="") -> list[str]:
    """Every price-like key anywhere inside a (nested) blind question."""
    leaks = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k in FORBIDDEN_KEYS:
                leaks.append(f"{path}{k}")
            leaks += find_leaks(v, f"{path}{k}.")
    elif isinstance(obj, (list, tuple)):
        for i, v in enumerate(obj):
            leaks += find_leaks(v, f"{path}{i}.")
    return leaks

def assert_blind_safe(question: dict) -> None:
    leaks = find_leaks(question)
    if leaks:
        raise ValueError(f"blind question leaks market state: {leaks}")
