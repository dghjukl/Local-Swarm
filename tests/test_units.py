from swarm import evidence as ev
from swarm.llm import extract_json, strip_think
from swarm.orchestrator import Swarm
from swarm.speech import speakable
from swarm.tools import Doc


def test_registry_labs_and_quant(cards):
    q = cards["Qwen3.5-4B"]
    assert q.lab == "Alibaba Qwen" and q.lineage == "Qwen"
    assert q.path.endswith("Q5_K_M.gguf"), "prefers Q5_K_M over Q8_0"
    assert q.mmproj and "mmproj" in q.mmproj
    assert cards["Qwen3-Embedding-0.6B"].kind == "embedding"
    assert cards["Granite-4.1-3B"].lab == "IBM"


def test_team_is_lineage_diverse(cfg, cards):
    sw = Swarm(cfg, pool=None, cards=cards, research=None)
    team = sw.team()
    assert len(team) == 3
    assert cfg["verifier"]["model"] not in team and cfg["coordinator"]["model"] not in team
    assert len({cards[m].lineage for m in team}) == 3
    assert sw.check_roster() == []


def test_chunk_and_select():
    text = ("The Eiffel Tower was completed in 1889 for the World's Fair. " * 5 + "\n\n"
            + "Paris is the capital of France and has many museums. " * 5 + "\n\n"
            + "Home\nAbout\nContact us\n")
    docs = [Doc("https://a.example/x", "Tower", text, "web"), Doc("https://b.example/y", "Bad", "", "web", error="404")]
    ps = ev.build_passages(docs, size=300)
    assert ps and all(p.url == "https://a.example/x" for p in ps)
    assert all("Contact us" not in p.text for p in ps), "nav crumbs removed"
    top = ev.select(ps, ["when was the eiffel tower completed"], k=3, per_source=1)
    assert "1889" in top[0].text
    assert len(top) <= 2, "per_source=1, plus at most the lead's on-topic continuation"
    if len(top) == 2:
        assert (top[0].pos, top[1].pos) == (0, 1)
    ids = ev.assign_ids([top, top])
    assert [p.id for p in ids] == [f"E{i + 1}" for i in range(len(top))], "duplicates share one id"


def test_clean_links():
    assert ev.clean("See [the docs](https://x.y/a_(b)) now, please read.") == "See the docs now, please read."


def test_json_helpers():
    assert extract_json('Sure!\n```json\n{"a": 1}\n```') == {"a": 1}
    assert strip_think("<think>hmm</think>Answer") == "Answer"
    assert strip_think("reasoning...</think>\nAnswer") == "Answer"


def test_cite_filters_unknown_ids():
    by_id = {"E1": ev.Passage("E1", "https://a", "A", "text a", "web"),
             "E2": ev.Passage("E2", "https://b", "B", "text b", "web")}
    text, src = Swarm._cite("Fact [E1]. Other [E2, E9]. Bogus [E7].", by_id)
    assert text == "Fact [E1]. Other [E2]. Bogus."
    assert [s["id"] for s in src] == ["E1", "E2"]


def test_speakable():
    assert speakable("**Yes** it is [E1, E2].\n- item") == "Yes it is.\nitem"


def test_evidence_ids_are_normalised():
    from swarm.orchestrator import _evidence_ids
    assert _evidence_ids([":E3", "[E5]"]) == ["E3", "E5"]
    assert _evidence_ids(["Publication details in [E5"]) == ["E5"]
    assert _evidence_ids(["Discovery in [E1], [E2], [E4]"]) == ["E1", "E2", "E4"]
    assert _evidence_ids("E7") == ["E7"]


def test_clean_drops_page_furniture():
    raw = ("### Explore by section\n* Home\n* News\nCheck your subscription status, update your details.\n"
           "# News from Brown ## Site Navigation\n"
           "## Faster chemical process\n"
           "The research shows that a newly identified chemical reaction can build these molecules much faster.")
    out = ev.clean(raw)
    assert "Explore" not in out and "subscription" not in out and "Site Navigation" not in out
    assert out.startswith("The research shows")


