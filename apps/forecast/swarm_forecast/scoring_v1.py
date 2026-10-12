"""Pre-registered, outcome-independent scoring for forecast cycles.

The functions here are deliberately pure apart from the optional public API
outcome puller.  Reports never silently discard a row: exclusions are counted.
"""
from __future__ import annotations

import hashlib
import json
import math
import random
import urllib.request
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path


def _mean(xs):
    return sum(xs) / len(xs) if xs else None


def _brier(rows):
    return _mean([(float(r["p"]) - int(r["y"])) ** 2 for r in rows])


def _log(rows):
    return _mean([math.log(max(1e-12, min(1 - 1e-12, r["p"] if r["y"] else 1 - r["p"]))) for r in rows])


def paired_bootstrap(rows, draws=2000, seed=0):
    """Return swarm-minus-market Brier/log differences and a seeded 95% CI."""
    if not rows:
        return {"n": 0, "brier_difference": None, "log_difference": None, "brier_ci95": [None, None], "log_ci95": [None, None]}
    diffs_b = [(r["p"] - r["y"]) ** 2 - (r["market"] - r["y"]) ** 2 for r in rows]
    diffs_l = [math.log(max(1e-12, min(1 - 1e-12, r["p"] if r["y"] else 1 - r["p"]))) - math.log(max(1e-12, min(1 - 1e-12, r["market"] if r["y"] else 1 - r["market"]))) for r in rows]
    rng = random.Random(seed)
    samples_b = sorted(_mean([rng.choice(diffs_b) for _ in diffs_b]) for _ in range(draws))
    rng = random.Random(seed)
    samples_l = sorted(_mean([rng.choice(diffs_l) for _ in diffs_l]) for _ in range(draws))
    def ci(s): return [s[int(draws * .025)], s[min(draws - 1, int(draws * .975))]]
    return {"n": len(rows), "brier_difference": _mean(diffs_b), "log_difference": _mean(diffs_l), "brier_ci95": ci(samples_b), "log_ci95": ci(samples_l), "bootstrap_draws": draws, "seed": seed}


def _horizon(end_date, as_of):
    try:
        end = datetime.fromisoformat(str(end_date).replace("Z", "+00:00"))
        start = datetime.fromisoformat(str(as_of).replace("Z", "+00:00"))
        days = (end - start).total_seconds() / 86400
    except (TypeError, ValueError):
        return "unknown"
    return "<=14d" if days <= 14 else "15-30d" if days <= 30 else "31+d"


def _contact_ids(audit_path):
    if not audit_path or not Path(audit_path).exists(): return set()
    data = json.loads(Path(audit_path).read_text(encoding="utf-8"))
    rows = data if isinstance(data, list) else data.get("rows", data.get("audit", []))
    return {str(r.get("market_id")) for r in rows if r.get("market_site_contact")}


def _group(rows, key):
    out = {}
    for name, group in _groups(rows, key).items():
        out[str(name)] = {"n": len(group), "brier": _brier(group), "log_score": _log(group)}
    return out


def _groups(rows, key):
    groups = defaultdict(list)
    for r in rows: groups[key(r)].append(r)
    return groups


def calibration(rows, bins=10):
    out = []
    for i in range(bins):
        group = [r for r in rows if i / bins <= r["p"] < (i + 1) / bins or (i == bins - 1 and r["p"] == 1)]
        if group:
            out.append({"lower": i / bins, "upper": (i + 1) / bins, "n": len(group), "mean_probability": _mean([r["p"] for r in group]), "hit_rate": _mean([r["y"] for r in group]), "reliable": len(group) >= 10})
    return out


def rows_from_cycle(cycle_dir, pool, outcomes):
    """Read a cycle as read-only normalized rows for the blind primary arm."""
    path = Path(cycle_dir) / "blind.jsonl"
    records = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()] if path.exists() else []
    markets = {str(m["market_id"]): m for m in pool}
    rows = []
    for r in records:
        mid = str(r.get("market_id")); m = markets.get(mid, {})
        status = "errored" if r.get("error") else "no_forecast" if r.get("no_forecast") or r.get("probability") is None else None
        outcome = outcomes.get(mid)
        if status is None and outcome in {"void", "ambiguous", "na", "unresolved", None}: status = outcome or "unresolved"
        yes = m.get("yes_ask"); no = m.get("no_ask")
        market = (float(yes) + (1 - float(no))) / 2 if yes is not None and no is not None else (float(yes) if yes is not None else None)
        rows.append({"id": mid, "p": r.get("probability"), "market": market, "y": 1 if outcome == "yes" else 0 if outcome == "no" else None, "status": status, "end_date": m.get("end_date"), "category": m.get("category", "unknown"), "cluster_id": m.get("cluster_id", "unknown"), "research_found": bool(r.get("research_summary") or r.get("evidence"))})
    return rows


