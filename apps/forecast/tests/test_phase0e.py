import json
from datetime import datetime, timezone, timedelta
from swarm_forecast.sample import enrich, sample_markets
from swarm_forecast.questions import blind_question, find_leaks

def market(i, category="other", days=14, price=.5, event=None):
    return enrich({"market_id": str(i), "source":"kalshi", "question":f"Will event {i} happen?", "resolution_rule":"Official result decides.", "end_date":(datetime.now(timezone.utc)+timedelta(days=days)).isoformat(), "last_price":price, "category":category, "event_ticker":event or f"E{i}"})

def test_cluster_and_category_are_auditable():
    m = enrich({"market_id":"x", "question":"Will Bitcoin reach $100,000?", "end_date":"2026-12-31T00:00:00Z", "event_ticker":"e"})
    assert m["theme"] == "asset-threshold" and m["category_source"] == "keyword" and m["cluster_id"].startswith("e|")

def test_sampler_limits_cluster_theme_and_sports():
    rows = [market(i, "Sports" if i < 30 else "other", event="pair" if i < 8 else str(i)) for i in range(100)]
    for i, row in enumerate(rows):
        row["question"] = f"Will event {i} happen? {['by December 31', 'reach $100', 'election', 'AI'][i % 4]}"
        rows[i] = enrich(row)
    chosen, report = sample_markets(rows, n=20, seed=1)
    assert len(chosen) <= 20 and max(report["category_counts"].get("Sports", 0), 0) <= 2
    assert max(report["clusters"], key=lambda x:x[1])[1] <= 5

def test_blind_file_has_no_market_state():
    q = blind_question({"market_id":"x", "source":"kalshi", "question":"q", "resolution_rule":"r", "end_date":"d", "last_price":.5}, "today")
    assert find_leaks(q) == [] and "market_state" not in q