def test_premise_quote_must_be_in_the_evidence():
    from swarm.evidence import Passage
    from swarm.orchestrator import _quote_found
    import inspect
    params = inspect.signature(Passage).parameters
    kw = {k: "" for k in params}
    kw.update({"id": "E1", "text": "The Roman telescope has not yet released its first science images, NASA said."})
    for k, v in params.items():
        if v.annotation in ("int", int) and k != "id":
            kw[k] = 0
    ps = [Passage(**kw)]
    assert _quote_found("The Roman telescope has not yet released its first science images", ps)
    assert not _quote_found("The passages show no such discovery happened in 2026 at all", ps)
    assert not _quote_found("too short", ps)


async def test_extraction_runs_in_worker_process_and_survives_a_crash(monkeypatch):
    """A native crash in the page parser must kill only the worker, not the run."""
    import os
    from swarm import tools
    monkeypatch.delenv("SWARM_EXTRACT_INPROCESS", raising=False)
    page = "<html><body><article>" + "<p>The tower was completed in 1889 and is 330 m tall.</p>" * 20 + "</article></body></html>"
    txt = await tools.extract_isolated(page, "https://example.org/a")
    assert "1889" in txt
    # kill the workers behind the pool's back: the next call fails cleanly, the one after works again
    for p in list(tools._pool()._processes.values()):
        os.kill(p.pid, 9)
    try:
        await tools.extract_isolated(page, "https://example.org/b")
    except Exception:
        pass
    txt = await tools.extract_isolated(page, "https://example.org/c")
    assert "1889" in txt
    tools._pool().shutdown()
    tools._extract_pool = None


def test_forced_thinker_no_grammar_and_response_tags(monkeypatch):
    import asyncio
    from swarm import llm
    seen = {}

    async def fake(base_url, messages, **kw):
        seen.update(kw)
        return llm.ChatResult(text=llm.strip_think('plan</think>\n\n<response>\n{"a": 1}\n</response>'))

    monkeypatch.setattr(llm, "_chat", fake)
    llm.FORCED_THINKING.add("http://127.0.0.1:9")
    try:
        res = asyncio.run(llm.chat("http://127.0.0.1:9/", [], schema={"type": "object"}, max_tokens=800))
    finally:
        llm.FORCED_THINKING.discard("http://127.0.0.1:9")
    assert seen["grammar"] is False and seen["max_tokens"] == 3200 and res.data == {"a": 1}


def test_scholarly_query_cleanup():
    from swarm.scholar import key_terms, plain_query
    assert "?" not in plain_query("What did the fossils reveal?")            # OpenAlex wildcard -> 400
    assert plain_query("UK Prime Minister -") == "UK Prime Minister"          # ADS operator -> 400
    assert plain_query("pharaoh 1290-1200 BC Roman-era") == "pharaoh 1290 1200 BC Roman-era"
    assert key_terms("What did the 567-million-year-old fossils found in Canada's Mackenzie reveal?", 4) == \
        ["567-million-year-old", "fossils", "found", "Canada"]


def test_forced_thinker_gets_json_request_then_rewrite(monkeypatch):
    import asyncio
    from swarm import llm
    calls = []

    async def fake(base_url, messages, **kw):
        calls.append(messages)
        text = "**Mode**: research" if len(calls) == 1 else '{"mode": "research"}'
        return llm.ChatResult(text=text)

    monkeypatch.setattr(llm, "_chat", fake)
    llm.FORCED_THINKING.add("http://127.0.0.1:9")
    try:
        res = asyncio.run(llm.chat_json("http://127.0.0.1:9", [{"role": "user", "content": "plan"}],
                                        {"type": "object"}))
    finally:
        llm.FORCED_THINKING.discard("http://127.0.0.1:9")
    assert res.data == {"mode": "research"}
    assert "JSON schema" in calls[0][-1]["content"]
    assert calls[1][-2] == {"role": "assistant", "content": "**Mode**: research"}


