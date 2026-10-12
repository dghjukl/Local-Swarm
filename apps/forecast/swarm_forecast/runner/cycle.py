"""One forecasting cycle: select -> blind -> pick -> deep -> bets, resumable, with rules fixed in advance."""
from __future__ import annotations

import json
from datetime import date, datetime, timezone
from pathlib import Path

from swarm_forecast import gpu_lock
from swarm_forecast.adapter import coordinator_json
from swarm_forecast.runner import bets as betmod
from swarm_forecast.runner import blind as blindmod
from swarm_forecast.runner import deep as deepmod
from swarm_forecast.runner import select as selmod
from swarm_forecast.store import RecordLog, config_hash, read_json, write_json_atomic

DEFAULT_RULES = {
    "mode": "gap",            # gap: blind forecast on the pool, pick the biggest gaps to the market
                              # screen: answerability screen from text, pick the most answerable
    "pool_limit": 300,        # questions the quick stage looks at
    "x": 30,                  # questions that get deep research
    "min_gap": 0.10,          # blind gap needed to be picked (gap mode)
    "confirm_margin": 0.05,   # the deep pass must still see this much edge on the picked side
    "bet_margin": 0.10,       # paper bet only if the deep edge is at least this
    "fee": 0.0,
    "seed": 0,
}


def utc_today() -> str:
    return date.today().isoformat()


def load_pool(path: str | Path, limit: int | None = None) -> list[dict]:
    rows = [json.loads(l) for l in Path(path).read_text(encoding="utf-8").splitlines() if l.strip()]
    return rows[:limit] if limit else rows


def preregister(cycle_dir: Path, rules: dict, pool: list[dict], stamps: dict) -> dict:
    """Rules, pool and stages are written before the first forecast; a resumed cycle must match."""
    meta_path = cycle_dir / "meta.json"
    ids = [str(m["market_id"]) for m in pool]
    meta = {"rules": rules, "rules_hash": config_hash(rules), "pool_hash": config_hash(ids), "pool_size": len(ids),
            "created": datetime.now(timezone.utc).isoformat(), "stamps": stamps}
    old = read_json(meta_path)
    if old:
        if old.get("rules_hash") != meta["rules_hash"] or old.get("pool_hash") != meta["pool_hash"]:
            raise RuntimeError("this cycle was registered with different rules or a different pool; "
                               "start a new cycle directory instead of changing them")
        return old
    write_json_atomic(meta_path, meta)
    return meta


async def run_cycle(cycle_dir: str | Path, pool: list[dict], rules: dict, quick, deep, *, today: str | None = None,
                    refresh=None, llm_json=None, lock_path=None, lock_owner="swarm-forecast", lock_timeout=0,
                    progress=None) -> dict:
    rules = {**DEFAULT_RULES, **(rules or {})}
    cycle_dir = Path(cycle_dir)
    cycle_dir.mkdir(parents=True, exist_ok=True)
    today = today or utc_today()
    pool = pool[: rules["pool_limit"]]
    markets = {str(m["market_id"]): m for m in pool}
    preregister(cycle_dir, rules, pool, {"quick": getattr(getattr(quick, "handle", None), "stamp", None)})
    lk = {"path": lock_path} if lock_path else {}
    held = gpu_lock.acquire(lock_owner, f"cycle {cycle_dir.name}", timeout=lock_timeout, **lk)
    if held is None:
        return {"status": "gpu_busy", "holder": gpu_lock.status(**lk)}
    summary: dict = {"status": "ok", "cycle": cycle_dir.name}
    try:
        screen_log = RecordLog(cycle_dir / "screen.jsonl")
        blind_log = RecordLog(cycle_dir / "blind.jsonl")
        deep_log = RecordLog(cycle_dir / "deep.jsonl")
        picks_path = cycle_dir / "picks.json"

        # ---- quick stage: everything that uses the quick configuration
        picks = read_json(picks_path)
        if picks is None:
            await quick.start()
            qs = [{"market_id": m["market_id"], "question": m["question"], "end_date": m.get("end_date"),
                   "rules": m.get("resolution_rule", "")} for m in pool]
            jl = llm_json or (lambda s, u, sc: coordinator_json(quick.handle, s, u, sc, 900))
            if rules["mode"] == "screen":
                screened = await selmod.screen(qs, jl)
                for s in screened:
                    screen_log.append(s)
                chosen = selmod.choose_by_screen(screened, rules["x"], rules["seed"])
                # blind forecasts for the chosen questions only (they also serve the scoring of the blind arm)
                chosen_markets = [markets[c["market_id"]] for c in chosen]
                summary["blind"] = await blindmod.run_blind(chosen_markets, quick, blind_log, today, progress)
            else:
                summary["blind"] = await blindmod.run_blind(pool, quick, blind_log, today, progress)
                chosen = selmod.choose_by_gap(blind_log.read(), markets, rules["x"], rules["min_gap"])
            picks = {"mode": rules["mode"], "picks": chosen, "saved": blindmod.now_iso(),
                     "baselines": {"random": selmod.random_picks(pool, len(chosen), rules["seed"]),
                                   "near_fifty": selmod.near_fifty_picks(pool, len(chosen))}}
            write_json_atomic(picks_path, picks)  # the reasons are on disk before any deep research
            await quick.close()                    # free the GPU for the deep configuration

        # ---- deep stage
        summary["picks"] = len(picks["picks"])
        summary["deep"] = await deepmod.run_deep(picks["picks"], markets, deep, deep_log, today, refresh,
                                                 rules["confirm_margin"], progress)
        await deep.close()

        # ---- bets (decided from confirmed deep forecasts; settled later when outcomes arrive)
        bets = betmod.decide_bets(deep_log.read(), rules["bet_margin"], rules["fee"])
        write_json_atomic(cycle_dir / "bets.json", bets)
        summary["bets"] = len(bets)
        return summary
    finally:
        gpu_lock.release(lock_owner, **lk)


