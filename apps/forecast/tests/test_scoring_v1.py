from swarm_forecast.scoring_v1 import paired_bootstrap, score_rows


def rows():
    return [
        {"id": "a", "p": .9, "market": .6, "y": 1, "end_date": "2026-10-20T00:00:00Z", "category": "science", "cluster_id": "c1", "research_found": True},
        {"id": "b", "p": .1, "market": .4, "y": 0, "end_date": "2026-11-20T00:00:00Z", "category": "economics", "cluster_id": "c2", "research_found": False},
        {"id": "c", "p": .5, "market": .5, "y": None, "status": "unresolved"},
        {"id": "d", "p": None, "market": .5, "y": 1, "status": "no_forecast"},
    ]


def test_paired_bootstrap_known_case_is_seeded():
    out = paired_bootstrap([{"p": .9, "market": .6, "y": 1}, {"p": .1, "market": .4, "y": 0}], draws=2000, seed=0)
    assert out["n"] == 2 and round(out["brier_difference"], 12) == -0.15
    assert out == paired_bootstrap([{"p": .9, "market": .6, "y": 1}, {"p": .1, "market": .4, "y": 0}], draws=2000, seed=0)


def test_exclusions_and_baselines_and_buckets_are_visible():
    out = score_rows(rows(), as_of="2026-10-12T00:00:00Z", date_label="7")
    assert out["resolved_count"] == 2 and out["exclusions"] == {"unresolved": 1, "no_forecast": 1}
    assert out["horizon"]["<=14d"]["n"] == 1 and out["horizon"]["31+d"]["n"] == 1
    assert "constant_0.5" in out["baselines"] and out["early_score_warning"]


def test_same_question_strata_are_explicit():
    out = score_rows(rows(), audit_path=None)
    assert out["arms"]["strata"]["all"]["n"] == 2
    assert out["arms"]["strata"]["no_market_contact"]["n"] == 2
