"""Offline selector bake-off: given several graded attempts per question, how well does each way of
choosing one do? (Plan step 4; no GPU needed.)

    python -m swarm.selector_bench runtime/evals/20261008-0650 [--config mgr-scale8-trust] [--out report.md]

Needs a run whose results have `attempt_grades` (evals.grade_attempts). Every selector only sees what a
live system would see (the attempts' answers, citations and trust-check verdicts), never the grades;
the grades are used only to score the pick.

Selectors (ideas from Chris's earlier projects are tagged with their past-projects doc number):
  first            attempt 1 only (the single-attempt baseline)
  coordinator      the coordinator's own vote (what the run actually answered)
  majority         biggest group of attempts that give the same short answer; ties -> earliest attempt
  answered_major   majority after dropping attempts that give no answer ("cannot determine")
  ready_major      majority among attempts whose trust check ended READY; falls back to answered_major
  ready_weighted   each attempt counts 1, or 2 if its trust check ended READY
  indep_sources    each group scores the number of distinct source families its attempts cite, so
                   attempts quoting the same page count once and Wikipedia mirrors are one family (S1-#2, S2-#10)
  grounded_major   majority after dropping attempts that cite no source at all (S1-#4)
  confidence       completeness x consistency x agreement (S1-#5): group share x READY share x
                   share of its attempts that cite sources
Also reported: the oracle (any attempt right), and how often code says the attempts all agree vs how
often the coordinator's vote said so.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from urllib.parse import urlparse

STOP = set("the a an of and in on at to is was were by for with from as or it its this that be are "
           "answer final approximately about around roughly".split())
NO_ANSWER = re.compile(r"\b(cannot|can't|could not|couldn't|unable to|not (?:be )?determin|no answer|"
                       r"unknown|not enough|insufficient|not stated|not found|unclear)\b", re.I)

# domains that are copies or mirrors of the same underlying source (one "family", S2-#10)
FAMILY_ALIASES = {
    "wikipedia": ("wikipedia.org", "wikiwand.com", "wikimedia.org", "dbpedia.org", "wikidata.org",
                  "everybodywiki.com", "wiki2.org", "alchetron.com", "dbpedia", "kiwix"),
}


def family(url: str) -> str:
    host = (urlparse(url or "").netloc or "").lower()
    if host.startswith("www."):
        host = host[4:]
    for fam, needles in FAMILY_ALIASES.items():
        if any(n in host for n in needles):
            return fam
    parts = host.split(".")
    return ".".join(parts[-2:]) if len(parts) >= 2 else host


def tokens(s: str) -> list[str]:
    s = (s or "").lower().replace(",", "")
    return [t for t in re.findall(r"[a-z0-9]+(?:\.[0-9]+)?", s) if t not in STOP]


def no_answer(short: str) -> bool:
    return not tokens(short) or bool(NO_ANSWER.search(short or ""))


def same_answer(a: str, b: str) -> bool:
    """Two short answers name the same thing: numbers must match, words mostly overlap."""
    ta, tb = tokens(a), tokens(b)
    if not ta or not tb:
        return False
    na = {t for t in ta if re.fullmatch(r"\d+(?:\.\d+)?", t)}
    nb = {t for t in tb if re.fullmatch(r"\d+(?:\.\d+)?", t)}
    if (na or nb) and not (na & nb):
        return False
    sa, sb = set(ta), set(tb)
    inter = len(sa & sb)
    return inter / min(len(sa), len(sb)) >= 0.8 or inter / len(sa | sb) >= 0.6


def group(shorts: list[str], idx: list[int]) -> list[list[int]]:
    """Greedy grouping of attempts (by index) whose short answers match the group's first member."""
    groups: list[list[int]] = []
    for i in idx:
        for g in groups:
            if same_answer(shorts[g[0]], shorts[i]):
                g.append(i)
                break
        else:
            groups.append([i])
    return groups


def pick_by(groups: list[list[int]], score) -> int | None:
    if not groups:
        return None
    best = max(groups, key=lambda g: (score(g), -min(g)))
    return min(best)


def short_answers(attempts: list[dict], votes: list[dict]) -> list[str]:
    """The coordinator's vote wrote each attempt's short answer; fall back to the answer's first sentence."""
    n = len(attempts)
    for v in reversed(votes or []):
        sh = v.get("short") or []
        if len(sh) == n and all(isinstance(x, str) for x in sh):
            return sh
    out = []
    for a in attempts:
        txt = " ".join(str(a.get("answer", "")).split())
        out.append(re.split(r"(?<=[.!?])\s", txt, maxsplit=1)[0][:200])
    return out


