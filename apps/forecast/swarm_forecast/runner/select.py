"""Stage 'select': which questions to spend deep research on, each with a saved reason."""
from __future__ import annotations

import random
import re
from typing import Awaitable, Callable

from swarm_forecast import prompts

LlmJson = Callable[[str, str, dict], Awaitable[dict]]


async def screen(pool: list[dict], llm_json: LlmJson, batch: int = 20) -> list[dict]:
    """Answerability screen from question text only (no prices): batches of ~20, one rating + reason each."""
    out: dict[str, dict] = {}
    for i in range(0, len(pool), batch):
        chunk = pool[i:i + batch]
        user = "\n\n".join(f"id: {m['market_id']}\nquestion: {m['question']}\nresolves by: {m.get('end_date', '')}\n"
                           f"rules: {(m.get('rules') or m.get('resolution_rule') or '')[:300]}" for m in chunk)
        try:
            d = await llm_json(prompts.SELECT_SYSTEM, user, prompts.SELECT_SCHEMA)
        except Exception as e:  # a failed batch gets neutral ratings, flagged
            d = {"items": [], "_error": type(e).__name__}
        for it in (d.get("items") or []):
            if isinstance(it, dict) and str(it.get("id")) in {str(m["market_id"]) for m in chunk}:
                out[str(it["id"])] = {"market_id": str(it["id"]), "answerable": max(1, min(5, int(it.get("answerable", 3) or 3))),
                                      "tag": str(it.get("tag", ""))[:30], "reason": str(it.get("reason", ""))[:240], "rated": True}
        for m in chunk:
            out.setdefault(str(m["market_id"]), {"market_id": str(m["market_id"]), "answerable": 3, "tag": "",
                                                 "reason": "no rating returned", "rated": False})
    return [out[str(m["market_id"])] for m in pool]


def choose_by_screen(screened: list[dict], x: int, seed: int = 0) -> list[dict]:
    rng = random.Random(seed)
    order = sorted(screened, key=lambda s: (-s["answerable"], rng.random()))
    return [{"market_id": s["market_id"], "basis": "answerability", "rank": i + 1, "score": s["answerable"],
             "reason": s["reason"]} for i, s in enumerate(order[:x])]


UNINFORMED_RE = re.compile(
    r"no (specific |direct )?(findings|evidence|information|data|polling)|zero information|"
    r"not (enough|sufficient) (evidence|information)|cannot determine|insufficient", re.I)


def is_uninformed(record: dict) -> bool:
    p = record.get("probability")
    if p is None or not 0.40 <= float(p) <= 0.60:
        return False
    text = " ".join([*(record.get("reasons") or []), record.get("research_summary", "")])
    return bool(UNINFORMED_RE.search(text))


def probability_distribution(records: list[dict]) -> dict:
    values = [float(r["probability"]) for r in records if r.get("probability") is not None]
    buckets = {}
    for p in values:
        lo = min(95, max(0, int(p * 20) * 5))
        key = f"{lo / 100:.2f}-{(lo + 5) / 100:.2f}"
        buckets[key] = buckets.get(key, 0) + 1
    return {"count": len(values), "distinct": len({round(p, 6) for p in values}), "buckets": dict(sorted(buckets.items()))}


def choose_by_gap(blind: list[dict], markets: dict[str, dict], x: int, min_gap: float = 0.10,
                  min_side_prob: float = 0.65, exclude_uninformed: bool = True) -> list[dict]:
    """Picks where the blind probability differs from the market's ask by at least min_gap, with a stated reason.
    side 'yes': p - yes_ask; side 'no': (1-p) - no_ask. Only the larger gap of the two counts."""
    cands = []
    for b in blind:
        p = b.get("probability")
        m = markets.get(str(b.get("market_id")))
        if p is None or not m or b.get("error") or b.get("no_forecast") or b.get("inconsistent"):
            continue
        uninformed = is_uninformed(b)
        if exclude_uninformed and uninformed:
            continue
        ya, na = m.get("yes_ask"), m.get("no_ask")
        gaps = []
        if ya is not None:
            gaps.append(("yes", p - float(ya), float(ya), p))
        if na is not None:
            gaps.append(("no", (1 - p) - float(na), float(na), 1 - p))
        if not gaps:
            continue
        side, gap, ask, ps = max(gaps, key=lambda g: g[1])
        if gap >= min_gap and ps >= min_side_prob:
            why = (b.get("reasons") or [""])[0]
            cands.append({"market_id": str(b["market_id"]), "basis": "gap", "side": side, "gap": round(gap, 4),
                          "ask": ask, "blind_probability": p, "side_probability": ps, "uninformed": uninformed, "score": gap,
                          "reason": f"blind forecast {ps:.0%} chance of {side.upper()} vs market ask {ask:.0%} "
                                    f"(gap {gap:+.0%}). {why}"[:400]})
    cands.sort(key=lambda c: -c["score"])
    for i, c in enumerate(cands[:x]):
        c["rank"] = i + 1
    return cands[:x]


def random_picks(pool: list[dict], x: int, seed: int = 0) -> list[str]:
    rng = random.Random(seed)
    ids = [str(m["market_id"]) for m in pool]
    rng.shuffle(ids)
    return ids[:x]


def near_fifty_picks(markets: list[dict], x: int) -> list[str]:
    """Baseline rule: the questions the market is least sure about."""
    def dist(m):
        ya = m.get("yes_ask")
        return abs(float(ya) - 0.5) if ya is not None else 1.0
    return [str(m["market_id"]) for m in sorted(markets, key=dist)[:x]]
