import asyncio
import json

import pytest
from fastapi.testclient import TestClient

from swarm.orchestrator import Swarm
from swarm.pool import ModelLoadError
from swarm.tools import Doc
from swarm.web import app as webapp

TOWER = ("The Eiffel Tower is a wrought-iron lattice tower in Paris. It was completed in 1889 "
         "as the entrance to the World's Fair. ") * 4 + "\n\n" + ("The tower is 330 metres tall, "
         "about the same height as an 81-storey building. ") * 4


class FakeResearch:
    async def search(self, q, n=5):
        return [{"title": f"{q} page {i}", "url": f"https://site{i}.example/{abs(hash(q)) % 1000}"} for i in range(n)]

    async def fetch(self, url):
        if url.startswith("https://site1"):
            return Doc(url, "", "", "web", error="HTTP 403: Forbidden")
        return Doc(url, "Eiffel Tower facts", TOWER, "web")

    async def close(self):
        pass


@pytest.fixture(autouse=True)
def no_wikipedia(monkeypatch):
    async def fake_wiki(q, n=2):
        return [Doc("https://en.wikipedia.org/wiki/Eiffel_Tower", "Eiffel Tower - Wikipedia", TOWER, "wikipedia")]
    monkeypatch.setattr("swarm.orchestrator.wikipedia", fake_wiki)


async def test_full_research_run(cfg, cards, mock_pool_cls, isolate_runtime):
    events = []

    async def emit(e):
        events.append(e)

    pool = mock_pool_cls(cfg, cards)
    sw = Swarm(cfg, pool, cards, FakeResearch())
    try:
        trace = await sw.run("Tell me about the Eiffel Tower", emit)
    finally:
        await pool.shutdown()
    types = [e["type"] for e in events]
    assert "error" not in types, [e for e in events if e["type"] == "error"]
    assert types[0] == "run_start" and types[-1] == "final"
    final = events[-1]
    assert "1889" in final["answer"]
    assert "E77" not in final["answer"], "citations to missing passages are stripped"
    assert final["sources"] and final["sources"][0]["id"] == "E1"
    assert any(e["type"] == "answer_delta" for e in events)
    # 2 sub-questions x 3 workers
    results = trace["worker_results"]
    assert len(results) == 6 and not any(r.get("error") for r in results)
    for r in results:
        verdicts = [c["verdict"] for c in r["claims"]]
        assert verdicts == ["supported", "uncited"]
        assert r["support_rate"] == 0.5
    assert trace["stats"]["models"]
    assert list(isolate_runtime.joinpath("runs").glob("*.json"))
    fetch_fail = [e for e in events if e["type"] == "fetch" and not e["ok"]]
    assert fetch_fail, "a failed fetch is reported, not fatal"


async def test_direct_mode(cfg, cards, mock_pool_cls):
    events = []

    async def emit(e):
        events.append(e)

    pool = mock_pool_cls(cfg, cards)
    try:
        trace = await Swarm(cfg, pool, cards, FakeResearch()).run("hello there", emit)
    finally:
        await pool.shutdown()
    assert trace["plan"]["mode"] == "direct"
    assert events[-1]["type"] == "final" and events[-1]["sources"] == []
    assert not any(e["type"] == "team" for e in events)


async def test_pool_evicts_lru_within_budget(cfg, cards, mock_pool_cls):
    pool = mock_pool_cls(cfg, cards)
    pool.budget_mb = 1000
    pool.estimate_mb = lambda card, c, p: 600
    try:
        async with pool.use("Granite-4.1-3B", 2048) as u1:
            assert u1.startswith("http://127.0.0.1:")
        async with pool.use("LFM2.5-2.6B", 2048):
            assert set(pool.running) == {"LFM2.5-2.6B"}, "Granite (idle) was evicted to make room"
    finally:
        await pool.shutdown()


