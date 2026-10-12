import asyncio

from swarm.tools import extract_isolated
from swarm_forecast.adapter import _blocked_host


def test_extraction_works_in_spawned_worker():
    raw = "<html><body><article><h1>Worker fixture</h1><p>" + ("article text " * 80) + "</p></article></body></html>"
    text = asyncio.run(extract_isolated(raw, "https://example.com/fixture"))
    assert "article text" in text
    assert len(text) > 100


def test_blind_market_domain_boundary():
    assert _blocked_host("https://www.polymarket.com/event/x")
    assert _blocked_host("https://sub.manifold.markets/x")
    assert not _blocked_host("https://www.reuters.com/article/x")
