from __future__ import annotations
import argparse, json
from pathlib import Path
from datetime import datetime, timezone
from swarm.atomic import write_text_atomic
from .markets import fetch_json, normalize_market, filter_markets


def append_snapshot(path: Path, markets: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = "".join(json.dumps({"snapshot_at": datetime.now(timezone.utc).isoformat(), "market": m}, ensure_ascii=False) + "\n" for m in markets)
    prior = path.read_text(encoding="utf-8") if path.exists() else ""
    write_text_atomic(path, prior + text)


def resolve_market(snapshot: dict, resolution: dict | None) -> dict:
    raw = resolution or {}
    outcome = raw.get("outcome") or raw.get("result")
    if outcome not in {"yes", "no", "void", "unresolved"}: outcome = "unresolved"
    return {"market_id": snapshot.get("market_id"), "outcome": outcome, "resolved_at": datetime.now(timezone.utc).isoformat()}


def main(argv=None):
    ap = argparse.ArgumentParser(); ap.add_argument("--out", default="runtime/forecast/batch_latest.jsonl"); ap.add_argument("--polymarket-json"); ap.add_argument("--kalshi-json")
    args = ap.parse_args(argv); markets = []
    for source, path in (("polymarket", args.polymarket_json), ("kalshi", args.kalshi_json)):
        if path:
            data = json.loads(Path(path).read_text(encoding="utf-8")); data = data if isinstance(data, list) else data.get("markets", [])
            markets.extend(normalize_market(source, x) for x in data)
    kept, dropped = filter_markets(markets); append_snapshot(Path(args.out), kept)
    print(json.dumps({"fetched": len(markets), "kept": len(kept), "dropped": dropped}, indent=2)); return 0


if __name__ == "__main__": raise SystemExit(main())