def select_all(attempts: list[dict], shorts: list[str], ready: list[bool | None],
               chosen: int | None) -> dict[str, int | None]:
    n = len(attempts)
    allidx = list(range(n))
    cites = [[s.get("url", "") if isinstance(s, dict) else str(s) for s in (a.get("sources") or [])]
             for a in attempts]
    answered = [i for i in allidx if not no_answer(shorts[i])]
    grounded = [i for i in answered if cites[i]]
    ready_idx = [i for i in answered if ready[i]]
    g_all, g_ans = group(shorts, allidx), group(shorts, answered)
    out: dict[str, int | None] = {"first": 0, "coordinator": chosen}
    out["majority"] = pick_by(g_all, len)
    out["answered_major"] = pick_by(g_ans, len) if g_ans else out["majority"]
    out["ready_major"] = pick_by(group(shorts, ready_idx), len) if ready_idx else out["answered_major"]
    out["ready_weighted"] = pick_by(g_ans, lambda g: sum(2 if ready[i] else 1 for i in g)) if g_ans else 0
    out["indep_sources"] = (pick_by(g_ans, lambda g: (len({family(u) for i in g for u in cites[i]}), len(g)))
                            if g_ans else 0)
    out["grounded_major"] = pick_by(group(shorts, grounded), len) if grounded else out["answered_major"]

    def conf(g):
        share = len(g) / max(1, len(answered))
        rd = sum(1 for i in g if ready[i]) / len(g)
        cited = sum(1 for i in g if cites[i]) / len(g)
        return share * (0.5 + rd) * (0.5 + cited)
    out["confidence"] = pick_by(g_ans, conf) if g_ans else 0
    return out


def load(run: Path, config: str | None) -> list[dict]:
    rows = []
    for line in (run / "results.jsonl").read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        r = json.loads(line)
        if config and r["config"] != config:
            continue
        ag = r.get("attempt_grades") or []
        if len(ag) < 2 or any(g is None or g.get("score") is None for g in ag):
            continue
        try:
            t = json.loads((run / r["trace"]).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError, KeyError):
            continue
        atts = t.get("attempts") or []
        if len(atts) != len(ag):
            continue
        info = r.get("attempt_info") or [{} for _ in atts]
        rows.append({"q": r["question_id"], "config": r["config"], "attempts": atts, "votes": t.get("votes") or [],
                     "right": [g["score"] >= 0.5 for g in ag],
                     "ready": [i.get("trust_ready") for i in info],
                     "chosen": ((r.get("stats") or {}).get("attempts") or {}).get("chosen"),
                     "vote_right": (r.get("grade") or {}).get("score", 0) >= 0.5,
                     "vote_same": ((r.get("stats") or {}).get("attempts") or {}).get("same")})
    return rows


def evaluate(rows: list[dict], k: int | None = None) -> dict:
    """Score every selector over the rows; k limits each question to its first k attempts."""
    names = ["first", "coordinator", "majority", "answered_major", "ready_major", "ready_weighted",
             "indep_sources", "grounded_major", "confidence"]
    hits = {n: 0 for n in names}
    oracle = code_same = coord_same = 0
    for r in rows:
        kk = min(k or len(r["attempts"]), len(r["attempts"]))
        atts, right, ready = r["attempts"][:kk], r["right"][:kk], r["ready"][:kk]
        shorts = short_answers(r["attempts"], r["votes"])[:kk]
        chosen = (r["chosen"] - 1) if (k is None and isinstance(r["chosen"], int)) else None
        picks = select_all(atts, shorts, ready, chosen)
        for n in names:
            p = picks.get(n)
            if n == "coordinator" and p is None:
                continue
            hits[n] += bool(p is not None and right[p])
        oracle += any(right)
        code_same += len(group(shorts, list(range(kk)))) == 1
        coord_same += bool(r["vote_same"])
    n = len(rows)
    res = {name: hits[name] / n for name in names if not (name == "coordinator" and k is not None)}
    res.update({"oracle": oracle / n, "n": n, "code_all_agree": code_same, "coordinator_all_agree": coord_same})
    return res


def report(rows: list[dict]) -> str:
    if not rows:
        return "No questions with graded attempts."
    full = evaluate(rows)
    n_att = max(len(r["attempts"]) for r in rows)
    lines = [f"# Selector bake-off ({full['n']} questions, up to {n_att} attempts)", "",
             "| Selector | Right |", "|---|---|"]
    for k, v in full.items():
        if isinstance(v, float):
            lines.append(f"| {k} | {v:.1%} |")
    lines += ["", f"All attempts agree (code): {full['code_all_agree']} questions; "
                  f"coordinator's vote said all agree: {full['coordinator_all_agree']}.", "",
              "## By number of attempts (first N attempts of each question)", "",
              "| N | " + " | ".join(["first", "majority", "answered_major", "ready_major", "ready_weighted",
                                     "indep_sources", "grounded_major", "confidence", "oracle"]) + " |",
              "|" + "---|" * 10]
    for k in range(1, n_att + 1):
        e = evaluate(rows, k)
        lines.append(f"| {k} | " + " | ".join(f"{e[c]:.0%}" for c in ["first", "majority", "answered_major",
                     "ready_major", "ready_weighted", "indep_sources", "grounded_major", "confidence", "oracle"]) + " |")
    ready_known = [(rd, ok) for r in rows for rd, ok in zip(r["ready"], r["right"]) if rd is not None]
    if ready_known:
        rr = [ok for rd, ok in ready_known if rd]
        nr = [ok for rd, ok in ready_known if not rd]
        lines += ["", f"Per attempt: READY right {sum(rr)}/{len(rr)} "
                      f"({sum(rr) / max(1, len(rr)):.0%}), NOT ready right {sum(nr)}/{len(nr)} "
                      f"({sum(nr) / max(1, len(nr)):.0%})."]
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m swarm.selector_bench")
    ap.add_argument("run", help="eval folder with graded attempts")
    ap.add_argument("--config", help="only this config")
    ap.add_argument("--out", help="write the markdown report here too")
    a = ap.parse_args(argv)
    text = report(load(Path(a.run), a.config))
    print(text)
    if a.out:
        Path(a.out).write_text(text, encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
