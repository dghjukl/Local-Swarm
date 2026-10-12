from __future__ import annotations

import hashlib
import json
import re
import urllib.request
from urllib.parse import urlencode
import time
from datetime import datetime, timezone, timedelta


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
        indexed = {name.lower(): float(prices[i]) for i, name in enumerate(outcomes) if i < len(prices) and name.lower() in {"yes", "no"}}
        yes = float(raw.get("bestAsk")) if raw.get("bestAsk") is not None else indexed.get("yes")
        no = (1 - float(raw.get("bestBid"))) if raw.get("bestBid") is not None else indexed.get("no")
        return {"source": source, "market_id": str(raw.get("id") or raw.get("conditionId")),
                "question": raw.get("question") or raw.get("title", ""), "resolution_rule": raw.get("description", ""),
                "outcomes": outcomes, "end_date": raw.get("endDate") or raw.get("endDateIso") or raw.get("end_date_iso"),
                "prices": [x for x in (yes, no) if x is not None], "yes_ask": yes, "no_ask": no,
                "last_price": (float(raw.get("lastTradePrice")) if raw.get("lastTradePrice") is not None else (float(prices[0]) if prices else None)),
                "spread": float(raw.get("spread")) if raw.get("spread") is not None else None,
                "volume": raw.get("volume") or raw.get("volumeNum"), "liquidity": raw.get("liquidity") or raw.get("liquidityNum"),
                "category": raw.get("category") or ((raw.get("events") or [{}])[0].get("category") if isinstance(raw.get("events"), list) and raw.get("events") else None),
                "series": ((raw.get("series") or [{}])[0].get("ticker") if isinstance(raw.get("series"), list) and raw.get("series") else raw.get("seriesSlug") or (((raw.get("events") or [{}])[0].get("series") or [{}])[0].get("ticker") if isinstance(raw.get("events"), list) and raw.get("events") else None)),
                "event_ticker": (raw.get("events") or [{}])[0].get("id") if isinstance(raw.get("events"), list) and raw.get("events") else None,
                "tags": raw.get("tags") or ((raw.get("events") or [{}])[0].get("tags", []) if isinstance(raw.get("events"), list) and raw.get("events") else []),
                "combo_status": raw.get("comboStatus"), "neg_risk": raw.get("negRisk"),
                "fetched_at": datetime.now(timezone.utc).isoformat(), "raw_hash": _hash(raw), "raw": raw}
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
            "series": raw.get("series_ticker"), "event_ticker": raw.get("event_ticker"),
            "tags": raw.get("tags", []), "is_combo": str(raw.get("ticker", "")).startswith("KXMVE") or bool(raw.get("mve_collection_ticker")),
            "fetched_at": datetime.now(timezone.utc).isoformat(), "raw_hash": _hash(raw), "raw": raw}


def pull_polymarket(limit=100, cap=2000, min_liquidity=1000, now=None, sleep_s=1.0, max_days=60):
    now = now or datetime.now(timezone.utc)
    params = {"closed": "false", "end_date_min": (now + timedelta(days=7)).isoformat(),
              "end_date_max": (now + timedelta(days=max_days)).isoformat(), "limit": limit,
              "order": "volumeNum", "ascending": "false", "liquidity_num_min": min_liquidity}
    result = []
    for offset in range(0, cap, limit):
        params["offset"] = offset
        data = fetch_json("https://gamma-api.polymarket.com/markets?" + urlencode(params))
        rows = data if isinstance(data, list) else data.get("markets", [])
        result.extend(normalize_market("polymarket", x) for x in rows)
        if len(rows) < limit: break
        time.sleep(sleep_s)
    pull_polymarket.last_capped = len(result) >= cap
    return result[:cap]


def pull_kalshi(cap=5000, sleep_s=1.0):
    result, cursor = [], ""
    while len(result) < cap:
        url = "https://external-api.kalshi.com/trade-api/v2/markets?status=open&limit=1000&mve_filter=exclude" + (f"&cursor={cursor}" if cursor else "")
        page = fetch_json(url); rows = page.get("markets", []) if isinstance(page, dict) else []
        result.extend(normalize_market("kalshi", x) for x in rows)
        cursor = page.get("cursor") or page.get("next_cursor") if isinstance(page, dict) else ""
        if not cursor or not rows: break
        time.sleep(sleep_s)
    pull_kalshi.last_capped = len(result) >= cap
    return result[:cap]


def pull_kalshi_categories(categories, cap=10000, per_category_cap=1500, sleep_s=1.0):
    result, seen, counts = [], set(), {}
    for category in categories:
        cursor = ""
        category_added = 0
        while len(result) < cap:
            params = {"status": "open", "limit": 200, "with_nested_markets": "true", "category": category}
            if cursor: params["cursor"] = cursor
            page = fetch_json("https://external-api.kalshi.com/trade-api/v2/events?" + urlencode(params))
            events = page.get("events", []) if isinstance(page, dict) else []
            for event in events:
                event_category = event.get("category") or category
                nested = event.get("markets", [])
                counts[event_category] = counts.get(event_category, 0) + len(nested)
                for raw in nested:
                    ticker = raw.get("ticker")
                    if ticker in seen: continue
                    seen.add(ticker)
                    raw = dict(raw); raw["category"] = event_category; raw["series_ticker"] = event.get("series_ticker")
                    raw["event_market_count"] = len(nested)
                    result.append(normalize_market("kalshi", raw))
                    category_added += 1
                    if len(result) >= cap or category_added >= per_category_cap: break
                if len(result) >= cap or category_added >= per_category_cap: break
            cursor = page.get("cursor") if isinstance(page, dict) else ""
            if not cursor or not events or len(result) >= cap or category_added >= per_category_cap: break
            time.sleep(sleep_s)
        if len(result) >= cap: break
    pull_kalshi_categories.category_counts = counts
    pull_kalshi_categories.last_capped = len(result) >= cap
    return result[:cap]


def filter_markets(markets: list[dict], *, now=None, min_days=7, max_days=60, min_liquidity=0,
                   max_spread=0.15, min_length=20, max_length=300):
    now = now or datetime.now(timezone.utc)
    kept, dropped = [], {"not_binary": 0, "date": 0, "liquidity": 0, "spread": 0, "price": 0, "text": 0, "rules": 0, "joke": 0, "event_cap": 0}
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
    per_event = {}
    final = []
    for m in kept:
        key = m.get("event_ticker") if m.get("source") == "kalshi" else None
        if not key:
            final.append(m); continue
        per_event.setdefault(key, []).append(m)
    for key, rows in per_event.items():
        rows.sort(key=lambda x: abs(float(x.get("last_price") or 0.5) - 0.5))
        limit = 1 if any(m.get("raw", {}).get("event_market_count") == 2 for m in rows) else 3
        final.extend(rows[:limit]); dropped["event_cap"] += max(0, len(rows) - limit)
    return final, dropped
