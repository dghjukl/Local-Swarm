from __future__ import annotations

import hashlib
import json
import re
import urllib.request
import time
from datetime import datetime, timezone


def fetch_json(url: str, timeout: int = 20):
    req = urllib.request.Request(url, headers={"User-Agent": "Local-Swarm-forecast-snapshot/0.1", "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def _hash(raw) -> str:
    return hashlib.sha256(json.dumps(raw, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def normalize_market(source: str, raw: dict) -> dict:
    """Normalize common Polymarket/Kalshi-like records without making assumptions about settlement."""
    if source == "polymarket":
        outcomes = raw.get("outcomes") or (["Yes", "No"] if raw.get("outcomePrices") else [])
        prices = raw.get("outcomePrices") or raw.get("prices") or []
        if isinstance(outcomes, str): outcomes = json.loads(outcomes)
        if isinstance(prices, str): prices = json.loads(prices)
        outcomes = [str(x) for x in outcomes]
        yes = float(raw.get("bestAsk", prices[0] if prices else 0)) if raw.get("bestAsk") is not None or prices else None
        no = (1 - float(raw.get("bestBid"))) if raw.get("bestBid") is not None else (float(prices[1]) if len(prices) > 1 else None)
        return {"source": source, "market_id": str(raw.get("id") or raw.get("conditionId")),
                "question": raw.get("question") or raw.get("title", ""), "resolution_rule": raw.get("description", ""),
                "outcomes": outcomes, "end_date": raw.get("endDate") or raw.get("endDateIso") or raw.get("end_date_iso"),
                "prices": [x for x in (yes, no) if x is not None], "yes_ask": yes, "no_ask": no,
                "last_price": (float(raw.get("lastTradePrice")) if raw.get("lastTradePrice") is not None else (float(prices[0]) if prices else None)),
                "spread": float(raw.get("spread")) if raw.get("spread") is not None else None,
                "volume": raw.get("volume") or raw.get("volumeNum"), "liquidity": raw.get("liquidity") or raw.get("liquidityNum"),
                "category": raw.get("category"), "tags": raw.get("tags", []), "fetched_at": datetime.now(timezone.utc).isoformat(), "raw_hash": _hash(raw), "raw": raw}
    yes = raw.get("yes_bid_dollars", raw.get("yes_bid")); no = raw.get("no_bid_dollars", raw.get("no_bid"))
    def cents(value):
        return float(value) if value is not None and float(value) <= 1 else float(value) / 100
    return {"source": source, "market_id": str(raw.get("ticker") or raw.get("id")),
            "question": raw.get("title") or raw.get("question", ""), "resolution_rule": raw.get("rules_primary") or raw.get("rules_secondary") or raw.get("rules", ""),
            "outcomes": ["Yes", "No"], "end_date": raw.get("close_time") or raw.get("expiration_time"),
            "prices": [cents(x) for x in (yes, no) if x is not None],
            "yes_ask": cents(raw.get("yes_ask_dollars")) if raw.get("yes_ask_dollars") is not None else (1 - cents(no) if no is not None else None),
            "no_ask": cents(raw.get("no_ask_dollars")) if raw.get("no_ask_dollars") is not None else (1 - cents(yes) if yes is not None else None),
            "last_price": (cents(yes) if yes is not None else None), "spread": None,
            "volume": raw.get("volume_fp", raw.get("volume")), "liquidity": raw.get("open_interest_fp", raw.get("open_interest")), "category": raw.get("category"),
            "tags": raw.get("tags", []), "is_combo": str(raw.get("ticker", "")).startswith("KXMVE") or bool(raw.get("mve_collection_ticker")),
            "fetched_at": datetime.now(timezone.utc).isoformat(), "raw_hash": _hash(raw), "raw": raw}


def pull_polymarket(limit=500):
    data = fetch_json(f"https://gamma-api.polymarket.com/markets?limit={limit}&active=true&closed=false")
    return [normalize_market("polymarket", x) for x in (data if isinstance(data, list) else data.get("markets", []))]


def pull_kalshi(cap=5000, sleep_s=1.0):
    result, cursor = [], ""
    while len(result) < cap:
        url = "https://external-api.kalshi.com/trade-api/v2/markets?status=open&limit=100" + (f"&cursor={cursor}" if cursor else "")
        page = fetch_json(url); rows = page.get("markets", []) if isinstance(page, dict) else []
        result.extend(normalize_market("kalshi", x) for x in rows)
        cursor = page.get("cursor") or page.get("next_cursor") if isinstance(page, dict) else ""
        if not cursor or not rows: break
        time.sleep(sleep_s)
    return result[:cap]


def filter_markets(markets: list[dict], *, now=None, min_days=7, max_days=60, min_liquidity=0,
                   max_spread=0.15, min_length=20, max_length=300):
    now = now or datetime.now(timezone.utc)
    kept, dropped = [], {"not_binary": 0, "date": 0, "liquidity": 0, "spread": 0, "price": 0, "text": 0, "rules": 0, "joke": 0}
    for m in markets:
        q = str(m.get("question", "")); outcomes = [str(x).lower() for x in m.get("outcomes", [])]
        if set(outcomes) != {"yes", "no"} or m.get("is_combo"): dropped["not_binary"] += 1; continue
        if len(q) < min_length or len(q) > max_length: dropped["text"] += 1; continue
        if not m.get("resolution_rule") or (m.get("source") == "kalshi" and not m.get("raw", {}).get("rules_primary")): dropped["rules"] += 1; continue
        try:
            end = datetime.fromisoformat(str(m["end_date"]).replace("Z", "+00:00")); days = (end - now).total_seconds() / 86400
        except (KeyError, TypeError, ValueError): days = -1
        if days < min_days or days > max_days: dropped["date"] += 1; continue
        if float(m.get("liquidity") or m.get("volume") or 0) < min_liquidity: dropped["liquidity"] += 1; continue
        prices = m.get("prices") or []
        spread = m.get("spread")
        if spread is None and len(prices) == 2: spread = abs(1 - sum(prices))
        if spread is not None and float(spread) > max_spread: dropped["spread"] += 1; continue
        p = m.get("last_price")
        if p is not None and (float(p) > .97 or float(p) < .03): dropped["price"] += 1; continue
        if re.search(r"\b(will .*? win|who will win)\b", q, re.I) and len(q) < 35: dropped["joke"] += 1; continue
        kept.append(m)
    return kept, dropped
