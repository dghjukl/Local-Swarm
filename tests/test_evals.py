"""End-to-end test of the eval harness with the mock llama-server and fake web."""
import json
from types import SimpleNamespace

from swarm import evals
from test_integration import FakeResearch


class StartableFake(FakeResearch):
    name = "fake"

    async def start(self):
        pass


async def test_harness_runs_grades_and_reports(cfg, cards, mock_pool_cls, tmp_path, monkeypatch):
    monkeypatch.setattr(evals, "load_config", lambda: cfg)
    monkeypatch.setattr(evals, "scan_models", lambda: cards)
    monkeypatch.setattr(evals, "ModelPool", mock_pool_cls)
    monkeypatch.setattr(evals, "RUNTIME", tmp_path / "runtime")
    monkeypatch.setattr(evals, "research_mcp_available", lambda cfg=None: True)
    monkeypatch.setattr(evals, "ResearchMCP", lambda n=3: StartableFake())
    monkeypatch.setattr(evals, "swarm_already_running", lambda c: False)
    monkeypatch.setattr(evals.procs, "gpu_memory_mb", lambda: (5000, 16000))

    args = SimpleNamespace(set="evals/research_v3.yaml", configs="baseline",
                           questions="lz-2026,pah-pathway-2026", repeats=1, reuse_evidence=None,
                           regrade=None, resume=None, no_judge=False, no_open=True)
    out = await evals.run(args)

    results = [json.loads(l) for l in (out / "results.jsonl").read_text(encoding="utf-8").splitlines()]
    assert len(results) == 8  # 2 questions x 4 configs
    assert {r["config"] for r in results} == {"swarm-mixed", "coordinator-only", "single-large", "same-model-x3"}
    assert all(not r["error"] for r in results), [r["error"] for r in results if r["error"]]
    assert all(r["grade"]["letter"] in "ABCDF" for r in results)
    solo = [r for r in results if r["config"] == "single-large"]
    assert all(r["coordinator"] == "Qwen3.5-9B" and r["mode"] == "solo" and not r["workers"] for r in solo)
    same = [r for r in results if r["config"] == "same-model-x3"][0]
    assert sorted({w["model"] for w in same["workers"]}) == ["Phi-4-mini-instruct#1", "Phi-4-mini-instruct#2",
                                                             "Phi-4-mini-instruct#3"]
    assert all(r["peak_vram_mb"] == 5000 for r in results)
    assert (out / "evidence" / "lz-2026.json").exists()
    assert all((out / r["trace"]).exists() for r in results)
    html = (out / "report.html").read_text(encoding="utf-8")
    assert "Leaderboard" in html and "single-large" in html and "Phi-4-mini-instruct" in html
    assert "report" in (out / "report.md").read_text(encoding="utf-8").lower() or "Leaderboard" in (out / "report.md").read_text(encoding="utf-8")

    # evidence reuse: a second run with --reuse-evidence must not touch the web
    class NoWeb(StartableFake):
        async def search(self, q, n=5):
            raise AssertionError("web used despite reuse")
    monkeypatch.setattr(evals, "ResearchMCP", lambda n=3: NoWeb())
    args2 = SimpleNamespace(**{**vars(args), "configs": "coordinator-only", "reuse_evidence": str(out), "no_judge": True})
    out2 = await evals.run(args2)
    r2 = [json.loads(l) for l in (out2 / "results.jsonl").read_text(encoding="utf-8").splitlines()]
    assert len(r2) == 2 and all(not r["error"] for r in r2)

    # regrade an existing folder without new runs
    args3 = SimpleNamespace(**{**vars(args), "regrade": str(out2)})
    await evals.run(args3)
    r3 = [json.loads(l) for l in (out2 / "results.jsonl").read_text(encoding="utf-8").splitlines()]
    assert all("grade" in r for r in r3)