async def test_pool_waits_for_busy_model(cfg, cards, mock_pool_cls):
    pool = mock_pool_cls(cfg, cards)
    pool.budget_mb = 1000
    pool.estimate_mb = lambda card, c, p: 600
    order = []

    async def a():
        async with pool.use("Granite-4.1-3B", 2048):
            order.append("granite-start")
            await asyncio.sleep(1.0)
            order.append("granite-end")

    async def b():
        await asyncio.sleep(0.1)
        while "granite-start" not in order:
            await asyncio.sleep(0.05)
        async with pool.use("LFM2.5-2.6B", 2048):
            order.append("lfm")

    try:
        await asyncio.wait_for(asyncio.gather(a(), b()), 30)
    finally:
        await pool.shutdown()
    assert order == ["granite-start", "granite-end", "lfm"]


async def test_pool_load_failure_is_reported(cfg, cards, mock_pool_cls, monkeypatch):
    monkeypatch.setenv("MOCK_LLAMA_FAIL", "Phi-4")
    events = []

    async def emit(e):
        events.append(e)

    pool = mock_pool_cls(cfg, cards, emit=emit)
    with pytest.raises(ModelLoadError):
        await pool.ensure("Phi-4-mini-instruct", 2048)
    await pool.shutdown()
    assert any(e.get("event") == "failed" for e in events)


async def test_worker_failure_does_not_break_run(cfg, cards, mock_pool_cls, monkeypatch):
    monkeypatch.setenv("MOCK_LLAMA_FAIL", "Ministral")
    events = []

    async def emit(e):
        events.append(e)

    pool = mock_pool_cls(cfg, cards)
    try:
        trace = await Swarm(cfg, pool, cards, FakeResearch()).run("Tell me about the Eiffel Tower", emit)
    finally:
        await pool.shutdown()
    assert events[-1]["type"] == "final"
    failed = [r for r in trace["worker_results"] if r.get("error")]
    assert len(failed) == 2 and all(r["model"] == "Ministral-3-3B-Instruct" for r in failed)


def test_web_app_websocket(cfg, cards, mock_pool_cls, monkeypatch):
    monkeypatch.setattr(webapp, "ModelPool", mock_pool_cls)
    app = webapp.create_app(cfg, cards=cards, research=FakeResearch(), start_research=False, warm=False)
    with TestClient(app) as client:
        assert "Local Swarm" in client.get("/").text
        st = client.get("/api/status").json()
        assert st["roles"]["coordinator"] == "Qwen3.5-4B" and len(st["roles"]["team"]) == 3
        with client.websocket_connect("/ws") as ws:
            assert json.loads(ws.receive_text())["type"] == "pool"
            ws.send_text(json.dumps({"type": "ask", "question": "Tell me about the Eiffel Tower"}))
            final = None
            for _ in range(500):
                e = json.loads(ws.receive_text())
                assert e["type"] != "error", e
                if e["type"] == "final":
                    final = e
                    break
            assert final and "1889" in final["answer"]
        assert client.post("/api/unload").status_code == 200


