"""python -m swarm_forecast cycle --pool FILE --out DIR [--mode gap|screen] [--x N] [--limit N] [--dry-run]
   python -m swarm_forecast score --out DIR --pool FILE --outcomes FILE [--date 7|14|21|final]"""
from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path

import yaml

from swarm_forecast.adapter import SwarmSession
from swarm_forecast.runner import cycle as cyc
from swarm_forecast.store import write_json_atomic

CONFIG = Path(__file__).resolve().parent.parent / "config" / "default.yaml"


def load_app_config(path: Path = CONFIG) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="swarm_forecast")
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("cycle")
    c.add_argument("--pool", required=True)
    c.add_argument("--out", required=True)
    c.add_argument("--mode", choices=["gap", "screen"])
    c.add_argument("--x", type=int)
    c.add_argument("--limit", type=int)
    c.add_argument("--dry-run", action="store_true")
    c.add_argument("--stop-after-picks", action="store_true")
    s = sub.add_parser("score")
    s.add_argument("--out", required=True)
    s.add_argument("--pool", required=True)
    s.add_argument("--outcomes", required=True, help="JSON file: market_id -> yes|no|void")
    s.add_argument("--date", choices=["7", "14", "21", "final"], default="final")
    a = ap.parse_args(argv)
    app = load_app_config()

    if a.cmd == "score":
        pool = {str(m["market_id"]): m for m in cyc.load_pool(a.pool)}
        outcomes = json.loads(Path(a.outcomes).read_text(encoding="utf-8"))
        from swarm_forecast.scoring_v1 import report_files, rows_from_cycle, score_rows
        rep = cyc.score_cycle(a.out, outcomes, pool)
        rows = rows_from_cycle(a.out, list(pool.values()), outcomes)
        report_files(score_rows(rows, total=len(rows), date_label=a.date, as_of=app.get("cycle_as_of")), a.out, cycle_dir=a.out)
        write_json_atomic(Path(a.out) / "report.json", rep)
        print(json.dumps({k: rep[k] for k in ("outcomes_known", "coverage", "bets", "selection") if k in rep}, indent=1, default=str))
        return 0

    rules = {**(app.get("cycle_rules") or {})}
    for k in ("mode", "x"):
        if getattr(a, k) is not None:
            rules[k] = getattr(a, k)
    if a.limit:
        rules["pool_limit"] = a.limit
    pool = cyc.load_pool(a.pool, rules.get("pool_limit") or cyc.DEFAULT_RULES["pool_limit"])
    full = {**cyc.DEFAULT_RULES, **rules}
    print(f"cycle {Path(a.out).name}: pool {len(pool)}, mode {full['mode']}, deep picks {full['x']}")
    for stage in ("select" if full["mode"] == "screen" else "blind", "pick", "deep", "bets"):
        print(f"planned stage: {stage}")
    if a.dry_run:
        return 0
    stages = app.get("stages") or {}
    quick = SwarmSession({**(stages.get("quick") or {}), "_name": "fc-quick"}, save_dir=Path(a.out) / "traces_quick")
    deep = SwarmSession({**(stages.get("deep") or {}), "_name": "fc-deep"}, save_dir=Path(a.out) / "traces_deep")
    res = asyncio.run(cyc.run_cycle(a.out, pool, rules, quick, deep,
                                    lock_path=(app.get("gpu_lock") or {}).get("path"),
                                    stop_after_picks=a.stop_after_picks))
    print(json.dumps(res, indent=1, default=str))
    return 0 if res.get("status") == "ok" else 3
