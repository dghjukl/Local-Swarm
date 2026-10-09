"""Resolver test (plan step 4): stuck questions, the research packet, make -> grade -> compare."""
import json
from contextlib import asynccontextmanager
from types import SimpleNamespace

from swarm import resolver_bench as R


def _attempt(answer, ready, claim, sid, url):
    return {"answer": answer, "sources": [{"id": sid, "url": url, "title": "T", "snippet": "snippet " + claim}],
            "manager": {"trust": [{"ready": ready, "steps": [{"claim": claim, "status": "supported",
                                                               "sources": [sid]}]}],
                        "notes": []}}


def _toy_run(tmp_path):
    run = tmp_path / "run"
    (run / "traces").mkdir(parents=True)
    rows = []
    # q1: attempts disagree (stuck); q2: one answer and READY (clear); q3: one answer, nobody READY (stuck)
    traces = {
        "q1": [_attempt("Lyon.", False, "Lyon is big", "E1", "https://a/1"),
               _attempt("Paris.", True, "Paris is the capital", "E1", "https://b/2")],   # same id, other page
        "q2": [_attempt("Paris.", True, "x", "E1", "https://a/1"), _attempt("Paris.", True, "x", "E1", "https://a/1")],
        "q3": [_attempt("Rome.", False, "y", "E2", "https://c/3"), _attempt("Rome.", None, "y", "E2", "https://c/3")],
    }
    for qid, atts in traces.items():
        t = {"question": f"question {qid}", "attempts": atts,
             "evidence": [{"id": "E1", "url": "https://a/1", "title": "A", "text": "shared passage"}],
             "votes": [{"short": [a["answer"].rstrip(".") for a in atts]}]}
        (run / "traces" / f"{qid}.json").write_text(json.dumps(t))
        rows.append({"config": "mgr-x", "question_id": qid, "question": t["question"], "trace": f"traces/{qid}.json",
                     "answer": atts[0]["answer"], "grade": {"score": 1.0 if qid == "q2" else 0.0},
                     "evidence_web_pages": 5, "total_seconds": 100})
    (run / "results.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows))
    (run / "meta.json").write_text(json.dumps({"question_set": "evals/x.yaml", "configs": ["mgr-x"]}))
    return run


def test_stuck_reasons_and_packet(tmp_path):
    assert R.stuck_reason(["Paris", "Lyon"], [True, False]) == "split"
    assert R.stuck_reason(["Paris", "Paris"], [None, False]) == "not_ready"
    assert R.stuck_reason(["Paris", "Lyon"], [None, False]) == "split+not_ready"
    assert R.stuck_reason(["Paris", "Lyon"], [None, None]) == "split"        # no trust check in that run
    assert R.stuck_reason(["Paris", "Paris"], [None, None]) is None
    assert R.stuck_reason(["Paris", "paris."], [True, None]) is None
    run = _toy_run(tmp_path)
    items = R.load_stuck(run, "mgr-x", None)
    assert [i["row"]["question_id"] for i in items] == ["q1", "q3"]
    assert [i["reason"] for i in items] == ["split", "not_ready"]
    packet, info = R.build_packet(items[0]["trace"], 2)
    assert "QUESTION: question q1" in packet and "### Attempt 2" in packet and "Trust check: READY" in packet
    # attempt 2 cited "E1" but meant another page: it gets its own id, and its fact chain points at it
    assert "[E1-2]" in packet and "Paris is the capital [supported; E1-2]" in packet
    assert info["passages_total"] == 2 and info["attempts"] == 2


async def test_make_then_compare(tmp_path, monkeypatch):
    from swarm import config, llm, pool, registry

    run = _toy_run(tmp_path)
    out = tmp_path / "res"
    seen = []

    class FakePool:
        def __init__(self, cfg, cards):
            self.cards = {"Big": object()}

        @asynccontextmanager
        async def use(self, model, ctx, parallel=1, pin=False):
            yield "http://fake"

        async def shutdown(self):
            pass

    async def fake_chat(url, messages, **kw):
        seen.append(messages[1]["content"])
        return SimpleNamespace(text="FINAL ANSWER: Paris\nWHY: [E1-2]", reasoning="", prompt_tokens=50,
                               completion_tokens=9)

    monkeypatch.setattr(pool, "ModelPool", FakePool)
    monkeypatch.setattr(config, "load_config", lambda: {})
    monkeypatch.setattr(registry, "scan_models", lambda: {})
    monkeypatch.setattr(llm, "chat", fake_chat)
    args = SimpleNamespace(run=str(run), config="mgr-x", model="Big", out=str(out), name=None, k=None, all=False,
                           limit=None, think=False, ctx=8192, max_chars=60000, max_tokens=500, timeout=60,
                           min_free_ram_mb=0, max_fails=3)
    assert await R.make(args) == 0
    rows = [json.loads(l) for l in (out / "results.jsonl").read_text().splitlines()]
    assert {(r["config"], r["question_id"]) for r in rows} == {
        (R.BASELINE, "q1"), (R.BASELINE, "q3"), ("resolver-Big", "q1"), ("resolver-Big", "q3")}
    assert len(seen) == 2
    meta = json.loads((out / "meta.json").read_text())
    assert meta["configs"] == [R.BASELINE, "resolver-Big"] and meta["question_set"] == "evals/x.yaml"
    assert await R.make(args) == 0 and len(seen) == 2            # already done: nothing is asked again
    # pretend the judge graded them: the vote was wrong on both, the resolver rescues q1 and misses q3
    for r in rows:
        r["grade"] = {"score": 1.0 if (r["config"] != R.BASELINE and r["question_id"] == "q1") else 0.0}
    (out / "results.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows))
    text = R.compare(out)
    assert "| resolver-Big | 2 | 0 | 1 | 1 | 0 | +1 |" in text and "Rescued: q1" in text
    assert (out / "resolver_report.md").exists()


async def test_failed_answers_are_retried_and_repeated_failures_stop(tmp_path, monkeypatch):
    """J5: the model server died, every later question failed instantly and was stored as answered.
    Now: stop after max_fails failures in a row, and ask failed questions again on the next run."""
    from swarm import config, llm, pool, procs, registry

    run = _toy_run(tmp_path)
    out = tmp_path / "res"

    class FakePool:
        def __init__(self, cfg, cards):
            self.cards = {"Big": object()}

        @asynccontextmanager
        async def use(self, model, ctx, parallel=1, pin=False):
            yield "http://fake"

        async def shutdown(self):
            pass

    state = {"up": False, "calls": 0}

    async def flaky_chat(url, messages, **kw):
        state["calls"] += 1
        if not state["up"]:
            raise llm.LLMError("request failed: All connection attempts failed")
        return SimpleNamespace(text="FINAL ANSWER: Paris", reasoning="", prompt_tokens=5, completion_tokens=3)

    monkeypatch.setattr(pool, "ModelPool", FakePool)
    monkeypatch.setattr(config, "load_config", lambda: {})
    monkeypatch.setattr(registry, "scan_models", lambda: {})
    monkeypatch.setattr(llm, "chat", flaky_chat)
    args = SimpleNamespace(run=str(run), config="mgr-x", model="Big", out=str(out), name=None, k=None, all=False,
                           limit=None, think=False, ctx=8192, max_chars=60000, max_tokens=500, timeout=60,
                           min_free_ram_mb=0, max_fails=1)
    assert await R.make(args) == 4 and state["calls"] == 1          # stopped at the first failure
    state["up"] = True
    args.max_fails = 3
    assert await R.make(args) == 0 and state["calls"] == 3          # the failed one asked again, plus the other
    rows = [json.loads(l) for l in (out / "results.jsonl").read_text().splitlines()]
    res = [r for r in rows if r["config"] == "resolver-Big"]
    assert len(res) == 2 and not any(r.get("error") for r in res)
    # the RAM guard stops before asking anything
    monkeypatch.setattr(procs, "system_ram_mb", lambda: (400, 16000))
    args.name, args.min_free_ram_mb = "other", 1500
    assert await R.make(args) == 3 and state["calls"] == 3