def score_rows(rows, *, total=None, as_of=None, date_label="final", audit_path=None, draws=2000):
    """Score normalized rows. Each row has id,p,market,y and optional metadata."""
    total = len(rows) if total is None else total
    exclusions = Counter()
    scored = []
    for r in rows:
        status = r.get("status")
        if status in {"no_forecast", "inconsistent", "errored", "unresolved", "ambiguous", "na", "void"}:
            exclusions[status] += 1; continue
        if r.get("y") not in (0, 1): exclusions["unresolved"] += 1; continue
        if r.get("p") is None: exclusions["no_forecast"] += 1; continue
        if r.get("market") is None: exclusions["market_missing"] += 1; continue
        scored.append(r)
    base = [{"p": r["p"], "market": r["market"], "y": r["y"]} for r in scored]
    contact = _contact_ids(audit_path)
    strata = {"all": base, "no_market_contact": [x for x, r in zip(base, scored) if str(r.get("id")) not in contact], "market_contact": [x for x, r in zip(base, scored) if str(r.get("id")) in contact]}
    arm = {"swarm": {"n": len(base), "brier": _brier(base), "log_score": _log(base)}, "market": {"n": len(base), "brier": _brier([{"p": x["market"], "y": x["y"]} for x in base]), "log_score": _log([{"p": x["market"], "y": x["y"]} for x in base])}}
    for name, values in strata.items(): arm.setdefault("strata", {})[name] = paired_bootstrap(values, draws, 0)
    # Baselines are evaluated on the same scored questions.
    rate = _mean([r["y"] for r in scored])
    baselines = {"market": [r["market"] for r in scored], "constant_0.5": [0.5] * len(scored), "cycle_base_rate": [rate] * len(scored), "random": [random.Random(0).random() for _ in scored], "near_50": [0.5 + (0.01 if i % 2 else -0.01) for i in range(len(scored))], "buy_cheaper_side": [min(r["market"], 1 - r["market"]) for r in scored]}
    baseline_report = {name: {"n": len(scored), "brier": _mean([(p - r["y"]) ** 2 for p, r in zip(ps, scored)])} for name, ps in baselines.items()}
    horizon = _group(scored, lambda r: _horizon(r.get("end_date"), as_of) if as_of else "unknown")
    report = {"schema": "scoring-v1", "date": date_label, "resolved_count": len(scored), "total": total, "coverage": len(scored) / total if total else None, "exclusions": dict(exclusions), "arms": arm, "baselines": baseline_report, "calibration": calibration(base), "horizon": horizon, "category": _group(scored, lambda r: r.get("category", "unknown")), "cluster": _group(scored, lambda r: r.get("cluster_id", "unknown")), "answerability": _group(scored, lambda r: "evidence" if r.get("research_found") else "thin"), "early_score_warning": date_label != "final" and "Early scores over-represent short-horizon markets and are not comparable with the final score." or None}
    return report


def report_files(report, out_dir, *, cycle_dir=None, analysis_path=None):
    out = Path(out_dir); out.mkdir(parents=True, exist_ok=True)
    report = dict(report)
    report["analysis_sha256"] = hashlib.sha256(Path(analysis_path or __file__).read_bytes()).hexdigest()
    if cycle_dir:
        files = sorted(p for p in Path(cycle_dir).rglob("*") if p.is_file())
        h = hashlib.sha256()
        for p in files: h.update(str(p.relative_to(cycle_dir)).encode()); h.update(p.read_bytes())
        report["cycle_sha256"] = h.hexdigest()
    (out / "score_report.json").write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    lines = [f"# Score report ({report['date']})", "", f"Resolved: {report['resolved_count']} / {report['total']} (coverage {report['coverage']:.1%})", "", "## Exclusions", ""]
    lines += [f"- {k}: {v}" for k, v in sorted(report["exclusions"].items())] or ["- none"]
    lines += ["", "## Arms", "", "| arm | n | Brier | log score |", "|---|---:|---:|---:|"]
    lines += [f"| {k} | {v['n']} | {v['brier']} | {v['log_score']} |" for k, v in report["arms"].items() if isinstance(v, dict) and "brier" in v]
    if report.get("early_score_warning"): lines += ["", f"> WARNING: {report['early_score_warning']}"]
    lines += ["", f"Analysis SHA-256: `{report.get('analysis_sha256')}`", f"Cycle SHA-256: `{report.get('cycle_sha256', 'not supplied')}`", "", "This report uses the pre-registered scoring rules; any fabricated input must be labeled FAKE."]
    (out / "score_report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return report


def pull_outcomes(cycle_dir, markets, *, cache_name="outcomes_raw.json", opener=None):
    """Pull only each market's public resolution field; never asks the swarm."""
    out = Path(cycle_dir); out.mkdir(parents=True, exist_ok=True); cache = out / cache_name
    opener = opener or urllib.request.urlopen
    raw = json.loads(cache.read_text(encoding="utf-8")) if cache.exists() else {}
    for m in markets:
        mid, source = str(m["market_id"]), m.get("source")
        if mid in raw: continue
        if source == "polymarket": url = f"https://gamma-api.polymarket.com/markets/{mid}"
        elif source == "kalshi": url = f"https://external-api.kalshi.com/trade-api/v2/markets/{mid}"
        else: raw[mid] = {"status": "unsupported_source"}; continue
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Local-Swarm-forecast-outcomes/1"})
            with opener(req, timeout=20) as response: raw[mid] = json.loads(response.read().decode("utf-8"))
        except Exception as exc:
            raw[mid] = {"status": "errored", "error": str(exc)}
    cache.write_text(json.dumps(raw, indent=2, sort_keys=True), encoding="utf-8")
    outcomes = {}
    for mid, data in raw.items():
        value = data.get("outcome") or data.get("result") or data.get("resolution")
        value = str(value).lower() if value is not None else "unresolved"
        outcomes[mid] = value if value in {"yes", "no", "void", "ambiguous", "na", "unresolved"} else "ambiguous"
    return outcomes