async def test_role_based_team(cfg, cards, mock_pool_cls, monkeypatch):
    """workers.roles: 2 answerers + fact sheet + premise check + skeptic, all fed into synthesis."""
    import copy
    from swarm import orchestrator as orch
    cfg = copy.deepcopy(cfg)
    cfg["workers"]["roles"] = [
        {"role": "answerer", "model": "Ministral-3-3B-Instruct"},
        {"role": "answerer", "model": "LFM2.5-2.6B"},
        {"role": "facts", "model": "LFM2.5-2.6B"},
        {"role": "premise", "model": "Ministral-3-3B-Instruct"},
        {"role": "skeptic", "model": cfg["verifier"]["model"]},
    ]
    synth_msgs = []
    real_chat = orch.llm.chat

    async def spy(url, msgs, *a, **k):
        if "on_delta" in k:
            synth_msgs.append(msgs)
        return await real_chat(url, msgs, *a, **k)
    monkeypatch.setattr(orch.llm, "chat", spy)

    events = []

    async def emit(e):
        events.append(e)

    pool = mock_pool_cls(cfg, cards)
    try:
        trace = await Swarm(cfg, pool, cards, FakeResearch()).run("Tell me about the Eiffel Tower on the Moon", emit)
    finally:
        await pool.shutdown()
    types = [e["type"] for e in events]
    assert "error" not in types, [e for e in events if e["type"] == "error"]
    assert {r["model"] for r in trace["worker_results"]} == {"Ministral-3-3B-Instruct", "LFM2.5-2.6B"}
    roles = trace["roles"]
    assert set(roles) == {"facts", "premise", "skeptic"}, roles
    assert not any(r.get("error") for r in roles.values()), roles
    assert all(e not in ("E999",) for e in roles["facts"]["data"]["facts"][0]["evidence"]), "unknown ids dropped"
    assert roles["premise"]["data"]["premise_ok"] is False
    assert roles["skeptic"]["data"]["flags"][0]["issue"] == "overcertain"
    assert "E999" not in str(roles["skeptic"]["data"]), "uncited claims are not reviewed"
    assert types.count("role_result") == 3 and "roles" in types
    user = synth_msgs[-1][1]["content"]
    for part in ("FACT SHEET", "PREMISE CHECK", "SKEPTIC'S CAUTIONS", "Blackpool Tower"):
        assert part in user
    assert "FACT SHEET" in synth_msgs[-1][0]["content"]


async def test_worker_strategies(cfg, cards, mock_pool_cls):
    """workers.strategies: the same model three times, each thinking a different way."""
    import copy
    cfg = copy.deepcopy(cfg)
    cfg["workers"]["team"] = ["Ministral-3-3B-Instruct"] * 3
    cfg["workers"]["strategies"] = ["self_ask", "step_back", "direct"]
    events = []

    async def emit(e):
        events.append(e)

    pool = mock_pool_cls(cfg, cards)
    try:
        trace = await Swarm(cfg, pool, cards, FakeResearch()).run("Tell me about the Eiffel Tower", emit)
    finally:
        await pool.shutdown()
    assert not [e for e in events if e["type"] == "error"]
    team = next(e for e in events if e["type"] == "team")["workers"]
    assert [w["model"] for w in team] == ["Ministral-3-3B-Instruct / Self-ask", "Ministral-3-3B-Instruct / Step back",
                                          "Ministral-3-3B-Instruct"]
    assert [w["strategy"] for w in team] == ["self_ask", "step_back", None]
    res = trace["worker_results"]
    assert len(res) == 6 and not any(r.get("error") for r in res)
    by = {r["model"]: r for r in res if r["subq"] == 0}
    assert by["Ministral-3-3B-Instruct / Self-ask"]["reasoning"].startswith("Path A")
    assert by["Ministral-3-3B-Instruct"]["reasoning"] == ""
    # one model, one load, three workers sharing it
    assert trace["stats"]["models"]


async def test_runs_count_tokens_and_solo_can_merge_drafts(cfg, cards, mock_pool_cls):
    """Every run reports total tokens read/written; solo_samples=3 writes 3 drafts then merges them."""
    import copy
    events = []

    async def emit(e):
        events.append(e)

    pool = mock_pool_cls(cfg, cards)
    try:
        sw = Swarm(cfg, pool, cards, FakeResearch())
        prep = await sw.prepare("Tell me about the Eiffel Tower")
        swarm_trace = await sw.run("Tell me about the Eiffel Tower", emit, prepared=prep)
        c2 = copy.deepcopy(cfg)
        c2["mode"], c2["solo_samples"] = "solo", 3
        solo_trace = await Swarm(c2, pool, cards, FakeResearch()).run("Tell me about the Eiffel Tower", emit, prepared=prep)
    finally:
        await pool.shutdown()
    t_swarm = swarm_trace["stats"]["tokens"]
    t_solo = solo_trace["stats"]["tokens"]
    assert t_swarm["calls"] > 5 and t_swarm["completion_tokens"] > 0
    assert t_solo["calls"] == 4, "3 drafts + 1 merge"
    assert len(solo_trace["drafts"]) == 3
    assert sum(1 for e in events if e["type"] == "draft") == 3
    assert "1889" in solo_trace["final"]["answer"]


