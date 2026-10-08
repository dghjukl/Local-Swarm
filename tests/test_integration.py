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
        c3 = copy.deepcopy(c)  # v3: the writer reads what solo reads (top 1 per part) + the notebook
        c3["notebook"].update(writer="evidence+notes", writer_passages_per_subquestion=1)
        c3["research"]["passages_per_subquestion"] = 3
        over = await Swarm(c3, pool, cards, FakeResearch()).run("Tell me about the Eiffel Tower", emit, prepared=prep)
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
    assert not over.get("error") and over["final"]["answer"], over.get("error")
    wv = over["writer_view"]
    assert 1 <= len(wv["passages"]) <= 2 < len(over["evidence"])  # writer: solo-sized view; team: wider
    assert not led["drafts"]                                     # the coordinator wrote it directly
    assert free["writer"] in free["team"] and free["objections"]  # LFM objected ...
    assert free["drafts"][-1].get("revision")                    # ... so the writer revised once
    assert any(d["by"] == "Phi-4-mini-instruct" for n in led["notebook"]["notes"] for d in n["disputes"])


async def test_manager_mode_directs_teammates_turn_by_turn(cfg, cards, mock_pool_cls):
    """Manager mode: the coordinator gives one task per turn (with a web search), gives the same task to
    the other teammate, stops itself, and writes from its evidence + the workspace. With no team it
    does the steps itself."""
    import copy
    events = []

    async def emit(e):
        events.append(e)

    c = copy.deepcopy(cfg)
    c["mode"] = "manager"
    c["workers"]["team"] = ["Ministral-3-3B-Instruct", "Phi-4-mini-instruct"]
    c["manager"] = {"max_cycles": 5, "passages_per_task": 3}
    pool = mock_pool_cls(cfg, cards)
    try:
        sw = Swarm(c, pool, cards, FakeResearch())
        prep = await sw.prepare("Tell me about the Eiffel Tower")
        duo = await sw.run("Tell me about the Eiffel Tower", emit, prepared=prep)
        c2 = copy.deepcopy(c)
        c2["workers"]["team"] = [c2["coordinator"]["model"]]
        alone = await Swarm(c2, pool, cards, FakeResearch()).run("Tell me about the Eiffel Tower", emit, prepared=prep)
    finally:
        await pool.shutdown()
    for t in (duo, alone):
        assert not t.get("error"), t.get("error")
        log = t["manager"]["log"]
        assert len(log) == 2 and all(s["search"] for s in log) and t["final"]["answer"]
        assert t["stats"]["manager"]["stopped_by_coordinator"] and t["stats"]["mode"] == "manager"
        assert t["manager"]["notes"]
    assert [s["worker"] for s in duo["manager"]["log"]] == ["Ministral-3-3B-Instruct", "Phi-4-mini-instruct"]
    assert duo["manager"]["log"][1]["reassigned"] and duo["stats"]["manager"]["reassigned"] == 1
    assert len(alone["team"]) == 1


async def test_manager_both_dispatch_sends_every_task_to_every_teammate(cfg, cards, mock_pool_cls):
    import copy

    async def emit(e):
        pass

    c = copy.deepcopy(cfg)
    c["mode"] = "manager"
    c["workers"]["team"] = ["Ministral-3-3B-Instruct", "Phi-4-mini-instruct"]
    c["manager"] = {"max_cycles": 5, "passages_per_task": 3, "dispatch": "both"}
    pool = mock_pool_cls(cfg, cards)
    try:
        sw = Swarm(c, pool, cards, FakeResearch())
        prep = await sw.prepare("Tell me about the Eiffel Tower")
        t = await sw.run("Tell me about the Eiffel Tower", emit, prepared=prep)
        c2 = copy.deepcopy(c)
        c2["workers"]["team"] = ["Phi-4-mini-instruct", "Phi-4-mini-instruct"]  # two copies on one server
        t2 = await Swarm(c2, pool, cards, FakeResearch()).run("Tell me about the Eiffel Tower", emit, prepared=prep)
    finally:
        await pool.shutdown()
    for tr in (t, t2):
        assert not tr.get("error"), tr.get("error")
        log = tr["manager"]["log"]
        assert len(log) == 2 and all(len(s["results"]) == 2 for s in log)
        st = tr["stats"]["manager"]
        assert st["dispatch"] == "both" and st["both_found"] == 2 and st["agree"] == 2
        assert any(len(n["readers"]) == 2 for n in tr["manager"]["notes"])  # the same fact from both
    assert {x["worker"] for x in t["manager"]["log"][0]["results"]} == {"Ministral-3-3B-Instruct", "Phi-4-mini-instruct"}