async def test_resume_after_interruption(cfg, cards, mock_pool_cls, tmp_path, monkeypatch):
    monkeypatch.setattr(evals, "load_config", lambda: cfg)
    monkeypatch.setattr(evals, "scan_models", lambda: cards)
    monkeypatch.setattr(evals, "ModelPool", mock_pool_cls)
    monkeypatch.setattr(evals, "RUNTIME", tmp_path / "runtime")
    monkeypatch.setattr(evals, "research_mcp_available", lambda cfg=None: True)
    monkeypatch.setattr(evals, "ResearchMCP", lambda n=3: StartableFake())
    monkeypatch.setattr(evals, "swarm_already_running", lambda c: False)
    args = SimpleNamespace(set="evals/research_v1.yaml", configs="coordinator-only,swarm-t1",
                           questions="lz-2026,pah-pathway-2026", repeats=1, reuse_evidence=None,
                           regrade=None, resume=None, no_judge=True, no_open=True)
    out = await evals.run(args)
    lines = (out / "results.jsonl").read_text(encoding="utf-8").splitlines()
    # simulate a power cut after 3 runs, with the last line half-written
    (out / "results.jsonl").write_text("\n".join(lines[:3]) + "\n" + lines[3][:40])

    class NoWeb(StartableFake):
        async def search(self, q, n=5):
            raise AssertionError("web used on resume")
    monkeypatch.setattr(evals, "ResearchMCP", lambda n=3: NoWeb())
    ran = []
    real_summarize = evals.summarize_run
    monkeypatch.setattr(evals, "summarize_run", lambda *a, **k: ran.append(a[0]) or real_summarize(*a, **k))
    args2 = SimpleNamespace(set="ignored", configs=None, questions=None, repeats=9, reuse_evidence=None,
                            regrade=None, resume="last", no_judge=True, no_open=True)
    out2 = await evals.run(args2)
    assert out2 == out
    assert ran == ["swarm-t1"]  # only the one missing run was redone
    rs = [json.loads(l) for l in (out / "results.jsonl").read_text(encoding="utf-8").splitlines()]
    assert sorted((r["config"], r["question_id"]) for r in rs) == sorted(
        [(c, q) for c in ("coordinator-only", "swarm-t1") for q in ("lz-2026", "pah-pathway-2026")])


def test_expand_configs_matrices_and_nested_groups():
    from swarm.evals import expand_configs
    econf = {"configs": {"a": {"overrides": {}}},
             "matrices": {"solo-t": {"name": "solo-{model}", "description": "{model} alone",
                                     "models": ["M1", "M2"],
                                     "overrides": {"mode": "solo", "coordinator": {"model": "{model}"}}}},
             "groups": {"big": ["a", "solo-t"]}}
    e = expand_configs(econf)
    assert e["configs"]["solo-M2"] == {"description": "M2 alone",
                                       "overrides": {"mode": "solo", "coordinator": {"model": "M2"}}}
    assert e["groups"]["solo-t"] == ["solo-M1", "solo-M2"]
    assert e["groups"]["big"] == ["a", "solo-M1", "solo-M2"]


def test_rubric_key_changes_with_checklist():
    from swarm.evals import rubric_key
    q = {"must": ["x"], "details": ["y"], "must_not": []}
    assert rubric_key(q) == rubric_key(dict(q))
    assert rubric_key(q) != rubric_key({**q, "must": ["x2"]})


def test_violation_needs_a_real_quote_from_the_answer():
    from swarm.evals import _in_answer
    ans = "The CAR-T cells eliminated tumours in mice. It has not yet been tested in patients."
    assert _in_answer("It has not yet been tested in patients", ans)
    assert not _in_answer("It cured glioblastoma in patients", ans)
    assert not _in_answer("", ans)


