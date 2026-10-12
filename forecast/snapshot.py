from __future__ import annotations
import argparse, json
from pathlib import Path
from datetime import datetime, timezone
from swarm.atomic import write_text_atomic, write_json_atomic
from .markets import fetch_json, normalize_market, filter_markets, pull_polymarket, pull_kalshi


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
    if not args.polymarket_json and not args.kalshi_json:
        try: markets.extend(pull_polymarket())
        except Exception as exc: errors["polymarket"] = f"{type(exc).__name__}: {exc}"
        try: markets.extend(pull_kalshi())
        except Exception as exc: errors["kalshi"] = f"{type(exc).__name__}: {exc}"
    kept, dropped = filter_markets(markets)
    out = Path(args.out or f"runtime/forecast/batch_{datetime.now().date().isoformat()}.jsonl")
    added = append_snapshot(out, kept)
    source_counts = {s: sum(1 for m in markets if m.get("source") == s) for s in {m.get("source") for m in markets}}
    kept_counts = {s: sum(1 for m in kept if m.get("source") == s) for s in {m.get("source") for m in kept}}
    stats = {"fetched": len(markets), "fetched_by_source": source_counts, "kept": len(kept), "kept_by_source": kept_counts,
             "added": added, "dropped": dropped, "errors": errors, "samples": kept[:10]}
    write_json_atomic(out.with_name(out.stem + "-stats.json"), stats)
    print(json.dumps(stats, separators=(",", ":"))); return 0


if __name__ == "__main__": raise SystemExit(main())