def test_json_list_instead_of_object_is_retried(monkeypatch):
    import asyncio
    from swarm import llm
    replies = iter(['["research", "a"]', '[{"mode": "research"}]'])

    async def fake(base_url, messages, **kw):
        return llm.ChatResult(text=next(replies))

    monkeypatch.setattr(llm, "_chat", fake)
    res = asyncio.run(llm.chat_json("http://x", [{"role": "user", "content": "plan"}], {"type": "object"}))
    assert res.data == {"mode": "research"}


def test_nemotron_gets_no_think_switch(monkeypatch):
    import asyncio
    from swarm import llm
    seen = []

    async def fake(base_url, messages, **kw):
        seen.append(messages)
        return llm.ChatResult(text="ok")

    monkeypatch.setattr(llm, "_chat", fake)
    llm.NO_THINK_SWITCH.add("http://n")
    try:
        asyncio.run(llm.chat("http://n", [{"role": "system", "content": "Be brief."}, {"role": "user", "content": "q"}]))
        asyncio.run(llm.chat("http://n", [{"role": "user", "content": "q"}]))
        asyncio.run(llm.chat("http://n", [{"role": "user", "content": "q"}], think=True))
    finally:
        llm.NO_THINK_SWITCH.discard("http://n")
    assert seen[0][0]["content"] == "Be brief. /no_think"
    assert seen[1][0] == {"role": "system", "content": "/no_think"}
    assert len(seen[2]) == 1                                   # thinking wanted: left alone


def test_stop_words_reach_the_server(monkeypatch):
    import asyncio
    import httpx
    from swarm import llm
    sent = {}

    class Resp:
        status_code = 200
        def json(self):
            return {"choices": [{"message": {"content": "Paris."}}], "usage": {}}

    async def post(self, url, json=None):
        sent.update(json)
        return Resp()

    monkeypatch.setattr(httpx.AsyncClient, "post", post)
    llm.STOP_WORDS["http://c"] = ["<|END_OF_TURN_TOKEN|>"]
    try:
        asyncio.run(llm.chat("http://c", [{"role": "user", "content": "q"}]))
    finally:
        llm.STOP_WORDS.pop("http://c", None)
    assert sent["stop"] == ["<|END_OF_TURN_TOKEN|>"]


def test_notebook_v2_merging_filters_and_citations():
    from swarm import notebook as nb
    # the same fact in two wordings is one note; different numbers never merge
    assert nb.same_fact("Antarctica gained 695 billion tonnes of ice between 2021 and 2023.",
                        "Between 2021 and 2023 Antarctica gained about 695 billion tonnes of ice-sheet mass.")
    assert not nb.same_fact("LZ saw a 2.6 sigma excess in its data.", "LZ saw a 3.4 sigma excess in its data.")
    # junk notes and fake open questions are dropped
    assert nb.clean_fact("What new wild cat species was described in 2026?") is None
    assert nb.clean_fact("Additional details from new passages") is None
    assert nb.clean_fact("**Problem**") is None
    assert nb.clean_fact("- The tower was completed in 1889.") == "The tower was completed in 1889."
    assert nb.clean_question("Genetic data confirmed the species.") is None
    assert nb.clean_question("Who designed it") == "Who designed it?"
    book = nb.Notebook({"E1", "E2"})
    assert book.add("The tower was completed in 1889.", ["E1"], "a")
    assert book.add("The Eiffel Tower was completed in the year 1889.", ["E2"], "b").readers == ["a", "b"]
    assert book.add("Additional details from new passages", ["E1"], "a") is None and book.rejected == 1
    view = book.render_for_writer()
    assert "N1" not in view and "[E1, E2]" in view and "verified" not in view.lower().split("(")[0]
    # note ids and status tags a writer copied are removed, E-citations kept
    out = nb.clean_citations("Shift found [N10, N7]. It was 1889 [VERIFIED; found by 2] [E1, N3]. [E7], [N6]")
    assert "N1" not in out and "N3" not in out and "VERIFIED" not in out and "[E1]" in out and "[E7]" in out