async def test_live_mode_each_run_does_its_own_research(cfg, cards, mock_pool_cls, tmp_path, monkeypatch):
    """--live: no shared evidence folder; every configuration plans and searches for itself."""
    import argparse, json
    from swarm import evals
    from test_integration import FakeResearch
    monkeypatch.setattr(evals, "RUNTIME", tmp_path)
    monkeypatch.setattr(evals, "load_config", lambda: cfg)
    monkeypatch.setattr(evals, "scan_models", lambda: cards)
    monkeypatch.setattr(evals, "ModelPool", mock_pool_cls)
    monkeypatch.setattr(evals, "research_mcp_available", lambda cfg=None: False)
    monkeypatch.setattr(evals, "DirectResearch", FakeResearch)
    monkeypatch.setattr(evals, "swarm_already_running", lambda c: False)
    monkeypatch.setattr(evals.procs, "gpu_memory_mb", lambda: (5000, 16000))
    async def fake_wiki(q, n=2):
        return []
    monkeypatch.setattr("swarm.orchestrator.wikipedia", fake_wiki)
    qfile = tmp_path / "q.yaml"
    qfile.write_text("- id: eiffel\n  question: When was the Eiffel Tower completed?\n  must: [completed in 1889]\n",
                     encoding="utf-8")
    args = argparse.Namespace(set=str(qfile), configs="coordinator-only", questions=None, repeats=1,
                              reuse_evidence=None, regrade=None, resume=None, no_judge=True, no_open=True, live=True)
    out = await evals.run(args)
    meta = json.loads((out / "meta.json").read_text(encoding="utf-8"))
    assert meta["live"] is True and meta["evidence"].startswith("live")
    assert not list((out / "evidence").glob("*.json")), "nothing shared between configurations"
    r = json.loads((out / "results.jsonl").read_text(encoding="utf-8").splitlines()[0])
    assert not r.get("error") and "1889" in r["answer"]


async def test_strategy_screen(cfg, cards, mock_pool_cls, tmp_path, monkeypatch):
    """Worker-only runs: graded answer = the worker's own answers; built-in thinking is recorded."""
    monkeypatch.setattr(evals, "load_config", lambda: cfg)
    monkeypatch.setattr(evals, "scan_models", lambda: cards)
    monkeypatch.setattr(evals, "ModelPool", mock_pool_cls)
    monkeypatch.setattr(evals, "RUNTIME", tmp_path / "runtime")
    monkeypatch.setattr(evals, "research_mcp_available", lambda cfg=None: True)
    monkeypatch.setattr(evals, "ResearchMCP", lambda n=3: StartableFake())
    monkeypatch.setattr(evals, "swarm_already_running", lambda c: False)
    econf = evals.expand_configs(__import__("yaml").safe_load(
        (evals.REPO / "evals" / "configs.yaml").read_text(encoding="utf-8")))
    assert len(econf["groups"]["strategy-study"]) == 3 * 8 + 2
    names = "screen-Qwen3.5-9B-direct,screen-Qwen3.5-9B-self_ask,screen-Qwen3.5-9B-native"
    args = SimpleNamespace(set="evals/research_v3.yaml", configs=names,
                           questions="lz-2026,pah-pathway-2026,fire-amoeba-2026", repeats=1, reuse_evidence=None,
                           regrade=None, resume=None, no_judge=False, no_open=True)
    out = await evals.run(args)
    results = [json.loads(l) for l in (out / "results.jsonl").read_text(encoding="utf-8").splitlines()]
    assert len(results) == 9 and all(not r["error"] for r in results), [r["error"] for r in results]
    assert all(r["stats"]["mode"] == "screen" for r in results)
    assert all("Qwen3.5-9B says" in r["answer"] and "When was the Eiffel Tower built?" in r["answer"] for r in results)
    native = [w for r in results if r["config"].endswith("native") for w in r["workers"]]
    assert native and all(w["strategy"] == "native" and w["thought_chars"] > 20 for w in native)
    direct = [w for r in results if r["config"].endswith("direct") for w in r["workers"]]
    assert all(w["strategy"] is None and w["support_rate"] is not None for w in direct)
    md = (out / "report.md").read_text(encoding="utf-8")
    assert "Strategy screen" in md and "Built-in thinking" in md and "Self-ask" in md and "Δ vs direct" in md


