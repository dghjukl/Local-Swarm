import json
from datetime import datetime, timezone, timedelta
from forecast.markets import filter_markets, normalize_market
from forecast.score import brier, calibration, paper_bets
from forecast.snapshot import append_snapshot, resolve_market


def test_market_normalize_and_filters():
    raw = {"id": "1", "question": "Will an open project release version 2?", "description": "Official release page decides.", "outcomes": ["Yes", "No"], "outcomePrices": ["0.55", "0.45"], "endDate": (datetime.now(timezone.utc) + timedelta(days=14)).isoformat(), "liquidity": 100}
    m = normalize_market("polymarket", raw)
    kept, dropped = filter_markets([m], min_liquidity=10)
    assert len(kept) == 1 and dropped["not_binary"] == 0


def test_snapshot_resolver_and_scoring(tmp_path):
    path = tmp_path / "batch.jsonl"; assert append_snapshot(path, [{"market_id": "x", "question": "q"}]) == 1; assert append_snapshot(path, [{"market_id": "x", "question": "q"}]) == 0
    assert json.loads(path.read_text())["market"]["market_id"] == "x"
    assert resolve_market({"market_id": "x"}, {"result": "yes"})["outcome"] == "yes"
    f = [{"probability": .8, "outcome": 1, "entry_price": .6}, {"probability": .2, "outcome": 0, "entry_price": .1}]
    assert round(brier(f), 4) == .04 and calibration(f)
    assert paper_bets(f, margin=.1, draws=100)["bets"] == 2
