import asyncio
import json

import pytest

from swarm_forecast import gpu_lock, prompts
from swarm_forecast.adapter import SwarmSession, normalize_forecast, parse_probability
from swarm_forecast.questions import blind_question, find_leaks, informed_question
from swarm_forecast.runner import bets as betmod
from swarm_forecast.runner import cycle as cyc
from swarm_forecast.runner import select as selmod
from swarm_forecast.store import RecordLog


def mk(i, yes_ask, no_ask=None):
    no_ask = (1 - yes_ask + 0.01) if no_ask is None else no_ask
    return {"market_id": f"m{i}", "source": "fake", "question": f"Will event {i} happen?",
            "resolution_rule": f"Resolves YES if event {i} happens before the end date.",
            "end_date": "2026-11-20T00:00:00Z", "yes_ask": yes_ask, "no_ask": no_ask,
            "last_price": yes_ask, "spread": 0.02, "fetched_at": "2026-10-12T00:00:00+00:00"}


class FakeHandle:
    stamp = {"swarm_commit": "abc", "swarm_tag": "forecast-base-0"}

    def __init__(self, calls):
        self.calls = calls
        self.swarm = self
        self.closed = False

    async def run(self, text, emit, force_research=False, save_dir=None):
        self.calls.append(text)
        return {"final": {"answer": "Evidence is mixed."}, "manager": {"notes": [{"fact": "a fact", "status": "supported"}]},
                "stats": {"total_seconds": 1.0}}

    async def close(self):
        self.closed = True


def make_session(table, calls, tmp_path, fail_after=None):
    """table: market_id -> probability the fake forecaster reports."""
    counter = {"n": 0}

    async def factory(overrides):
        return FakeHandle(calls)

    async def extractor(handle, question, mode, answer, notes):
        counter["n"] += 1
        if fail_after is not None and counter["n"] > fail_after:
            raise asyncio.CancelledError()
        p = table.get(question["market_id"], 0.5)
        return {"probability": p, "reasons": [f"reason for {question['market_id']}"], "key_uncertainty": "x",
                "market_may_be_missing": "y" if mode == "informed" else ""}

    return SwarmSession({}, factory=factory, extractor=extractor, save_dir=tmp_path / "tr")


def test_blind_question_has_no_price_and_informed_has_state():
    m = mk(1, 0.3)
    b = blind_question(m, "2026-10-12")
    assert not find_leaks(b) and "yes_ask" not in json.dumps(b)
    i = informed_question(m, "2026-10-12")
    assert i["market_state"]["yes_ask"] == 0.3
    assert find_leaks({"x": {"market_state": 1}})
    assert "30 cents" not in prompts.research_question(b, "blind")
    assert "30 cents" in prompts.research_question(i, "informed")


def test_session_refuses_leaky_blind_and_stateless_informed(tmp_path):
    s = make_session({}, [], tmp_path)
    leaky = {**blind_question(mk(1, 0.3), "2026-10-12"), "prices": [0.3]}
    with pytest.raises(ValueError):
        asyncio.run(s.forecast(leaky, "blind"))
    with pytest.raises(ValueError):
        asyncio.run(s.forecast(blind_question(mk(1, 0.3), "2026-10-12"), "informed"))


def test_normalize_and_parse():
    p, parts = normalize_forecast({"probability": 35, "reasons": ["a", "b"], "key_uncertainty": "k"}, "")
    assert p == 0.35 and parts["reasons"] == ["a", "b"]
    p, _ = normalize_forecast({}, "I estimate the probability at 72%.")
    assert p == 0.72
    p, _ = normalize_forecast({"probability": "abc"}, "no number")
    assert p is None
    assert normalize_forecast({"probability": 1.0}, "")[0] == 0.99
    assert parse_probability("about 5% chance") == 0.05