def test_keep_reasoning_strips_budget_flag(cfg, cards, mock_pool_cls):
    p = mock_pool_cls(cfg, cards)
    assert "--reasoning-budget" in p._extra_for(cards["Qwen3.5-9B"])
    p.keep_reasoning = ["gpt-oss", "qwen3.5-9b"]
    assert "--reasoning-budget" not in p._extra_for(cards["Qwen3.5-9B"])
    assert "--reasoning-budget" in p._extra_for(cards["Qwen3.5-4B"])
    # the RAM prompt cache is off (it filled 16 GB of RAM during the FRAMES run)
    args = p._extra_for(cards["Qwen3.5-4B"])
    assert args[args.index("--cache-ram") + 1] == "0"


def test_paired_ci():
    a = {"q1": 0.9, "q2": 0.8, "q3": 0.7, "q4": 0.9}
    b = {"q1": 0.5, "q2": 0.6, "q3": 0.5, "q4": 0.4}
    mean, lo, hi = evals.paired_ci(a, b)
    assert abs(mean - 0.325) < 1e-9 and 0 < lo <= mean <= hi
    assert evals.paired_ci({"q1": 1}, {"q1": 0}) is None


async def test_benchmark_set_budget_and_freeze(cfg, cards, mock_pool_cls, tmp_path, monkeypatch):
    """A reference-answer benchmark set, blocked answer-key sites, a normalized budget and a frozen manifest."""
    import yaml
    monkeypatch.setattr(evals, "load_config", lambda: cfg)
    monkeypatch.setattr(evals, "scan_models", lambda: cards)
    monkeypatch.setattr(evals, "ModelPool", mock_pool_cls)
    monkeypatch.setattr(evals, "RUNTIME", tmp_path / "runtime")
    monkeypatch.setattr(evals, "research_mcp_available", lambda cfg=None: True)
    monkeypatch.setattr(evals, "ResearchMCP", lambda n=3: StartableFake())
    monkeypatch.setattr(evals, "swarm_already_running", lambda c: False)
    monkeypatch.setattr(evals, "FROZEN_DIR", tmp_path / "frozen")
    bench = tmp_path / "bench.yaml"
    bench.write_text(yaml.safe_dump({"meta": {"benchmark": "TEST", "grading": "exact",
                                              "block_domains": ["huggingface.co"]},
                                     "questions": [{"id": "b1", "question": "When was the Eiffel Tower completed?", "answer": "1889"},
                                                   {"id": "b2", "question": "Who designed the tower?", "answer": "Gustave Eiffel"}]}))
    econf = evals.expand_configs(yaml.safe_load((evals.REPO / "evals" / "configs.yaml").read_text(encoding="utf-8")))
    evals.freeze("t1", ["coordinator-only", "swarm-t1"], cfg, econf)
    try:
        evals.freeze("t1", ["coordinator-only"], cfg, econf)
        raise AssertionError("a freeze must never be overwritten")
    except SystemExit:
        pass
    args = SimpleNamespace(set=str(bench), configs="coordinator-only,swarm-t1", questions=None, repeats=1,
                           reuse_evidence=None, regrade=None, resume=None, no_judge=False, no_open=True, live=True,
                           budget_tokens=3000, budget_seconds=None, frozen="t1")
    out = await evals.run(args)
    results = [json.loads(l) for l in (out / "results.jsonl").read_text(encoding="utf-8").splitlines()]
    meta = json.loads((out / "meta.json").read_text(encoding="utf-8"))
    assert meta["frozen"]["name"] == "t1" and meta["budget"]["max_output_tokens"] == 3000
    assert meta["block_domains"] == ["huggingface.co"] and meta["grading"] == "exact"
    assert len(results) == 4 and all(not r["error"] for r in results)
    b1 = [r for r in results if r["question_id"] == "b1"]
    assert all(r["grade"]["reference"] == "1889" and r["grade"]["score"] == 1.0 and r["grade"]["exact_match"] for r in b1)
    b2 = [r for r in results if r["question_id"] == "b2"]
    assert all(r["grade"]["score"] == 0.0 for r in b2)  # the mock never names Eiffel as designer
    assert all(r["stats"]["budget"]["max_output_tokens"] == 3000 and r["stats"]["budget"]["used"] <= 3000 for r in results)
    assert "Benchmark accuracy" in (out / "report.md").read_text(encoding="utf-8")

    # a changed configuration is refused
    cfg["coordinator"]["ctx_per_slot"] = 1234
    args2 = SimpleNamespace(**{**vars(args), "frozen": "t1"})
    try:
        await evals.run(args2)
        raise AssertionError("changed config ran despite the frozen manifest")
    except SystemExit as e:
        assert "changed since the freeze" in str(e) and "coordinator-only" in str(e)