async def test_manager_coordinator_styles_run(cfg, cards, mock_pool_cls):
    """step_back and think styles for the coordinator: the loop still runs and the style is recorded."""
    import copy

    async def emit(e):
        pass

    pool = mock_pool_cls(cfg, cards)
    try:
        out = {}
        for style in ("step_back", "think"):
            c = copy.deepcopy(cfg)
            c["mode"] = "manager"
            c["workers"]["team"] = ["Ministral-3-3B-Instruct", "Ministral-3-3B-Instruct"]
            c["manager"] = {"max_cycles": 4, "passages_per_task": 3, "dispatch": "both", "coordinator_style": style}
            sw = Swarm(c, pool, cards, FakeResearch())
            prep = await sw.prepare("Tell me about the Eiffel Tower")
            out[style] = await sw.run("Tell me about the Eiffel Tower", emit, prepared=prep)
    finally:
        await pool.shutdown()
    for style, t in out.items():
        assert not t.get("error"), t.get("error")
        assert t["final"]["answer"] and t["stats"]["manager"]["coordinator_style"] == style
        assert t["manager"]["log"]


async def test_manager_verifies_notes_only_one_teammate_found(cfg, cards, mock_pool_cls):
    import copy

    async def emit(e):
        pass

    c = copy.deepcopy(cfg)
    c["mode"] = "manager"
    c["workers"]["team"] = ["Ministral-3-3B-Instruct", "Phi-4-mini-instruct"]
    c["manager"] = {"max_cycles": 4, "passages_per_task": 3, "dispatch": "both", "verify": True}
    pool = mock_pool_cls(cfg, cards)
    try:
        sw = Swarm(c, pool, cards, FakeResearch())
        prep = await sw.prepare("Tell me about the Eiffel Tower")
        t = await sw.run("Tell me about the Eiffel Tower", emit, prepared=prep)
    finally:
        await pool.shutdown()
    assert not t.get("error"), t.get("error")
    st = t["stats"]["manager"]
    assert st["verify"] is True
    assert st["verify_checked"] >= 1  # Phi's extra fact was found by Phi alone, so it was fact-checked
    for s in t["manager"]["log"]:
        assert all("verified" in x for x in s["results"])
    # both teammates found the same fact: confirmed by the other, so the verifier is not needed for it
    assert any(x["confirmed_by_other"] for s in t["manager"]["log"] for x in s["results"])