def test_bets_math_and_luck():
    deep = [{"market_id": "a", "confirmed": True, "side": "yes", "side_ask": 0.30, "side_probability": 0.55},
            {"market_id": "b", "confirmed": True, "side": "no", "side_ask": 0.40, "side_probability": 0.80},
            {"market_id": "c", "confirmed": False, "side": "yes", "side_ask": 0.20, "side_probability": 0.90},
            {"market_id": "d", "confirmed": True, "side": "yes", "side_ask": 0.50, "side_probability": 0.55}]
    b = betmod.decide_bets(deep, margin=0.10)
    assert [x["market_id"] for x in b] == ["a", "b"]  # c not confirmed, d edge too small
    s = betmod.settle(b, {"a": "yes", "b": "yes"})
    assert s[0]["won"] and abs(s[0]["pnl"] - (1 / 0.30 - 1)) < 1e-9
    assert not s[1]["won"] and s[1]["pnl"] == -1.0
    assert betmod.settle(b, {"a": "void"}) == []
    assert abs(betmod.prob_at_least(120, [0.97] * 120) - 0.97 ** 120) < 1e-12
    assert abs(betmod.prob_at_least(1, [0.5, 0.5]) - 0.75) < 1e-12
    summ = betmod.summarize(s)
    assert summ["bets"] == 2 and summ["hits"] == 1 and summ["under_50c"]["bets"] == 2


def test_gap_picks_and_reasons():
    markets = {f"m{i}": mk(i, 0.5) for i in range(5)}
    markets["m0"] = mk(0, 0.10)   # swarm says 0.40 -> yes gap 0.30
    markets["m1"] = mk(1, 0.90, no_ask=0.11)   # swarm says 0.40 -> no gap: 0.60-0.11 = 0.49
    blind = [{"market_id": "m0", "probability": 0.40, "reasons": ["r0"]}, {"market_id": "m1", "probability": 0.40, "reasons": ["r1"]},
             {"market_id": "m2", "probability": 0.52, "reasons": []}, {"market_id": "m3", "probability": None, "error": "x"}]
    picks = selmod.choose_by_gap(blind, markets, x=5, min_gap=0.10)
    assert [p["market_id"] for p in picks] == ["m1", "m0"]
    assert picks[0]["side"] == "no" and "r1" in picks[0]["reason"] and picks[0]["rank"] == 1


def test_cycle_gap_mode_end_to_end_resume_and_prereg(tmp_path):
    pool = [mk(i, 0.5) for i in range(10)]
    pool[2] = mk(2, 0.10)
    pool[7] = mk(7, 0.85, no_ask=0.16)
    quick_table = {"m2": 0.45, "m7": 0.40}      # gaps: m2 yes +0.35, m7 no +0.44
    deep_table = {"m2": 0.40, "m7": 0.45}       # deep still sees the edge
    qcalls, dcalls = [], []
    lock = str(tmp_path / "lock.json")
    rules = {"x": 3, "min_gap": 0.10, "pool_limit": 10}
    out = tmp_path / "cycle1"
    res = asyncio.run(cyc.run_cycle(out, pool, rules, make_session(quick_table, qcalls, tmp_path),
                                    make_session(deep_table, dcalls, tmp_path), lock_path=lock, today="2026-10-12"))
    assert res["status"] == "ok" and res["picks"] == 2
    assert len(qcalls) == 10 and len(dcalls) == 2
    picks = json.loads((out / "picks.json").read_text())
    assert [p["market_id"] for p in picks["picks"]] == ["m7", "m2"] and all(p["reason"] for p in picks["picks"])
    assert len(picks["baselines"]["random"]) == 2
    deep = RecordLog(out / "deep.jsonl").read()
    assert {d["market_id"] for d in deep} == {"m2", "m7"} and all(d["confirmed"] for d in deep)
    bets = json.loads((out / "bets.json").read_text())
    assert {b["market_id"]: b["side"] for b in bets} == {"m2": "yes", "m7": "no"}
    assert gpu_lock.status(lock) is None                              # lock released
    # rerun: nothing is forecast again
    q2, d2 = [], []
    asyncio.run(cyc.run_cycle(out, pool, rules, make_session(quick_table, q2, tmp_path),
                              make_session(deep_table, d2, tmp_path), lock_path=lock, today="2026-10-12"))
    assert q2 == [] and d2 == []
    # changed rules on the same cycle directory are refused
    with pytest.raises(RuntimeError):
        asyncio.run(cyc.run_cycle(out, pool, {**rules, "min_gap": 0.2}, make_session({}, [], tmp_path),
                                  make_session({}, [], tmp_path), lock_path=lock))
    assert gpu_lock.status(lock) is None
    # scoring
    outcomes = {m["market_id"]: ("yes" if i % 2 == 0 else "no") for i, m in enumerate(pool)}
    rep = cyc.score_cycle(out, outcomes, {m["market_id"]: m for m in pool})
    assert rep["blind"]["n"] == 10 and rep["bets"]["bets"] == 2
    assert rep["selection"]["picked"]["n"] == 2 and "p_hits_at_least_this_by_luck" in rep["bets"]


