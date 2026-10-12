from __future__ import annotations

import hashlib
import json
import re
import urllib.request
from datetime import datetime, timezone


def fetch_json(url: str, timeout: int = 20):
    req = urllib.request.Request(url, headers={"User-Agent": "Local-Swarm-forecast-snapshot/0.1"})
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
        return {"source": source, "market_id": str(raw.get("id") or raw.get("conditionId")),
                "question": raw.get("question") or raw.get("title", ""), "resolution_rule": raw.get("description", ""),
                "outcomes": outcomes, "end_date": raw.get("endDate") or raw.get("end_date_iso"),
                "prices": [float(x) for x in prices] if prices else [], "last_price": (float(prices[0]) if prices else None),
                "volume": raw.get("volume") or raw.get("volumeNum"), "liquidity": raw.get("liquidity"),
                "category": raw.get("category"), "tags": raw.get("tags", []), "fetched_at": datetime.now(timezone.utc).isoformat(), "raw_hash": _hash(raw), "raw": raw}
    yes = raw.get("yes_bid_dollars", raw.get("yes_bid")); no = raw.get("no_bid_dollars", raw.get("no_bid"))
    def cents(value):
        return float(value) if value is not None and float(value) <= 1 else float(value) / 100
    return {"source": source, "market_id": str(raw.get("ticker") or raw.get("id")),
            "question": raw.get("title") or raw.get("question", ""), "resolution_rule": raw.get("rules_primary") or raw.get("rules_secondary") or raw.get("rules", ""),
            "outcomes": ["Yes", "No"], "end_date": raw.get("close_time") or raw.get("expiration_time"),
            "prices": [cents(x) for x in (yes, no) if x is not None],
            "last_price": (cents(yes) if yes is not None else None),
            "volume": raw.get("volume_fp", raw.get("volume")), "liquidity": raw.get("open_interest_fp", raw.get("open_interest")), "category": raw.get("category"),
            "tags": raw.get("tags", []), "fetched_at": datetime.now(timezone.utc).isoformat(), "raw_hash": _hash(raw), "raw": raw}


def filter_markets(markets: list[dict], *, now=None, min_days=7, max_days=60, min_liquidity=0,
                   max_spread=0.15, min_length=20, max_length=300):
    now = now or datetime.now(timezone.utc)
    kept, dropped = [], {"not_binary": 0, "date": 0, "liquidity": 0, "spread": 0, "price": 0, "text": 0, "rules": 0, "joke": 0}
    for m in markets:
        q = str(m.get("question", "")); outcomes = [str(x).lower() for x in m.get("outcomes", [])]
        if set(outcomes) != {"yes", "no"}: dropped["not_binary"] += 1; continue
        if len(q) < min_length or len(q) > max_length: dropped["text"] += 1; continue
        if not m.get("resolution_rule"): dropped["rules"] += 1; continue
        try:
            end = datetime.fromisoformat(str(m["end_date"]).replace("Z", "+00:00")); days = (end - now).total_seconds() / 86400
        except (KeyError, TypeError, ValueError): days = -1
        if days < min_days or days > max_days: dropped["date"] += 1; continue
        if float(m.get("liquidity") or m.get("volume") or 0) < min_liquidity: dropped["liquidity"] += 1; continue
        prices = m.get("prices") or []
        if prices and (max(prices) - min(prices)) > max_spread: dropped["spread"] += 1; continue
        p = m.get("last_price")
        if p is not None and (float(p) > .97 or float(p) < .03): dropped["price"] += 1; continue
        if re.search(r"\b(will .*? win|who will win)\b", q, re.I) and len(q) < 35: dropped["joke"] += 1; continue
        kept.append(m)
    return kept, dropped
