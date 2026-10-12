from __future__ import annotations
import math, random


def brier(forecasts):
    return sum((float(x["probability"]) - int(bool(x["outcome"]))) ** 2 for x in forecasts) / len(forecasts) if forecasts else None


def log_score(forecasts):
    if not forecasts: return None
    return sum(math.log(max(1e-12, min(1 - 1e-12, p if o else 1 - p))) for p, o in ((float(x["probability"]), bool(x["outcome"])) for x in forecasts)) / len(forecasts)


def calibration(forecasts, bins=10):
    out = []
    for i in range(bins):
        group = [x for x in forecasts if i / bins <= float(x["probability"]) < (i + 1) / bins or (i == bins - 1 and float(x["probability"]) == 1)]
        if group: out.append({"lower": i / bins, "upper": (i + 1) / bins, "count": len(group), "mean_probability": sum(float(x["probability"]) for x in group) / len(group), "hit_rate": sum(bool(x["outcome"]) for x in group) / len(group)})
    return out


def paper_bets(forecasts, margin=.10, fee=0, draws=10000, seed=0):
    bets = [x for x in forecasts if float(x["probability"]) - float(x["entry_price"]) >= margin]
    returns = [((1 - fee) / float(x["entry_price"]) - 1) if x["outcome"] else -1 for x in bets]
    rng = random.Random(seed); samples = [sum(rng.choice(returns) for _ in returns) / len(returns) if returns else 0 for _ in range(draws)]
    samples.sort(); roi = sum(returns) / len(returns) if returns else 0
    return {"bets": len(bets), "roi": roi, "hit_rate": sum(bool(x["outcome"]) for x in bets) / len(bets) if bets else None,
            "ci95": (samples[int(draws * .025)], samples[int(draws * .975)]) if returns else (None, None)}


def score(forecasts, outcomes=None):
    return {"count": len(forecasts), "brier": brier(forecasts), "log_score": log_score(forecasts), "calibration": calibration(forecasts), "paper_bets": paper_bets(forecasts)}