async def test_manager_reports_and_expert(cfg, cards, mock_pool_cls):
    """Structured reports reach the coordinator (and taking a suggestion is counted); the coordinator can
    call the expert (X), and a blocked repeat of a failed step goes to the expert automatically."""
    import copy

    async def emit(e):
        pass

    c = copy.deepcopy(cfg)
    c["mode"] = "manager"
    c["workers"]["team"] = ["Ministral-3-3B-Instruct", "Ministral-3-3B-Instruct"]
    c["manager"] = {"max_cycles": 5, "passages_per_task": 3, "dispatch": "both", "reports": True,
                    "expert": {"model": "Qwen3.5-9B", "ctx_per_slot": 4096, "max_calls": 1, "followup_searches": 1}}
    pool = mock_pool_cls(cfg, cards)
    try:
        sw = Swarm(c, pool, cards, FakeResearch())
        prep = await sw.prepare("Tell me about the Eiffel Tower")
        t = await sw.run("Tell me about the Eiffel Tower", emit, prepared=prep)
        stuck = await Swarm(c, pool, cards, FakeResearch()).run("Tell me about the nowhere tower", emit, prepared=prep)
        c3 = copy.deepcopy(c)
        c3["manager"]["expert"]["model"] = "Phi-4-mini-instruct"   # an expert that can't find it either
        miss = await Swarm(c3, pool, cards, FakeResearch()).run("Tell me about the nowhere tower", emit, prepared=prep)
    finally:
        await pool.shutdown()
    assert not t.get("error"), t.get("error")
    log = t["manager"]["log"]
    assert log[0]["results"][0]["report"]["next_search"] == "Eiffel Tower official height"
    assert log[1]["expert"] and log[1]["model"] == "Qwen3.5-9B" and log[1]["found"] and not log[1]["auto"]
    st = t["stats"]["manager"]
    assert st["reports"] and st["expert_calls"] == 1 and st["picks"]["X"] == 1 and st["confidence"]["high"] >= 2
    assert st["suggested_turns"] >= 1
    assert any("Qwen3.5-9B (expert)" in n["readers"] for n in t["manager"]["notes"])

    assert not stuck.get("error"), stuck.get("error")
    slog = stuck["manager"]["log"]
    assert not slog[0]["found"]                                  # both teammates came back empty
    assert slog[1]["expert"] and slog[1]["auto"] and slog[1]["found"]  # the repeat went to the expert
    assert slog[1]["search"] == ""                               # the failed search was not rerun
    assert slog[2].get("repeat")                                 # no expert calls left: skipped
    assert stuck["stats"]["manager"]["expert_auto"] == 1
    # the expert came back empty, so it ran its own suggested follow-up search and read again
    assert not miss.get("error"), miss.get("error")
    mx = miss["manager"]["log"][1]
    assert mx["expert"] and not mx["found"] and mx["expert_searches"] == ["nowhere fact official"]
    assert miss["stats"]["manager"]["expert_searches"] == 1 and miss["final"]["answer"]


async def test_manager_attempts_and_vote(cfg, cards, mock_pool_cls):
    """Several independent manager attempts (different temperature / worker pair), then the coordinator
    votes; adaptive mode stops after two attempts that agree."""
    import copy

    async def emit(e):
        pass

    c = copy.deepcopy(cfg)
    c["mode"] = "manager"
    c["workers"]["team"] = ["Ministral-3-3B-Instruct", "Phi-4-mini-instruct"]
    c["manager"] = {"max_cycles": 3, "passages_per_task": 3, "dispatch": "both",
                    "attempts": {"runs": [{"temperature": 0.2}, {"temperature": 0.7},
                                          {"temperature": 0.7, "team": ["Phi-4-mini-instruct", "Phi-4-mini-instruct"]}]}}
    pool = mock_pool_cls(cfg, cards)
    try:
        sw = Swarm(c, pool, cards, FakeResearch())
        prep = await sw.prepare("Tell me about the Eiffel Tower")
        t = await sw.run("Tell me about the Eiffel Tower", emit, prepared=prep)
        c2 = copy.deepcopy(c)
        c2["manager"]["attempts"]["adaptive"] = True
        t2 = await Swarm(c2, pool, cards, FakeResearch()).run("Do the sources agree on the Eiffel Tower?", emit,
                                                              prepared=prep)
    finally:
        await pool.shutdown()
    assert not t.get("error"), t.get("error")
    st = t["stats"]["attempts"]
    assert st["runs"] == 3 and st["chosen"] == 2 and len(t["votes"]) == 1 and len(t["attempts"]) == 3
    assert t["final"]["answer"] == t["attempts"][1]["answer"]
    assert t["attempts"][2]["config"]["team"] == ["Phi-4-mini-instruct", "Phi-4-mini-instruct"]
    assert t["attempts"][2]["manager"]["log"][0]["model"] == "Phi-4-mini-instruct+Phi-4-mini-instruct"
    assert sw.cfg is c                                   # the base config is restored
    assert not t2.get("error"), t2.get("error")
    st2 = t2["stats"]["attempts"]
    assert st2["runs"] == 2 and st2["first2_same"] is True and st2["planned"] == 3