async def test_gather_uses_news_and_scholarly_sources(cfg, cards, mock_pool_cls, monkeypatch):
    """News hits are fetched before plain web hits, and paper records join the evidence."""
    from swarm import scholar

    class NewsResearch(FakeResearch):
        async def news(self, q, n=4):
            return [{"title": "Tower news", "url": "https://news.example/eiffel", "date": "2026-09-01"}]

    async def fake_papers(query, n=2, sources=None, since=""):
        return {"openalex": [scholar._doc("https://doi.org/10.1/eiffel", "Wrought iron towers", ["A. Engineer"],
                                          "Journal of Towers", "2026-05-01", "article",
                                          "The Eiffel Tower was completed in 1889.", "OpenAlex")],
                "arxiv": RuntimeError("429 Too Many Requests")}
    monkeypatch.setattr(scholar, "search_all", fake_papers)
    events = []

    async def emit(e):
        events.append(e)

    pool = mock_pool_cls(cfg, cards)
    try:
        prep = await Swarm(cfg, pool, cards, NewsResearch()).prepare("Tell me about the Eiffel Tower", emit)
    finally:
        await pool.shutdown()
    kinds = {d["source"] for d in prep["docs"]}
    assert "paper" in kinds
    paper = next(d for d in prep["docs"] if d["source"] == "paper")
    assert "peer-reviewed journal article published in Journal of Towers" in paper["text"]
    fetched = [e["url"] for e in events if e["type"] == "fetch"]
    assert fetched and fetched[0] == "https://news.example/eiffel", "news articles are read first"
    backends = {e.get("backend") for e in events if e["type"] == "search"}
    assert {"web", "news", "openalex", "arxiv"} <= backends
    assert any(e.get("backend") == "arxiv" and e.get("error") for e in events), "a failing source is reported, not fatal"


def test_recent_questions_filter_old_papers():
    import datetime
    from swarm import scholar
    today = datetime.date(2026, 9, 27)
    assert scholar.recent_since("What did LHCb announce in March 2026?", today) == "2024-01-01"
    assert scholar.recent_since("What is the newest planet found?", today) == "2024-01-01"
    assert scholar.recent_since("How does photosynthesis work?", today) == ""


def test_article_extraction_drops_page_furniture():
    from swarm.tools import extract_text
    nav = "".join(f"<li><a href='/s{i}'>{i} min read Some other story {i} article 2 days ago</a></li>" for i in range(30))
    body = " ".join(["Astronomers found the planet, called Gaia23bra b, using TESS data."] * 12)
    html_doc = (f"<html><head><title>T</title></head><body><nav><ul>{nav}</ul></nav>"
                f"<article><h1>NASA's TESS finds a planet</h1><p>{body}</p></article><footer>Privacy policy</footer></body></html>")
    txt = extract_text(html_doc)
    assert txt.lstrip().startswith(("NASA", "Astronomers")) and "min read" not in txt


async def test_split_research_gives_each_part_its_own_searches(cfg, cards, mock_pool_cls):
    import copy
    cfg = copy.deepcopy(cfg)
    cfg["research"]["split_by_subquestion"] = True
    events = []

    async def emit(e):
        events.append(e)

    pool = mock_pool_cls(cfg, cards)
    try:
        trace = await Swarm(cfg, pool, cards, FakeResearch()).run("Tell me about the Eiffel Tower", emit)
    finally:
        await pool.shutdown()
    assert trace.get("error") is None
    queries = {e["query"] for e in events if e["type"] == "search" and e.get("backend") == "web"}
    # the plan's 2 shared queries + one per sub-question
    assert any("built" in q.lower() for q in queries) and any("tall" in q.lower() for q in queries)
    assert len(trace["sources_fetched"]) > 4
    assert "1889" in trace["final"]["answer"]