def score_cycle(cycle_dir: str | Path, outcomes: dict[str, str], markets: dict[str, dict]) -> dict:
    """Honest scoring once outcomes exist: forecasts vs the market and trivial baselines, picks vs baselines,
    paper bets vs luck. outcomes: market_id -> 'yes'|'no'|'void'|None."""
    from swarm_forecast.score import brier, calibration, log_score

    cycle_dir = Path(cycle_dir)
    blind = RecordLog(cycle_dir / "blind.jsonl").keyed()
    deep = RecordLog(cycle_dir / "deep.jsonl").keyed()
    picks = read_json(cycle_dir / "picks.json") or {"picks": [], "baselines": {}}
    bets = read_json(cycle_dir / "bets.json") or []

    def market_p(m):
        ya, na = m.get("yes_ask"), m.get("no_ask")
        if ya is not None and na is not None:
            return (float(ya) + (1.0 - float(na))) / 2.0
        return float(ya) if ya is not None else None

    def fs(records, pfield="probability"):
        return [{"probability": r[pfield], "outcome": outcomes[i] == "yes", "id": i}
                for i, r in records.items() if r.get(pfield) is not None and outcomes.get(i) in ("yes", "no")]

    def arm(name, f):
        return {"arm": name, "n": len(f), "brier": brier(f), "log_score": log_score(f), "calibration": calibration(f)}

    out = {"outcomes_known": sum(1 for v in outcomes.values() if v in ("yes", "no"))}
    out["coverage"] = {"blind_total": len(blind), "blind_forecast": sum(1 for r in blind.values() if r.get("probability") is not None),
                        "no_forecast": sum(1 for r in blind.values() if r.get("no_forecast")),
                        "inconsistent": sum(1 for r in blind.values() if r.get("inconsistent")),
                        "stale_suspect": sum(1 for r in deep.values() if r.get("stale_suspect"))}
    bf = fs(blind)
    ids = [x["id"] for x in bf]
    out["blind"] = arm("blind", bf)
    out["market_on_same"] = arm("market", [{"probability": market_p(markets[i]), "outcome": outcomes[i] == "yes"}
                                          for i in ids if i in markets and market_p(markets[i]) is not None])
    out["fifty_on_same"] = arm("fifty", [{"probability": 0.5, "outcome": outcomes[i] == "yes"} for i in ids])
    dy = [{"probability": r["probability"], "outcome": outcomes[i] == "yes", "id": i}
          for i, r in deep.items() if r.get("probability") is not None and outcomes.get(i) in ("yes", "no")]
    out["deep"] = arm("deep", dy)
    out["market_on_deep"] = arm("market", [{"probability": market_p(markets[x["id"]]), "outcome": x["outcome"]}
                                          for x in dy if x["id"] in markets and market_p(markets[x["id"]]) is not None])
    settled = betmod.settle(bets, outcomes)
    out["bets"] = betmod.summarize(settled)
    pick_ids = [p["market_id"] for p in picks["picks"]]
    out["baseline_bets_cheaper_side"] = betmod.baseline_roi(markets, pick_ids, outcomes, "cheaper")
    out["baseline_bets_random_side"] = betmod.baseline_roi(markets, pick_ids, outcomes, "random")
    # did the selection know something? Compare swarm-minus-market Brier on the picked vs the other blind forecasts
    pick_set = set(pick_ids)

    def edge(ids_):
        f = [(blind[i]["probability"], market_p(markets[i]), outcomes[i] == "yes") for i in ids_
             if i in blind and blind[i].get("probability") is not None and i in markets
             and market_p(markets[i]) is not None and outcomes.get(i) in ("yes", "no")]
        if not f:
            return None
        sw = sum((p - int(o)) ** 2 for p, _, o in f) / len(f)
        mk = sum((q - int(o)) ** 2 for _, q, o in f) / len(f)
        return {"n": len(f), "swarm_brier": sw, "market_brier": mk, "swarm_minus_market": sw - mk}

    out["selection"] = {"picked": edge([i for i in blind if i in pick_set]),
                        "not_picked": edge([i for i in blind if i not in pick_set])}
    screen = RecordLog(cycle_dir / "screen.jsonl").keyed()
    if screen:  # screen mode: does the answerability score predict the swarm's accuracy?
        by = {}
        for i, sc in screen.items():
            if i in blind and blind[i].get("probability") is not None and outcomes.get(i) in ("yes", "no"):
                by.setdefault(sc["answerable"], []).append(
                    (blind[i]["probability"] - int(outcomes[i] == "yes")) ** 2)
        out["answerability_vs_brier"] = {str(k): {"n": len(v), "brier": sum(v) / len(v)} for k, v in sorted(by.items())}
    return out
