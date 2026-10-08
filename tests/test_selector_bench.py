"""Offline selectors: groups of matching short answers, source families, READY preference."""
import json

from swarm import selector_bench as S


def test_same_answer_and_families():
    assert S.same_answer("Jane Ballou", "jane ballou.")
    assert S.same_answer("About 28 times (9,140 / 326)", "28 times")
    assert not S.same_answer("28 times", "9 times")
    assert not S.same_answer("Harold Wilson", "Edward Heath")
    assert S.no_answer("Cannot determine; no data") and not S.no_answer("Paris")
    assert S.family("https://en.wikipedia.org/wiki/X") == S.family("https://www.wikiwand.com/en/X") == "wikipedia"
    assert S.family("https://www.britannica.com/a") == "britannica.com"


def _att(answer, *urls):
    return {"answer": answer, "sources": [{"url": u} for u in urls]}


def test_selectors_on_a_toy_run(tmp_path):
    # 2 wrong attempts quoting the same wikipedia page (and a mirror) vs 1 right attempt with 2 independent
    # sources, which is also the only READY one; a 4th attempt gives no answer
    atts = [_att("Lyon.", "https://en.wikipedia.org/wiki/A"), _att("Lyon.", "https://en.wikiwand.com/A"),
            _att("Paris.", "https://www.britannica.com/p", "https://www.gov.fr/p"),
            _att("Cannot determine.")]
    trace = {"attempts": atts, "votes": [{"n": 4, "short": ["Lyon", "Lyon", "Paris", "cannot determine"]}]}
    (tmp_path / "traces").mkdir()
    (tmp_path / "traces" / "q1.json").write_text(json.dumps(trace))
    r = {"config": "c", "question_id": "q1", "trace": "traces/q1.json",
         "attempt_grades": [{"score": 0.0}, {"score": 0.0}, {"score": 1.0}, {"score": 0.0}],
         "attempt_info": [{"trust_ready": False}, {"trust_ready": False}, {"trust_ready": True}, {"trust_ready": None}],
         "stats": {"attempts": {"chosen": 1, "same": True}}, "grade": {"score": 0.0}}
    (tmp_path / "results.jsonl").write_text(json.dumps(r) + "\n")
    rows = S.load(tmp_path, None)
    assert len(rows) == 1
    res = S.evaluate(rows)
    assert res["majority"] == 0.0 and res["coordinator"] == 0.0 and res["first"] == 0.0
    assert res["indep_sources"] == 1.0          # 2 source families beat wikipedia + its mirror
    assert res["ready_major"] == 1.0            # the only READY attempt
    assert res["ready_weighted"] == 0.0         # 2 Lyon (1 each) vs Paris (2): tie -> earliest -> Lyon
    assert res["grounded_major"] == 0.0
    assert res["oracle"] == 1.0
    assert res["coordinator_all_agree"] == 1 and res["code_all_agree"] == 0
    by_k = S.evaluate(rows, 2)
    assert by_k["oracle"] == 0.0 and "coordinator" not in by_k
    assert "Selector bake-off" in S.report(rows)