async def test_manager_trust_check_sends_team_back_then_passes(cfg, cards, mock_pool_cls):
    """Before finishing, the coordinator lays out the answer's chain. Code catches the made-up citation and
    the wrong arithmetic, so the team goes back to work; the second check passes and the answer is written."""
    import copy

    async def emit(e):
        pass

    c = copy.deepcopy(cfg)
    c["mode"] = "manager"
    c["workers"]["team"] = ["Ministral-3-3B-Instruct", "Phi-4-mini-instruct"]
    c["manager"] = {"max_cycles": 3, "passages_per_task": 3, "dispatch": "both",
                    "trust_check": {"rounds": 2, "extra_cycles": 2}}
    pool = mock_pool_cls(cfg, cards)
    try:
        sw = Swarm(c, pool, cards, FakeResearch())
        prep = await sw.prepare("Tell me about the Eiffel Tower")
        t = await sw.run("Tell me about the Eiffel Tower", emit, prepared=prep)
    finally:
        await pool.shutdown()
    assert not t.get("error"), t.get("error")
    st = t["stats"]["manager"]
    trust = t["manager"]["trust"]
    assert st["trust_check"] and st["trust_checks"] == 2 and st["trust_sent_back"] == 1
    first, last = trust[0], trust[-1]
    assert first["said_ready"] and not first["ready"]                 # the lead said ready, the check disagreed
    assert first["calc"]["ok"] is False and st["trust_calc_wrong"] == 1
    assert st["trust_bad_citation"] == 1 and any("E999" in x["bad_sources"] for x in first["steps"])
    assert any("unsupported" in p for p in first["problems"])
    assert last["ready"] and st["trust_final_ready"] is True
    assert any(s.get("trust") for s in t["manager"]["log"])           # the gaps went back into the workspace
    assert t["final"]["answer"]


async def test_manager_charter_nudge_reaches_lead_and_workers(cfg, cards, mock_pool_cls, monkeypatch):
    """manager.charter {lead, workers} puts the short partner charter at the top of MiMo's prompts (decide and
    write) and the workers' prompts, and the worker honesty counters are recorded."""
    import copy
    from swarm import llm as llm_mod
    from swarm import manager as mgr

    seen = []
    real_json, real_chat = llm_mod.chat_json, llm_mod.chat

    async def spy_json(url, msgs, *a, **kw):
        seen.append(msgs[0]["content"])
        return await real_json(url, msgs, *a, **kw)

    async def spy_chat(url, msgs, *a, **kw):
        seen.append(msgs[0]["content"])
        return await real_chat(url, msgs, *a, **kw)

    monkeypatch.setattr(llm_mod, "chat_json", spy_json)
    monkeypatch.setattr(llm_mod, "chat", spy_chat)

    async def emit(e):
        pass

    c = copy.deepcopy(cfg)
    c["mode"] = "manager"
    c["workers"]["team"] = ["Ministral-3-3B-Instruct", "Phi-4-mini-instruct"]
    c["manager"] = {"max_cycles": 2, "passages_per_task": 3, "dispatch": "both",
                    "charter": {"lead": True, "workers": True}}
    pool = mock_pool_cls(cfg, cards)
    try:
        sw = Swarm(c, pool, cards, FakeResearch())
        prep = await sw.prepare("Tell me about the Eiffel Tower")
        t = await sw.run("Tell me about the Eiffel Tower", emit, prepared=prep)
    finally:
        await pool.shutdown()
    assert not t.get("error"), t.get("error")
    st = t["stats"]["manager"]
    assert st["charter"] == {"lead": True, "workers": True}
    assert any(s.startswith(mgr.CHARTER_WORKER) and "research assistant" in s for s in seen)
    assert any(s.startswith(mgr.CHARTER_LEAD) and "lead a small research team" in s for s in seen)
    assert any(s.startswith(mgr.CHARTER_LEAD) and "final answer" in s for s in seen)
    assert st["worker_answers"] >= 2 and st["worker_notes_offered"] >= st["worker_notes_kept"] >= 0
    assert "worker_bad_citations" in st and "worker_found_unbacked" in st
    assert any("candidates" in e and "read_urls" in e for e in t["manager"]["log"])  # pages found vs read, per task