def test_answer_matching_and_blocking():
    from swarm import benchmarks
    from swarm.orchestrator import _blocked
    assert benchmarks.answers_match("1,234", "1234") and benchmarks.answers_match("$12", "12")
    assert benchmarks.answers_match("The Beatles.", "beatles") and not benchmarks.answers_match("Beatles", "Stones")
    assert benchmarks.answers_match("a, b", "A; B") and not benchmarks.answers_match("a", "a, b")
    assert benchmarks.gold_in_text("It was Jane Ballou.", "Jane Ballou") and not benchmarks.gold_in_text("in 2023", "3")
    assert _blocked("huggingface.co", ["huggingface.co"]) and _blocked("raw.githubusercontent.com", ["githubusercontent.com"])
    assert not _blocked("nothuggingface.co", ["huggingface.co"]) and not _blocked("x.org", None)
    qs = benchmarks.frames_from_tsv("\tPrompt\tAnswer\treasoning_types\n0\tQ one?\tA1\tNumerical\n1\tQ two?\tA2\tTemporal\n", n=5)
    assert [q["answer"] for q in qs] == ["A1", "A2"] and qs[0]["id"] == "frames-0"
    gq = benchmarks.gaia_from_jsonl('{"task_id": "abcdef123", "Question": "Q?", "Level": 1, "Final answer": "42", "file_name": ""}\n'
                                    '{"task_id": "x2", "Question": "Q2?", "Level": 2, "Final answer": "7", "file_name": "a.png"}\n'
                                    '{"task_id": "x3", "Question": "Q3?", "Level": 3, "Final answer": "9", "file_name": ""}')
    assert [q["answer"] for q in gq] == ["42"]


async def test_budget_caps_calls(monkeypatch):
    from swarm import llm
    calls = []

    async def fake(base_url, messages, *, max_tokens, **kw):
        calls.append(max_tokens)
        return llm.ChatResult(text="ok", completion_tokens=max_tokens)
    monkeypatch.setattr(llm, "_chat", fake)
    llm.start_usage()
    llm.start_budget(max_output_tokens=2000, reserve_tokens=900)
    await llm.chat("u", [], max_tokens=800)           # fits: 2000 - 900 reserve = 1100 left
    await llm.chat("u", [], max_tokens=800)           # only 300 left before the reserve
    try:
        await llm.chat("u", [], max_tokens=800)       # nothing left outside the reserve
        raise AssertionError("should be over budget")
    except llm.BudgetExhausted:
        pass
    await llm.chat("u", [], max_tokens=900, final=True)  # the final answer gets the reserve
    assert calls == [800, 300, 900]
    snap = llm.budget_snapshot()
    assert snap["used"] == 2000 and snap["skipped_calls"] == 1 and snap["capped_calls"] == 1
    llm.start_budget(None, None)