def test_cycle_killed_mid_deep_resumes_without_redoing(tmp_path):
    pool = [mk(i, 0.1) for i in range(6)]
    quick_table = {f"m{i}": 0.5 for i in range(6)}
    deep_table = {f"m{i}": 0.5 for i in range(6)}
    rules = {"x": 5, "min_gap": 0.10, "pool_limit": 6}
    out = tmp_path / "c"
    lock = str(tmp_path / "lock.json")
    d1 = []
    with pytest.raises(asyncio.CancelledError):
        asyncio.run(cyc.run_cycle(out, pool, rules, make_session(quick_table, [], tmp_path),
                                  make_session(deep_table, d1, tmp_path, fail_after=2), lock_path=lock))
    assert gpu_lock.status(lock) is None and len(RecordLog(out / "deep.jsonl").read()) == 2
    d2 = []
    asyncio.run(cyc.run_cycle(out, pool, rules, make_session(quick_table, [], tmp_path),
                              make_session(deep_table, d2, tmp_path), lock_path=lock))
    assert len(RecordLog(out / "deep.jsonl").read()) == 5 and len(d2) == 3


def test_cycle_screen_mode_and_gpu_busy(tmp_path):
    pool = [mk(i, 0.5) for i in range(7)]
    lock = str(tmp_path / "lock.json")
    assert gpu_lock.acquire("someone-else", "study", path=lock)
    busy = asyncio.run(cyc.run_cycle(tmp_path / "b", pool, {"x": 2}, make_session({}, [], tmp_path),
                                     make_session({}, [], tmp_path), lock_path=lock))
    assert busy["status"] == "gpu_busy"
    gpu_lock.release("someone-else", lock)

    async def llm_json(system, user, schema):
        ids = [l.split(": ")[1] for l in user.splitlines() if l.startswith("id: ")]
        return {"items": [{"id": i, "answerable": 5 if i in ("m3", "m5") else 2, "tag": "t", "reason": f"why {i}"} for i in ids]}

    qc, dc = [], []
    out = tmp_path / "s"
    res = asyncio.run(cyc.run_cycle(out, pool, {"mode": "screen", "x": 2}, make_session({"m3": 0.3, "m5": 0.6}, qc, tmp_path),
                                    make_session({"m3": 0.3, "m5": 0.6}, dc, tmp_path), lock_path=lock, llm_json=llm_json))
    picks = json.loads((out / "picks.json").read_text())
    assert sorted(p["market_id"] for p in picks["picks"]) == ["m3", "m5"] and all(p["reason"].startswith("why") for p in picks["picks"])
    assert len(qc) == 2 and len(dc) == 2          # blind only on the chosen, deep only on the chosen
    rep = cyc.score_cycle(out, {"m3": "yes", "m5": "no"}, {m["market_id"]: m for m in pool})
    assert "answerability_vs_brier" in rep
