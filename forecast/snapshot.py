from __future__ import annotations
import argparse, json, random
from collections import Counter
from pathlib import Path
from datetime import datetime, timezone
from swarm.atomic import write_text_atomic, write_json_atomic
from .markets import fetch_json, normalize_market, filter_markets, pull_polymarket, pull_kalshi


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
    ap = argparse.ArgumentParser(); ap.add_argument("--out"); ap.add_argument("--polymarket-json"); ap.add_argument("--kalshi-json")
    args = ap.parse_args(argv); markets = []
    for source, path in (("polymarket", args.polymarket_json), ("kalshi", args.kalshi_json)):
        if path:
            data = json.loads(Path(path).read_text(encoding="utf-8")); data = data if isinstance(data, list) else data.get("markets", [])
            markets.extend(normalize_market(source, x) for x in data)
    errors = {}
    caps = {"polymarket": False, "kalshi": False}
    if not args.polymarket_json and not args.kalshi_json:
        try:
            markets.extend(pull_polymarket(min_liquidity=1000)); caps["polymarket"] = getattr(pull_polymarket, "last_capped", False)
        except Exception as exc: errors["polymarket"] = f"{type(exc).__name__}: {exc}"
        try:
            markets.extend(pull_kalshi()); caps["kalshi"] = getattr(pull_kalshi, "last_capped", False)
        except Exception as exc: errors["kalshi"] = f"{type(exc).__name__}: {exc}"
    kept, dropped = filter_markets(markets, min_liquidity=1000)
    out = Path(args.out or f"runtime/forecast/batch_{datetime.now().date().isoformat()}.jsonl")
    added = append_snapshot(out, kept)
    source_counts = {s: sum(1 for m in markets if m.get("source") == s) for s in {m.get("source") for m in markets}}
    kept_counts = {s: sum(1 for m in kept if m.get("source") == s) for s in {m.get("source") for m in kept}}
    rng = random.Random(0)
    samples = rng.sample(kept, min(10, len(kept)))
    stats = {"fetched": len(markets), "fetched_by_source": source_counts, "kept": len(kept), "kept_by_source": kept_counts,
             "added": added, "dropped": dropped, "errors": errors, "pull_caps_reached": caps,
             "filters": {"min_days": 7, "max_days": 60, "min_liquidity": 1000, "max_spread": 0.15},
             **_histograms(kept), "samples": samples}
    write_json_atomic(out.with_name(out.stem + "-stats.json"), stats)
    print(json.dumps(stats, separators=(",", ":"))); return 0


if __name__ == "__main__": raise SystemExit(main())
