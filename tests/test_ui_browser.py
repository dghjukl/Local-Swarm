"""Drive the real web page in headless Chromium (skipped where Playwright isn't installed)."""
import threading
import time

import pytest
import uvicorn

from swarm.web import app as webapp
from test_integration import FakeResearch  # noqa: F401  (fixture module side effects)

pw = pytest.importorskip("playwright.sync_api")


def test_page_runs_a_question(cfg, cards, mock_pool_cls, monkeypatch):
    monkeypatch.setattr(webapp, "ModelPool", mock_pool_cls)
    from test_integration import TOWER
    from swarm.tools import Doc

    async def fake_wiki(q, n=2):
        return [Doc("https://en.wikipedia.org/wiki/Eiffel_Tower", "Eiffel Tower - Wikipedia", TOWER, "wikipedia")]
    monkeypatch.setattr("swarm.orchestrator.wikipedia", fake_wiki)
    app = webapp.create_app(cfg, cards=cards, research=FakeResearch(), start_research=False, warm=False)
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=8712, log_level="warning"))
    t = threading.Thread(target=server.run, daemon=True)
    t.start()
    time.sleep(1.5)
    try:
        with pw.sync_playwright() as p:
            try:
                browser = p.chromium.launch()
            except Exception as e:
                pytest.skip(f"no browser: {e}")
            page = browser.new_page()
            errors = []
            page.on("pageerror", lambda e: errors.append(str(e)))
            page.goto("http://127.0.0.1:8712/")
            page.wait_for_function("document.getElementById('chipConn').textContent === 'connected'", timeout=10000)
            page.fill("#q", "When was the Eiffel Tower built?")
            page.click("#btnAsk")
            page.wait_for_selector("#sources li[id^='src-']", timeout=60000)
            assert "1889" in page.inner_text("#answer")
            assert page.locator(".worker").count() == 3
            assert errors == []
            browser.close()
    finally:
        server.should_exit = True
        t.join(10)
