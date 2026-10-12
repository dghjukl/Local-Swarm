"""Cluster, classify, and stratified-sample a frozen market batch."""
from __future__ import annotations
import json, random, re
from collections import Counter
from datetime import datetime
from pathlib import Path

def theme_for(question):
    q = question.lower()
    if "house seat" in q or "senate" in q or "election" in q: return "election"
    if "by december 31" in q or "before 2027" in q: return "deadline"
    if re.search(r"\$[0-9]|price|fdv|market cap|bitcoin|ethereum|solana", q): return "asset-threshold"
    if any(x in q for x in ("war", "invade", "capture", "ceasefire", "president")): return "geopolitics"
    if any(x in q for x in ("ai", "openai", "anthropic", "technology", "software")): return "tech"
    if any(x in q for x in ("game of the year", "movie", "music", "award")): return "entertainment"
    if any(x in q for x in ("nfl", "nba", "tennis", "soccer", "fight", "ufc", "sports")): return "sports"
    return "other"

def category_for(market):
    raw = market.get("raw") or {}
    api = market.get("category") or raw.get("category")
    if api: return str(api), "api"
    theme = theme_for(market.get("question", ""))
    return {"election":"elections", "geopolitics":"geopolitics/war", "asset-threshold":"crypto", "tech":"tech/AI", "entertainment":"entertainment", "sports":"sports", "deadline":"politics"}.get(theme, "other"), "keyword"

def enrich(market):
    m = dict(market); category, source = category_for(m); theme = theme_for(m.get("question", ""))
    event = m.get("event_ticker") or (m.get("raw") or {}).get("event_ticker") or m.get("market_id")
    end = str(m.get("end_date", ""))[:10]
    m.update({"category": category, "category_source": source, "theme": theme, "cluster_id": f"{event}|{theme}|{end}"})
    return m

def load_batch(path):
    return [enrich(json.loads(line)["market"] if "market" in json.loads(line) else json.loads(line)) for line in Path(path).read_text(encoding="utf-8").splitlines() if line.strip()]

def _band(m):
    p = float(m.get("last_price") or 0)
    return "tail-low" if p < .15 else "low" if p < .35 else "middle" if p < .65 else "high" if p < .85 else "tail-high"

def sample_markets(markets, n=60, seed=0, max_per_cluster=5, max_theme_share=.15, sports_share=.10):
    rng = random.Random(seed); pool = list(markets); rng.shuffle(pool)
    max_theme = max(1, int(n * max_theme_share)); max_sports = int(n * sports_share)
    chosen, clusters, themes, bands, dates = [], Counter(), Counter(), Counter(), Counter(); chosen_ids = set()
    def eligible(m):
        if clusters[m["cluster_id"]] >= max_per_cluster or themes[m["theme"]] >= max_theme: return False
        if m.get("category", "").lower() == "sports" and sum(x.get("category", "").lower() == "sports" for x in chosen) >= max_sports: return False
        return True
    # Reserve at least a quarter for the 7-21 day band where available.
    now = datetime.now().astimezone()
    def days(m): return (datetime.fromisoformat(m["end_date"].replace("Z", "+00:00")) - now).total_seconds()/86400
    def add(m):
        if m["market_id"] in chosen_ids or not eligible(m): return False
        chosen.append(m); chosen_ids.add(m["market_id"]); clusters[m["cluster_id"]]+=1; themes[m["theme"]]+=1; return True
    early = [m for m in pool if 7 <= days(m) <= 21]
    for m in early:
        if len(chosen) >= max(0, n // 4) or len(chosen) >= n: break
        add(m)
    for wanted in ("tail-low", "tail-high"):
        target = max(1, int(n * .15))
        for m in (x for x in pool if _band(x) == wanted):
            if sum(_band(x) == wanted for x in chosen) >= target or len(chosen) >= n: break
            add(m)
    for m in pool:
        if len(chosen) >= n: break
        add(m)
    date_bands = Counter()
    for m in chosen:
        bands[_band(m)] += 1; dates[str(m.get("end_date", ""))[:10]] += 1
        d = days(m); date_bands["7-21" if d <= 21 else "22-45" if d <= 45 else "46-90"] += 1
    report = {"requested": n, "selected": len(chosen), "seed": seed, "clusters": clusters.most_common(15), "themes": dict(themes), "price_bands": dict(bands), "date_bands": dict(date_bands), "resolve_dates": dict(dates), "category_counts": dict(Counter(m.get("category", "other") for m in chosen)), "constraints": {"max_cluster": max_per_cluster, "max_theme": max_theme, "max_sports": max_sports, "min_early": n // 4, "min_price_tail": int(n * .15)}}
    return chosen, report

def write_jsonl(path, markets):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text("".join(json.dumps(m, ensure_ascii=False) + "\n" for m in markets), encoding="utf-8")
