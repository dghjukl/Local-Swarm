import asyncio

from swarm_forecast.adapter import SwarmSession, explicit_yes_probability
from swarm_forecast.runner.deep import has_recent_dated_support
from swarm_forecast.runner.select import choose_by_gap


def test_explicit_yes_probability_and_recent_support():
    assert explicit_yes_probability("My estimate: ~20% probability of YES.") == 0.20
    assert has_recent_dated_support("Official data published 2026-10-01 supports this.", "2026-10-12")
    assert not has_recent_dated_support("Official data published 2026-08-01 supports this.", "2026-10-12")


def test_gap_selection_excludes_no_forecast_and_inconsistent():
    market = {"market_id": "m1", "yes_ask": 0.10, "no_ask": 0.91}
    blind = [
        {"market_id": "m1", "probability": 0.90, "reasons": ["empty"], "no_forecast": True},
        {"market_id": "m2", "probability": 0.90, "reasons": ["mismatch"], "inconsistent": True},
        {"market_id": "m3", "probability": 0.90, "reasons": ["usable"]},
    ]
    markets = {"m1": market, "m2": {**market, "market_id": "m2"}, "m3": {**market, "market_id": "m3"}}
    assert [p["market_id"] for p in choose_by_gap(blind, markets, 5)] == ["m3"]


def test_empty_research_becomes_no_forecast(tmp_path):
    class Handle:
        stamp = {}
        def __init__(self):
            self.swarm = self
        async def run(self, *args, **kwargs):
            return {"final": {"answer": "No findings were recorded."}, "manager": {"notes": []}}
        async def close(self):
            pass

    async def factory(_):
        return Handle()

    async def extractor(*_):
        return {"probability": 0.5, "reasons": ["guess"], "key_uncertainty": "x"}

    s = SwarmSession(factory=factory, extractor=extractor, save_dir=tmp_path)
    result = asyncio.run(s.forecast({"market_id": "m", "question": "Q", "today": "2026-10-12", "end_date": "2026-11-01", "rules": ""}, "blind"))
    assert result["probability"] is None and result["no_forecast"]