async def test_second_judge_and_model_servers(cfg, cards, mock_pool_cls, tmp_path, monkeypatch):
    """--judge2 grades every answer again into grade2; Bonsai gets its own llama-server build."""
    monkeypatch.setattr(evals, "load_config", lambda: cfg)
    monkeypatch.setattr(evals, "scan_models", lambda: cards)
    monkeypatch.setattr(evals, "ModelPool", mock_pool_cls)
    monkeypatch.setattr(evals, "RUNTIME", tmp_path / "runtime")
    monkeypatch.setattr(evals, "research_mcp_available", lambda cfg=None: True)
    monkeypatch.setattr(evals, "ResearchMCP", lambda n=3: StartableFake())
    monkeypatch.setattr(evals, "swarm_already_running", lambda c: False)
    args = SimpleNamespace(set="evals/research_v3.yaml", configs="coordinator-only",
                           questions="lz-2026,pah-pathway-2026", repeats=1, reuse_evidence=None,
                           regrade=None, resume=None, no_judge=False, no_open=True, judge2=True)
    out = await evals.run(args)
    results = [json.loads(l) for l in (out / "results.jsonl").read_text(encoding="utf-8").splitlines()]
    assert all(r["grade"]["judge"] == "Ministral-3-14B-Instruct" and r["grade2"]["judge"] == "gpt-oss-20b"
               and r["grade2"]["score"] is not None for r in results)
    assert json.loads((out / "meta.json").read_text(encoding="utf-8"))["judge2"] == "gpt-oss-20b"
    assert "second judge" in (out / "report.md").read_text(encoding="utf-8")

    from swarm import pool as poolmod
    p = poolmod.ModelPool(cfg, cards)
    assert p._exe_for(cards["Bonsai-2-27B"]).as_posix().endswith("Bin/llama-prism/llama-server.exe")
    assert p._exe_for(cards["Qwen3.5-4B"]) == p.exe
    assert cards["Bonsai-2-27B"].lineage == "Qwen"


async def test_verifier_bench(cfg, cards, mock_pool_cls, tmp_path, monkeypatch):
    from swarm import verifier_bench as vb
    src = tmp_path / "ev"
    (src / "traces").mkdir(parents=True)
    ev_ = [{"id": "E1", "title": "Tower", "url": "https://a", "text": "The tower was completed in 1889.", "pos": 0, "score": 1.0}]
    wr = [{"model": "M", "base_model": "M", "claims": [{"claim": "It was completed in 1889.", "evidence": ["E1"]},
                                                        {"claim": "It is made of cheese.", "evidence": ["E1"]}]}]
    (src / "traces" / "t1.json").write_text(json.dumps({"question": "Q?", "evidence": ev_, "worker_results": wr}))
    monkeypatch.setattr(vb, "load_config", lambda: cfg)
    monkeypatch.setattr(vb, "scan_models", lambda: cards)
    monkeypatch.setattr(vb, "ModelPool", mock_pool_cls)
    monkeypatch.setattr(vb, "RUNTIME", tmp_path / "runtime")
    args = SimpleNamespace(source=str(src), n=10, verifiers=["Qwen3.5-4B", "Granite-Guardian-4.1-8B", "Not-A-Model"],
                           refs=["Ministral-3-14B-Instruct", "gpt-oss-20b"])
    out = await vb.run(args)
    md = (out / "report.md").read_text(encoding="utf-8")
    assert "Granite-Guardian-4.1-8B" in md and "Qwen3.5-4B" in md and "2 real worker claims" in md
    answers = json.loads((out / "answers.json").read_text(encoding="utf-8"))
    assert sorted(answers["Granite-Guardian-4.1-8B"]) == ["supported", "unsupported"]
    assert all(answers["Ministral-3-14B-Instruct"])      # answered through the plain JSON grammar


