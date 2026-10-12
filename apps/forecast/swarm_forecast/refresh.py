"""Read-only price refresh for exactly the markets in a sample file."""
from __future__ import annotations
import json, time
from datetime import datetime, timezone
from pathlib import Path
from .markets.core import fetch_json

def refresh(sample_path, out_path=None, sleep_s=1.0):
    rows = [json.loads(line) for line in Path(sample_path).read_text(encoding="utf-8").splitlines() if line.strip()]
    out = []
    for i, market in enumerate(rows):
        source, mid = market.get("source"), market.get("market_id")
        url = (f"https://gamma-api.polymarket.com/markets/{mid}" if source == "polymarket" else f"https://external-api.kalshi.com/trade-api/v2/markets/{mid}")
        try:
            raw = fetch_json(url); raw = raw.get("market", raw) if isinstance(raw, dict) else raw
            from .markets.core import normalize_market
            fresh = normalize_market(source, raw); old = float(market.get("last_price") or 0); new = float(fresh.get("last_price") or 0)
            closed = bool(raw.get("closed")) or str(raw.get("status", "")).lower() in {"closed", "settled", "inactive"} or raw.get("acceptingOrders") is False
            m = dict(market); m["refreshed"] = fresh; m["stale"] = closed or abs(new - old) > .10; m["stale_reason"] = "closed_or_stopped" if closed else "price_move_over_10_points" if abs(new-old) > .10 else None
        except Exception as exc:
            m = dict(market); m["stale"] = True; m["stale_reason"] = f"refresh_error:{type(exc).__name__}: {exc}"
        out.append(m)
        if i + 1 < len(rows): time.sleep(sleep_s)
    target = Path(out_path or str(sample_path).replace(".jsonl", "_priced.jsonl")); write_jsonl(target, out); return out

def write_jsonl(path, rows):
    Path(path).write_text("".join(json.dumps(x, ensure_ascii=False) + "\n" for x in rows), encoding="utf-8")
