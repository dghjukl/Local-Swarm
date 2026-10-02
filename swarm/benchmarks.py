"""Established benchmarks as question sets for the eval harness.

    python -m swarm.benchmarks fetch frames          # 100 random FRAMES questions (public)
    python -m swarm.benchmarks fetch gaia            # GAIA validation, levels 1-2, text-only (gated:
                                                     #   accept the terms on Hugging Face and put a
                                                     #   free HF_TOKEN in runtime/secrets.json)

The sets are written to runtime/benchmarks/<name>.yaml, which is never committed: both benchmarks
ask that their answers are not republished (answers on the open web leak into search results and
into the training data of future models).

A benchmark set is a dict {meta: {...}, questions: [...]}. Each question has an `answer` (the
reference answer) instead of a must/details checklist, and `meta` says how to grade and which
sites to block during live research (the sites that publish the answer keys):

  FRAMES  (Google, 2024)  824 questions that each need facts from 2-15 Wikipedia articles
                          combined. Graded like the FRAMES paper: an LLM rater decides whether the
                          response gives the reference answer.
  GAIA    (Meta/HF, 2023) questions for a general assistant with web access, one exact answer.
                          Graded like GAIA: the final answer is extracted and compared quasi-exactly
                          (numbers as numbers, lists element by element, case and punctuation ignored).
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import random
import re
import string
import sys

import httpx
import yaml

from swarm.paths import RUNTIME

BENCH_DIR = RUNTIME / "benchmarks"
FRAMES_URL = "https://huggingface.co/datasets/google/frames-benchmark/resolve/main/test.tsv"
GAIA_ROWS = "https://datasets-server.huggingface.co/rows"
# where the answer keys are published; never read these during a benchmark run
BLOCK = ["huggingface.co", "hf.co", "github.com", "githubusercontent.com", "gist.github.com", "kaggle.com",
         "paperswithcode.com"]


# ---------------------------------------------------------------------- answer matching (GAIA style)

def _norm_number(s: str) -> float | None:
    t = s.strip().replace(",", "").replace("$", "").replace("%", "").replace("€", "").replace("£", "")
    try:
        return float(t)
    except ValueError:
        return None


def _norm_text(s: str) -> str:
    s = s.lower().strip()
    s = s.translate(str.maketrans("", "", string.punctuation))
    s = re.sub(r"\b(a|an|the)\b", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def answers_match(given: str, gold: str) -> bool:
    """GAIA's quasi-exact match: numbers compare as numbers, comma/semicolon lists element by
    element, text ignoring case, punctuation, articles and spacing."""
    given, gold = str(given or "").strip(), str(gold or "").strip()
    if not given:
        return False
    g = _norm_number(gold)
    if g is not None:
        x = _norm_number(given)
        return x is not None and abs(x - g) <= 1e-9 * max(1.0, abs(g))
    if any(c in gold for c in ",;"):
        a = [p for p in re.split(r"[,;]", gold)]
        b = [p for p in re.split(r"[,;]", given)]
        return len(a) == len(b) and all(answers_match(y, x) for x, y in zip(a, b))
    return _norm_text(given) == _norm_text(gold)


def gold_in_text(text: str, gold: str) -> bool:
    """Cheap cross-check: does the reference answer appear in the response (as whole words)?"""
    t, g = _norm_text(text), _norm_text(gold)
    if not g:
        return False
    return re.search(r"(?<![a-z0-9])" + re.escape(g) + r"(?![a-z0-9])", t) is not None


# ---------------------------------------------------------------------- fetching

def _save(name: str, meta: dict, questions: list[dict]) -> str:
    BENCH_DIR.mkdir(parents=True, exist_ok=True)
    path = BENCH_DIR / f"{name}.yaml"
    path.write_text(yaml.safe_dump({"meta": meta, "questions": questions}, sort_keys=False, allow_unicode=True,
                                   width=4096), encoding="utf-8")
    return str(path)


def frames_from_tsv(text: str, n: int = 100, seed: int = 20260928) -> list[dict]:
    rows = list(csv.DictReader(io.StringIO(text), delimiter="\t"))
    rows = [r for r in rows if (r.get("Prompt") or "").strip() and (r.get("Answer") or "").strip()]
    idx = sorted(random.Random(seed).sample(range(len(rows)), min(n, len(rows))))
    out = []
    for i in idx:
        r = rows[i]
        out.append({"id": f"frames-{r.get('') or r.get('Unnamed: 0') or i}",
                    "question": r["Prompt"].strip(), "answer": r["Answer"].strip(),
                    "reasoning_types": (r.get("reasoning_types") or "").strip()})
    return out


def fetch_frames(n: int = 100, seed: int = 20260928) -> str:
    r = httpx.get(FRAMES_URL, follow_redirects=True, timeout=60)
    r.raise_for_status()
    qs = frames_from_tsv(r.text, n, seed)
    meta = {"name": f"frames-{len(qs)}", "benchmark": "FRAMES (google/frames-benchmark, test split)",
            "grading": "judge", "sample_seed": seed, "sampled": len(qs), "block_domains": BLOCK,
            "note": "Random sample. Answers are the reference answers from the dataset; do not commit or share."}
    return _save(f"frames-{len(qs)}", meta, qs)


def gaia_from_rows(rows: list[dict], levels=(1, 2), n: int | None = None) -> list[dict]:
    out = []
    for d in rows:
        if d.get("file_name"):  # needs an attached file (image, spreadsheet, audio...): not text-only
            continue
        if int(d.get("Level", 0) or 0) not in levels:
            continue
        out.append({"id": f"gaia-{d['task_id'][:8]}", "question": d["Question"].strip(),
                    "answer": str(d["Final answer"]).strip(), "level": int(d["Level"])})
    return out[:n] if n else out


def gaia_from_jsonl(text: str, levels=(1, 2), n: int | None = None) -> list[dict]:
    return gaia_from_rows([json.loads(l) for l in text.splitlines() if l.strip()], levels, n)


def fetch_gaia(levels=(1, 2), n: int | None = None) -> str:
    """GAIA's files are parquet now; the Hugging Face dataset viewer API returns the same rows as
    JSON (100 per page), so no parquet reader is needed."""
    from swarm.scholar import secret
    token = secret("HF_TOKEN")
    if not token:
        raise SystemExit("GAIA is gated: accept its terms at huggingface.co/datasets/gaia-benchmark/GAIA, create a "
                         "free read token (huggingface.co/settings/tokens) and put it in runtime/secrets.json as "
                         '"HF_TOKEN".')
    rows, offset = [], 0
    with httpx.Client(headers={"Authorization": f"Bearer {token}"}, timeout=60, follow_redirects=True) as c:
        while True:
            r = c.get(GAIA_ROWS, params={"dataset": "gaia-benchmark/GAIA", "config": "2023_all",
                                         "split": "validation", "offset": offset, "length": 100})
            if r.status_code in (401, 403):
                raise SystemExit(f"Hugging Face said {r.status_code}: accept the GAIA terms on its dataset page "
                                 "with the account the token belongs to, then try again.")
            r.raise_for_status()
            d = r.json()
            page = [x["row"] for x in d.get("rows", [])]
            rows += page
            offset += len(page)
            if not page or offset >= int(d.get("num_rows_total", 0) or 0):
                break
    qs = gaia_from_rows(rows, levels, n)
    meta = {"name": f"gaia-l{''.join(map(str, levels))}-text", "benchmark": "GAIA 2023 validation, text-only",
            "grading": "exact", "levels": list(levels), "count": len(qs), "of_total": len(rows),
            "block_domains": BLOCK, "note": "GAIA asks that answers are not published; do not commit or share."}
    return _save(meta["name"], meta, qs)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m swarm.benchmarks")
    sub = ap.add_subparsers(dest="cmd", required=True)
    f = sub.add_parser("fetch")
    f.add_argument("which", choices=["frames", "gaia", "all"])
    f.add_argument("-n", type=int, default=100)
    a = ap.parse_args(argv)
    if a.which in ("frames", "all"):
        print("FRAMES ->", fetch_frames(a.n))
    if a.which in ("gaia", "all"):
        try:
            print("GAIA ->", fetch_gaia())
        except SystemExit as e:
            if a.which == "gaia":
                raise
            print("GAIA skipped:", e)
    return 0


if __name__ == "__main__":
    sys.exit(main())
