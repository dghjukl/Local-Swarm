"""Small no-GPU check for the exact extraction and page-fetch path used by forecasts."""
from __future__ import annotations


async def run_preflight() -> None:
    from swarm.tools import extract_isolated
    from swarm_forecast.adapter import FilteredResearch

    raw = "<html><body><article><h1>Preflight</h1><p>" + ("usable smoke text " * 80) + "</p></article></body></html>"
    text = await extract_isolated(raw, "https://example.com/preflight")
    if len(text) < 100:
        raise RuntimeError("extraction preflight returned too little text")
    research = FilteredResearch()
    try:
        doc = await research.fetch("https://en.wikipedia.org/wiki/Artificial_intelligence")
        if doc.error or len(doc.text) < 100:
            raise RuntimeError(f"page-fetch preflight failed: {doc.error or 'too little text'}")
    finally:
        await research.close()