async def test_reranker_and_guardian_verifier(cfg, cards, mock_pool_cls, isolate_runtime):
    """Passages chosen by a reranker model; claims checked by Granite Guardian's yes/no format."""
    import copy
    c = copy.deepcopy(cfg)
    c["research"]["reranker"] = "Qwen3-Reranker-4B"
    c["verifier"] = {**c["verifier"], "model": "Granite-Guardian-4.1-8B", "style": "guardian"}
    events = []

    async def emit(e):
        events.append(e)
    pool = mock_pool_cls(c, cards)
    try:
        trace = await Swarm(c, pool, cards, FakeResearch()).run("Tell me about the Eiffel Tower", emit)
    finally:
        await pool.shutdown()
    assert not [e for e in events if e["type"] in ("error", "warning")], [e for e in events if e["type"] in ("error", "warning")]
    assert trace["evidence"] and all(isinstance(p["score"], float) and p["score"] <= 1.5 for p in trace["evidence"])
    for r in trace["worker_results"]:
        assert [cl["verdict"] for cl in r["claims"]] == ["supported", "uncited"]
        assert "guardian" in r["claims"][0]["reason"]

    # a reranker that returns nothing useful falls back to keyword ranking, with a warning
    c["research"]["reranker"] = "Broken-Reranker"
    c["verifier"] = cfg["verifier"]
    events.clear()
    pool = mock_pool_cls(c, cards)
    try:
        trace = await Swarm(c, pool, cards, FakeResearch()).run("Tell me about the Eiffel Tower", emit)
    finally:
        await pool.shutdown()
    assert any(e["type"] == "warning" and "reranker" in e["message"] for e in events)
    assert "1889" in trace["final"]["answer"]


async def test_notebook_mode_with_and_without_a_coordinator(cfg, cards, mock_pool_cls):
    """Notebook mode: workers read with running notes, the notes are merged (a fact found by two
    workers is one note with two readers), verified, reviewed in a round, and the answer is
    written from the notebook - by the coordinator, or (leader: none) by a worker plus review."""
    import copy
    events = []

    async def emit(e):
        events.append(e)

    c = copy.deepcopy(cfg)
    c["mode"] = "notebook"
    c["workers"]["team"] = ["Ministral-3-3B-Instruct", "LFM2.5-2.6B", "Phi-4-mini-instruct"]
    c["notebook"] = {"leader": "coordinator", "chunk_passages": 2, "reads_per_passage": 2, "rounds": 1}
    pool = mock_pool_cls(cfg, cards)
    try:
        sw = Swarm(c, pool, cards, FakeResearch())
        prep = await sw.prepare("Tell me about the Eiffel Tower")
        led = await sw.run("Tell me about the Eiffel Tower", emit, prepared=prep)
        c2 = copy.deepcopy(c)
        c2["notebook"]["leader"] = "none"
        free = await Swarm(c2, pool, cards, FakeResearch()).run("Tell me about the Eiffel Tower", emit, prepared=prep)
    finally:
        await pool.shutdown()
    for t in (led, free):
        assert not t.get("error"), t.get("error")
        notes = t["notebook"]["notes"]
        first = next(n for n in notes if "1889" in n["fact"])
        assert len(first["readers"]) >= 2                       # found independently by several workers
        assert not any("E999" in n["sources"] for n in notes)   # unsourced notes are dropped
        assert any(n["added_in"] == "round 1" for n in notes)    # the review round added a note
        assert all(n["status"] == "supported" for n in notes)   # every note was fact-checked
        assert t["stats"]["mode"] == "notebook" and t["stats"]["notebook"]["found_by_2plus"] >= 1
        assert t["stats"]["notebook"]["rejected_notes"] >= 2 and t["stats"]["notebook"]["unchecked"] == 0
        assert not any("?" in n["fact"] or "Additional details" in n["fact"] for n in notes)
        assert t["final"]["answer"]
    assert not led["drafts"]                                     # the coordinator wrote it directly
    assert free["writer"] in free["team"] and free["objections"]  # LFM objected ...
    assert free["drafts"][-1].get("revision")                    # ... so the writer revised once
    assert any(d["by"] == "Phi-4-mini-instruct" for n in led["notebook"]["notes"] for d in n["disputes"])