async def test_preflight_skips_configs_whose_model_fails(cfg, cards, mock_pool_cls, tmp_path, monkeypatch):
    from swarm import preflight
    monkeypatch.setattr(evals, "load_config", lambda: cfg)
    monkeypatch.setattr(evals, "scan_models", lambda: cards)
    monkeypatch.setattr(evals, "ModelPool", mock_pool_cls)
    monkeypatch.setattr(evals, "RUNTIME", tmp_path / "runtime")
    monkeypatch.setattr(evals, "research_mcp_available", lambda cfg=None: True)
    monkeypatch.setattr(evals, "ResearchMCP", lambda n=3: StartableFake())
    monkeypatch.setattr(evals, "swarm_already_running", lambda c: False)
    econf = evals.expand_configs(evals.yaml.safe_load((evals.REPO / "evals" / "configs.yaml").read_text(encoding="utf-8")))
    t1 = evals._merge(evals.copy.deepcopy(cfg), econf["configs"]["swarm-t1"]["overrides"])
    worker = [m for m in preflight.models_for(t1, cards) if m not in (cfg["coordinator"]["model"], cfg["verifier"]["model"])][0]
    monkeypatch.setenv("MOCK_LLAMA_FAIL", worker)
    args = SimpleNamespace(set="evals/research_v1.yaml", configs="coordinator-only,swarm-t1",
                           questions="lz-2026", repeats=1, reuse_evidence=None,
                           regrade=None, resume=None, no_judge=True, no_open=True)
    out = await evals.run(args)
    rs = [json.loads(l) for l in (out / "results.jsonl").read_text(encoding="utf-8").splitlines()]
    assert {r["config"] for r in rs} == {"coordinator-only"}          # swarm-t1 skipped, nothing wasted
    assert worker in json.loads((out / "meta.json").read_text(encoding="utf-8"))["preflight_failed"]


async def test_grade_attempts_grades_every_attempt_and_reports_oracle(tmp_path, monkeypatch):
    """Multi-attempt runs: every attempt gets its own grade (the chosen one reuses the run's grade), and
    the report shows one-attempt accuracy, the vote, the oracle and the oracle-by-N curve."""
    import json as _json
    from swarm import evals

    q = {"id": "q1", "question": "Capital of France?", "answer": "Paris", "grading": "judge"}
    key = evals.rubric_key(q)
    (tmp_path / "traces").mkdir()
    (tmp_path / "traces" / "t1.json").write_text(_json.dumps({"attempts": [
        {"answer": "It is Lyon.", "stats": {"total_seconds": 10, "manager": {"trust_final_ready": False}}, "config": {"temperature": 0.2}},
        {"answer": "It is Paris.", "stats": {"total_seconds": 12, "manager": {"trust_final_ready": True}}, "config": {"temperature": 0.7}},
        {"answer": "Paris, the capital.", "stats": {"total_seconds": 11}, "config": {"temperature": 0.7}}]}))
    r = {"config": "mgr-x", "question_id": "q1", "answer": "It is Paris.", "trace": "traces/t1.json",
         "grade": {"judge": "J", "rubric": key, "score": 1.0, "verdict": "correct", "extracted": "Paris"}}
    judged = []

    async def fake_loop(recs, questions, pool, jcfg, rec, model, save=None, k="grade"):
        for p in recs:
            judged.append(p["answer"])
            ok = "Paris" in p["answer"]
            p[k] = {"judge": model, "rubric": key, "score": 1.0 if ok else 0.0,
                    "verdict": "correct" if ok else "incorrect", "extracted": "Paris" if ok else "Lyon"}
        if save:
            save()

    class Pool:
        cards = {"J": object()}

        async def unload_all(self):
            pass

    class Rec:
        def say(self, m):
            pass

    monkeypatch.setattr(evals, "_judge_loop", fake_loop)
    n = await evals.grade_attempts(tmp_path, [r], {"q1": q}, Pool(), {"model": "J"}, Rec())
    assert n == 2 and sorted(judged) == ["It is Lyon.", "Paris, the capital."]   # the chosen one was reused
    assert [g["score"] for g in r["attempt_grades"]] == [0.0, 1.0, 1.0] and r["attempt_grades"][1].get("copied")
    assert [i["trust_ready"] for i in r["attempt_info"]] == [False, True, None]
    assert await evals.grade_attempts(tmp_path, [r], {"q1": q}, Pool(), {"model": "J"}, Rec()) == 0  # resumes
    md, page = evals.attempts_section([r], ["mgr-x"])
    text = "\n".join(md)
    assert "| mgr-x | 1 | 3 | 67% | 100% | 100% | 100% | 1/1 |" in text
    assert "1: 67%, 2: 100%, 3: 100%" in text and "Oracle" in page
