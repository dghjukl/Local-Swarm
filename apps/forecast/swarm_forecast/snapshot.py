from __future__ import annotations
import argparse, json, random
from collections import Counter
from pathlib import Path
from datetime import datetime, timezone
from swarm.atomic import write_text_atomic, write_json_atomic
from .markets import fetch_json, normalize_market, filter_markets, pull_polymarket, pull_kalshi_categories


def _histograms(markets):
    prices = Counter()
    weeks = Counter()
    categories = Counter()
    series = Counter()
    tags = Counter()
    for m in markets:
        p = m.get("last_price")
        if p is not None:
            prices[f"{min(9, max(0, int(float(p) * 10)))}0-{min(100, (int(float(p) * 10) + 1) * 10)}%"] += 1
        try:
            end = datetime.fromisoformat(str(m["end_date"]).replace("Z", "+00:00"))
            monday = end.date().fromordinal(end.date().toordinal() - end.weekday())
            weeks[monday.isoformat()] += 1
        except (KeyError, TypeError, ValueError):
            pass
        if m.get("category"): categories[str(m["category"])] += 1
        if m.get("series"): series[str(m["series"])] += 1
        for tag in m.get("tags", []) if isinstance(m.get("tags"), list) else []: tags[str(tag)] += 1
    return {"price_histogram": dict(sorted(prices.items())), "resolve_week_histogram": dict(sorted(weeks.items())),
            "top_categories": categories.most_common(15), "top_series": series.most_common(15), "top_tags": tags.most_common(15)}


def _apply_batch_caps(markets, sports_share=0.20):
    sports = [m for m in markets if str(m.get("category", "")).lower() == "sports"]
    non_sports = [m for m in markets if m not in sports]
    allowed = len(sports) if not non_sports else min(len(sports), int(len(non_sports) * sports_share / (1 - sports_share)))
    sports.sort(key=lambda m: abs(float(m.get("last_price") or 0.5) - 0.5))
    kept = non_sports + sports[:allowed]
    return kept, {"before": Counter(str(m.get("category") or "unknown") for m in markets),
                  "after": Counter(str(m.get("category") or "unknown") for m in kept),
                  "sports_dropped": len(sports) - allowed}


def append_snapshot(path: Path, markets: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    prior = path.read_text(encoding="utf-8") if path.exists() else ""
    cutoff = datetime.now(timezone.utc).timestamp() - 3600
    existing = [json.loads(line) for line in prior.splitlines() if line.strip()]
    seen = {x.get("market", {}).get("market_id") for x in existing if datetime.fromisoformat(x["snapshot_at"]).timestamp() >= cutoff}
    fresh = [m for m in markets if m.get("market_id") not in seen]
    text = "".join(json.dumps({"snapshot_at": datetime.now(timezone.utc).isoformat(), "market": m}, ensure_ascii=False) + "\n" for m in fresh)
    write_text_atomic(path, prior + text)
    return len(fresh)


def resolve_market(snapshot: dict, resolution: dict | None) -> dict:
    raw = resolution or {}
    outcome = raw.get("outcome") or raw.get("result")
    if outcome not in {"yes", "no", "void", "unresolved"}: outcome = "unresolved"
    return {"market_id": snapshot.get("market_id"), "outcome": outcome, "resolved_at": datetime.now(timezone.utc).isoformat()}


def main(argv=None):
    ap = argparse.ArgumentParser(); ap.add_argument("--out"); ap.add_argument("--polymarket-json"); ap.add_argument("--kalshi-json"); ap.add_argument("--max-days", type=int, default=60)
    args = ap.parse_args(argv); markets = []
    for source, path in (("polymarket", args.polymarket_json), ("kalshi", args.kalshi_json)):
        if path:
            data = json.loads(Path(path).read_text(encoding="utf-8")); data = data if isinstance(data, list) else data.get("markets", [])
            markets.extend(normalize_market(source, x) for x in data)
    errors = {}
    caps = {"polymarket": False, "kalshi": False}; category_counts = {}
    if not args.polymarket_json and not args.kalshi_json:
        try:
            from .markets import pull_polymarket
            markets.extend(pull_polymarket(min_liquidity=1000, max_days=args.max_days)); caps["polymarket"] = getattr(pull_polymarket, "last_capped", False)
        except Exception as exc: errors["polymarket"] = f"{type(exc).__name__}: {exc}"
        try:
            categories = ["Politics", "Elections", "Economics", "World", "Science and Technology", "Companies", "Climate and Weather", "Sports"]
            markets.extend(pull_kalshi_categories(categories, cap=10000)); caps["kalshi"] = getattr(pull_kalshi_categories, "last_capped", False)
            category_counts = getattr(pull_kalshi_categories, "category_counts", {})
        except Exception as exc: errors["kalshi"] = f"{type(exc).__name__}: {exc}"
    kept60, dropped60 = filter_markets(markets, min_liquidity=1000, max_days=60)
    kept90, dropped90 = filter_markets(markets, min_liquidity=1000, max_days=90)
    kept, dropped = (kept60, dropped60) if args.max_days == 60 else (kept90, dropped90)
    kept, category_caps = _apply_batch_caps(kept)
    out = Path(args.out or f"runtime/forecast/batch_{datetime.now().date().isoformat()}.jsonl")
    added = append_snapshot(out, kept)
    source_counts = {s: sum(1 for m in markets if m.get("source") == s) for s in {m.get("source") for m in markets}}
    kept_counts = {s: sum(1 for m in kept if m.get("source") == s) for s in {m.get("source") for m in kept}}
    rng = random.Random(0)
    samples = rng.sample(kept, min(12, len(kept)))
    stats = {"fetched": len(markets), "fetched_by_source": source_counts, "kept": len(kept), "kept_by_source": kept_counts,
             "added": added, "dropped": dropped, "errors": errors, "pull_caps_reached": caps,
             "category_pull_counts": category_counts, "category_caps": {k: dict(v) if isinstance(v, Counter) else v for k, v in category_caps.items()},
             "horizon_counts": {"60": sum(1 for m in _apply_batch_caps(kept60)[0]), "90": sum(1 for m in _apply_batch_caps(kept90)[0])},
             "filters": {"min_days": 7, "max_days": args.max_days, "min_liquidity": 1000, "max_spread": 0.15, "sports_share": 0.20},
             **_histograms(kept), "samples": samples}
    write_json_atomic(out.with_name(out.stem + "-stats.json"), stats)
    print(json.dumps(stats, separators=(",", ":"))); return 0


if __name__ == "__main__": raise SystemExit(main())
