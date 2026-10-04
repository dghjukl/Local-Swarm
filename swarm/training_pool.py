"""Build and check the separate training question pool."""
from __future__ import annotations

import argparse
import asyncio
import csv
import hashlib
import io
import json
import random
import re
import sys
import urllib.parse
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable

import httpx
import yaml

from swarm.paths import REPO, RUNTIME

POOL = RUNTIME / "training" / "pool-v1"
FRAMES_URL = "https://huggingface.co/datasets/google/frames-benchmark/resolve/main/test.tsv"
EVAL_FILES = sorted((REPO / "evals").glob("research_v*.yaml"))
BENCH_FILES = sorted((RUNTIME / "benchmarks").glob("*.yaml"))
HF_ROWS = "https://datasets-server.huggingface.co/rows"
MUSIQUE_ANS = "https://huggingface.co/datasets/voidful/MuSiQue/resolve/main/musique_ans_v1.0_train.jsonl"
MUSIQUE_FULL = "https://huggingface.co/datasets/voidful/MuSiQue/resolve/main/musique_full_v1.0_train.jsonl"
SOURCE_INFO = {
    "musique": {"dataset": "MuSiQue-Ans and MuSiQue-Full", "license": "CC BY 4.0",
                 "license_url": "https://creativecommons.org/licenses/by/4.0/",
                 "url": "https://github.com/stonybrooknlp/musique"},
    "2wiki": {"dataset": "framolfese/2WikiMultihopQA", "license": "Apache License 2.0",
              "license_url": "https://www.apache.org/licenses/LICENSE-2.0",
              "url": "https://huggingface.co/datasets/framolfese/2WikiMultihopQA"},
    "hotpotqa": {"dataset": "hotpotqa/hotpot_qa, distractor train", "license": "CC BY-SA 4.0",
                 "license_url": "https://creativecommons.org/licenses/by-sa/4.0/",
                 "url": "https://github.com/hotpotqa/hotpotqa"},
}


def norm_text(value: Any) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]+", " ", str(value or "").lower())).strip()


def word_jaccard(a: str, b: str) -> float:
    aa, bb = set(norm_text(a).split()), set(norm_text(b).split())
    return len(aa & bb) / len(aa | bb) if aa and bb else 0.0


def contamination(question: str, eval_questions: list[str], frame_titles: list[set[str]], answer: str = "", year: int = 2026) -> str | None:
    if str(year) in f"{question} {answer}":
        return "events_2026"
    nq = norm_text(question)
    if any(nq == norm_text(x) for x in eval_questions):
        return "eval_exact"
    if any(word_jaccard(question, x) >= 0.6 for x in eval_questions):
        return "eval_fuzzy"
    return None


def frame_title_overlap(supporting_titles: Iterable[str], frame_titles: list[set[str]]) -> bool:
    ours = {norm_text(x) for x in supporting_titles if x}
    return any(len(ours & titles) >= 2 for titles in frame_titles)


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _jsonl(data: bytes) -> list[dict]:
    return [json.loads(line) for line in data.decode("utf-8-sig").splitlines() if line.strip()]


def _paragraphs_from_musique(row: dict) -> tuple[list[dict], list[str]]:
    docs, titles = [], []
    for p in row.get("paragraphs") or []:
        text, title = str(p.get("paragraph_text") or "").strip(), str(p.get("title") or "").strip()
        if text and title:
            docs.append({"title": title, "url": "https://en.wikipedia.org/wiki/" + urllib.parse.quote(title.replace(" ", "_")),
                         "text": text, "source": "web", "error": ""})
            if p.get("is_supporting"):
                titles.append(title)
    return docs, titles


def _paragraphs_from_context(row: dict) -> tuple[list[dict], list[str]]:
    context = row.get("context") or {}
    docs = []
    for title, sentences in zip(context.get("title", []), context.get("sentences", [])):
        title = str(title).strip()
        text = " ".join(str(x).strip() for x in (sentences or []) if str(x).strip())
        if title and text:
            docs.append({"title": title, "url": "https://en.wikipedia.org/wiki/" + urllib.parse.quote(title.replace(" ", "_")),
                         "text": text, "source": "web", "error": ""})
    titles = [str(x).strip() for x in (row.get("supporting_facts") or {}).get("title", []) if str(x).strip()]
    return docs, titles


def _question(source: str, row: dict, qtype: str, docs: list[dict], titles: list[str], answerable: bool | None = True) -> dict | None:
    question = str(row.get("question") or "").strip()
    is_answerable = bool(row.get("answerable", True)) if answerable is None else answerable
    answer = str(row.get("answer") or "").strip()
    if not is_answerable:
        answer = "The evidence does not contain enough information to answer this."
    if not question or not answer or not docs or not titles:
        return None
    return {"id": f"{source}-{str(row.get('id') or hashlib.sha1(question.encode()).hexdigest()[:12])}",
            "question": question, "answer": answer,
            "answer_aliases": [str(x) for x in row.get("answer_aliases", []) if str(x).strip()],
            "source": source, "type": qtype, "answerable": is_answerable,
            "supporting_titles": list(dict.fromkeys(titles)), "_docs": docs}


def normalize_musique(rows: Iterable[dict], _legacy_answerable: bool | None = None) -> list[dict]:
    out = []
    for row in rows:
        docs, titles = _paragraphs_from_musique(row)
        decomp = row.get("question_decomposition") or []
        hops = len(decomp) or sum(1 for p in row.get("paragraphs") or [] if p.get("is_supporting"))
        is_answerable = bool(row.get("answerable", True))
        qtype = "unanswerable" if not is_answerable else (f"{hops}hop" if hops in (2, 3, 4) else "compositional")
        q = _question("musique", row, qtype, docs, titles, is_answerable)
        if q:
            q["subquestions"] = [str(x.get("question") or "") for x in decomp if x.get("question")] or [q["question"]]
            out.append(q)
    return out


def normalize_2wiki(rows: Iterable[dict]) -> list[dict]:
    out = []
    for row in rows:
        docs, titles = _paragraphs_from_context(row)
        q = _question("2wiki", row, str(row.get("type") or "compositional").replace("_", "-"), docs, titles)
        if q:
            q["subquestions"] = [q["question"]]
            out.append(q)
    return out


def hotpot_type(question: str) -> str:
    q = question.lower()
    return "comparison" if any(x in q for x in ("which", "who", "what", "more", "less", "first", "earlier", "larger")) else "bridge"


def normalize_hotpot(rows: Iterable[dict]) -> list[dict]:
    out = []
    for row in rows:
        if str(row.get("level", "")).lower() != "hard":
            continue
        docs, titles = _paragraphs_from_context(row)
        q = _question("hotpotqa", row, str(row.get("type") or hotpot_type(str(row.get("question") or ""))).replace("_", "-"), docs, titles)
        if q:
            q["subquestions"] = [q["question"]]
            out.append(q)
    return out


def _simple_false_premise(q: dict) -> dict | None:
    title = q.get("supporting_titles", [None])[0]
    by_title = {norm_text(d["title"]): d["text"] for d in q.get("_docs", [])}
    text = by_title.get(norm_text(title), "")
    if not title or not text:
        return None
    title_words = norm_text(title).split()
    sentence = next((s.strip() for s in re.split(r"(?<=[.!?])\s+", text)
                     if s.strip() and title_words and title_words[0] in norm_text(s).split()[:6]), "")
    pattern = re.compile(r"\b(?P<verb>founded|established|born|released|created|opened|formed|started|published)\b[^.]{0,100}?\b(?:in|on)\s+(?P<year>1[5-9]\d{2}|20[0-2]\d)\b", re.I)
    match = pattern.search(sentence)
    if not match or norm_text(title) not in norm_text(sentence):
        return None
    true, verb = match.group("year"), match.group("verb").lower()
    offset = 3 + (sum(ord(c) for c in title) % 13)
    false = str(int(true) + offset)
    prompt = f"Why was {title} {verb} in {false}?"
    answer = f"The premise is false: {title} was {verb} in {true}, not {false}."
    out = dict(q)
    out["id"], out["question"], out["answer"] = q["id"] + "-fp", prompt, answer
    out["source"], out["answerable"], out["type"] = "false-premise", False, "false-premise"
    out["_false_source_sentence"] = sentence
    return out


def derive_false_premises(items: Iterable[dict], n: int, seed: int) -> list[dict]:
    candidates, seen = [], set()
    for q in items:
        fp = _simple_false_premise(q)
        if fp and fp["question"] not in seen:
            seen.add(fp["question"])
            candidates.append(fp)
    random.Random(seed).shuffle(candidates)
    return candidates[:n]


def trim_evidence(q: dict, max_words: int = 12000) -> dict | None:
    gold = set(q.get("supporting_titles", []))
    docs = list(q.get("_docs", []))
    gold_docs = [d for d in docs if d.get("title") in gold]
    if sum(len(str(d.get("text", "")).split()) for d in gold_docs) > max_words:
        return None
    keep, words = list(gold_docs), sum(len(str(d.get("text", "")).split()) for d in gold_docs)
    for doc in docs:
        if doc in gold_docs:
            continue
        size = len(str(doc.get("text", "")).split())
        if words + size <= max_words:
            keep.append(doc); words += size
    out = dict(q); out["_docs"] = keep
    return out


def stratified_split(items: list[dict], seed: int, dev_fraction: float = 0.1) -> tuple[list[dict], list[dict]]:
    groups: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for item in items:
        groups[(item["source"], item["type"])].append(item)
    train, dev, rng = [], [], random.Random(seed)
    for group in groups.values():
        group = list(group)
        rng.shuffle(group)
        ndev = max(1, round(len(group) * dev_fraction)) if len(group) > 1 else 0
        dev.extend(group[:ndev]); train.extend(group[ndev:])
    return sorted(train, key=lambda x: x["id"]), sorted(dev, key=lambda x: x["id"])


def _public(q: dict) -> dict:
    return {k: v for k, v in q.items() if not k.startswith("_") and k != "_docs"}


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")


async def _get(client: httpx.AsyncClient, url: str, params: dict | None = None) -> bytes:
    for attempt in range(7):
        response = await client.get(url, params=params, timeout=120)
        if response.status_code != 429:
            response.raise_for_status()
            return response.content
        retry_after = response.headers.get("retry-after")
        delay = float(retry_after) if retry_after and retry_after.replace(".", "", 1).isdigit() else min(60.0, 2.0 ** attempt)
        await asyncio.sleep(delay)
    response.raise_for_status()
    return response.content


async def _cached_download(client: httpx.AsyncClient, url: str, name: str) -> bytes:
    path = RUNTIME / "training" / "cache" / name
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        return path.read_bytes()
    data = await _get(client, url)
    path.write_bytes(data)
    return data


async def fetch_hf_rows(dataset: str, config: str, split: str, total: int, concurrency: int = 2) -> tuple[list[dict], str, str]:
    sem = asyncio.Semaphore(concurrency)
    offsets = list(range(0, total, 100))
    async with httpx.AsyncClient(follow_redirects=True) as client:
        async def one(offset: int):
            async with sem:
                return offset, await _get(client, HF_ROWS, {"dataset": dataset, "config": config, "split": split,
                                                              "offset": offset, "length": min(100, total - offset)})
        pages = await asyncio.gather(*(one(offset) for offset in offsets))
    rows, raw = [], bytearray()
    for _, data in sorted(pages):
        raw.extend(data)
        rows.extend(x["row"] for x in json.loads(data).get("rows", []))
    return rows, HF_ROWS, _sha(bytes(raw))


async def fetch_parquet_rows(urls: list[str], cache_name: str, caps: dict[str, int]) -> tuple[list[dict], list[dict]]:
    """Download the converted parquet files once, then read them with pyarrow."""
    try:
        import pyarrow.parquet as pq
    except ImportError as exc:
        raise RuntimeError("pyarrow is required for the training-pool build; run uv sync") from exc
    cache = RUNTIME / "training" / "cache" / cache_name
    cache.mkdir(parents=True, exist_ok=True)
    files, records = [], []
    async with httpx.AsyncClient(follow_redirects=True) as client:
        for index, url in enumerate(urls):
            path = cache / f"{index:04d}.parquet"
            if not path.exists():
                data = await _get(client, url)
                path.write_bytes(data)
            files.append({"url": url, "sha256": _sha(path.read_bytes()), "bytes": path.stat().st_size})
            # Keep a deterministic reservoir per source type. The full parquet file is still
            # downloaded and hashed, but only a bounded candidate set is materialized.
            rng = random.Random(f"training-pool-v1:{cache_name}")
            reservoirs: dict[str, list[dict]] = defaultdict(list)
            seen: Counter[str] = Counter()
            parquet = pq.ParquetFile(path)
            for batch in parquet.iter_batches(batch_size=2048):
                for row in batch.to_pylist():
                    key = str(row.get("type") or "bridge")
                    limit = caps.get(key, max(caps.values()))
                    seen[key] += 1
                    bucket = reservoirs[key]
                    if len(bucket) < limit:
                        bucket.append(row)
                    else:
                        slot = rng.randrange(seen[key])
                        if slot < limit:
                            bucket[slot] = row
            records.extend(row for bucket in reservoirs.values() for row in bucket)
    return records, files


def _read_blocked_questions() -> list[str]:
    out = []
    for path in EVAL_FILES + BENCH_FILES:
        if path.exists():
            data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
            rows = data.get("questions", []) if isinstance(data, dict) else data
            out.extend(str(q.get("question") or "") for q in rows if isinstance(q, dict) and q.get("question"))
    return out


def _frame_titles(data: str) -> list[set[str]]:
    out = []
    for row in csv.DictReader(io.StringIO(data), delimiter="\t"):
        raw = row.get("wiki_links") or row.get("WikiLinks") or ""
        try:
            vals = json.loads(raw)
        except Exception:
            vals = re.findall(r"[A-Z][^,;|]+", raw)
        out.append({norm_text(x) for x in vals if x})
    return out


def _select_balanced(candidates: list[dict], quotas: dict[str, int], seed: int) -> list[dict]:
    rng, by = random.Random(seed), defaultdict(list)
    for q in candidates:
        by[q["type"]].append(q)
    out = []
    for key, n in quotas.items():
        xs = by.get(key, []); rng.shuffle(xs)
        if len(xs) < n:
            raise RuntimeError(f"source quota {key} needs {n}, found {len(xs)}")
        out.extend(xs[:n])
    return out


def _counts(items: Iterable[dict], key: str) -> dict[str, int]:
    return dict(sorted(Counter(str(x.get(key, "")) for x in items).items()))


async def build(n: int = 3000, seed: int = 20261003) -> Path:
    if n != 3000:
        raise ValueError("pool-v1 uses the specified 3000-item allocation")
    eval_questions, dropped, downloads = _read_blocked_questions(), Counter(), {}
    async with httpx.AsyncClient(follow_redirects=True) as client:
        ans_bytes = await _cached_download(client, MUSIQUE_ANS, "musique-ans-train.jsonl")
        full_bytes = await _cached_download(client, MUSIQUE_FULL, "musique-full-train.jsonl")
    downloads["musique_ans"] = {"url": MUSIQUE_ANS, "sha256": _sha(ans_bytes), "bytes": len(ans_bytes)}
    downloads["musique_full"] = {"url": MUSIQUE_FULL, "sha256": _sha(full_bytes), "bytes": len(full_bytes)}
    ans = normalize_musique(_jsonl(ans_bytes))
    full = [q for q in normalize_musique(_jsonl(full_bytes)) if not q["answerable"]]
    rows2, files2 = await fetch_parquet_rows([
        "https://huggingface.co/datasets/framolfese/2WikiMultihopQA/resolve/refs%2Fconvert%2Fparquet/default/train/0000.parquet",
        "https://huggingface.co/datasets/framolfese/2WikiMultihopQA/resolve/refs%2Fconvert%2Fparquet/default/train/0001.parquet"], "2wiki",
        {"comparison": 800, "inference": 800, "compositional": 800, "bridge_comparison": 800})
    rows_hp, files_hp = await fetch_parquet_rows([
        "https://huggingface.co/datasets/hotpotqa/hotpot_qa/resolve/refs%2Fconvert%2Fparquet/distractor/train/0000.parquet",
        "https://huggingface.co/datasets/hotpotqa/hotpot_qa/resolve/refs%2Fconvert%2Fparquet/distractor/train/0001.parquet"], "hotpotqa",
        {"comparison": 1200, "bridge": 1200})
    downloads["2wiki_train"] = {"dataset": "framolfese/2WikiMultihopQA/default/train", "files": files2, "rows": len(rows2)}
    downloads["hotpotqa_train"] = {"dataset": "hotpotqa/hotpot_qa/distractor/train", "files": files_hp, "rows": len(rows_hp)}
    two, hot = normalize_2wiki(rows2), normalize_hotpot(rows_hp)
    async with httpx.AsyncClient(follow_redirects=True) as client:
        frames_bytes = await _get(client, FRAMES_URL)
    downloads["frames_check"] = {"url": FRAMES_URL, "sha256": _sha(frames_bytes), "bytes": len(frames_bytes)}
    frame_titles = _frame_titles(frames_bytes.decode("utf-8-sig"))

    def clean(items: list[dict]) -> list[dict]:
        out, seen = [], set()
        for q in items:
            reason = contamination(q["question"], eval_questions, frame_titles, q["answer"])
            if reason:
                dropped[reason] += 1; continue
            if frame_title_overlap(q["supporting_titles"], frame_titles):
                dropped["frames_title_overlap"] += 1; continue
            if q["question"] in seen:
                dropped["duplicate"] += 1; continue
            if not q.get("_docs") or not q.get("supporting_titles"):
                dropped["missing_paragraphs"] += 1; continue
            q = trim_evidence(q)
            if q is None:
                dropped["evidence_too_large"] += 1; continue
            seen.add(q["question"]); out.append(q)
        return out

    ans, full, two, hot = map(clean, (ans, full, two, hot))
    false_items = clean(derive_false_premises(ans + two + hot, 100, seed + 1))
    if len(false_items) < 100:
        raise RuntimeError(f"only {len(false_items)} conservative false-premise items were derived")
    ans_selected = _select_balanced(ans, {"2hop": 400, "3hop": 400, "4hop": 400}, seed)
    used_questions = {norm_text(q["question"]) for q in ans_selected}
    full_unique = [q for q in full if norm_text(q["question"]) not in used_questions]
    dropped["duplicate_question_text"] += len(full) - len(full_unique)
    full_selected = _select_balanced(full_unique, {"unanswerable": 300}, seed + 1)
    used_questions.update(norm_text(q["question"]) for q in full_selected)
    two_selected = _select_balanced(two, {"comparison": 200, "inference": 200, "compositional": 200,
                                          "bridge-comparison": 200}, seed + 2)
    hot_selected = _select_balanced(hot, {"comparison": 300, "bridge": 300}, seed + 3)
    selected = ans_selected + full_selected + two_selected + hot_selected + false_items[:100]
    if len({norm_text(q["question"]) for q in selected}) != len(selected):
        raise RuntimeError("duplicate question text remained after source selection")
    if len(selected) != 3000:
        raise AssertionError(len(selected))
    train, dev = stratified_split(selected, seed)
    POOL.mkdir(parents=True, exist_ok=True)
    for path in list(POOL.glob("train-*.yaml")) + list(POOL.glob("dev-*.yaml")):
        path.unlink()
    for sub in (POOL / "evidence", POOL / "gold"):
        sub.mkdir(parents=True, exist_ok=True)
    for split, items in (("train", train), ("dev", dev)):
        for shard_no, start in enumerate(range(0, len(items), 100), 1):
            shard = items[start:start + 100]
            meta = {"name": f"pool-v1-{split}-{shard_no:03d}", "benchmark": "training pool v1",
                    "grading": "judge", "sample_seed": seed, "note": "TRAINING ONLY. Never use for evaluation claims."}
            (POOL / f"{split}-{shard_no:03d}.yaml").write_text(yaml.safe_dump(
                {"meta": meta, "questions": [_public(q) for q in shard]}, sort_keys=False,
                allow_unicode=True, width=4096), encoding="utf-8")
            for q in shard:
                docs = list(q["_docs"]); random.Random(f"{seed}:{q['id']}").shuffle(docs)
                _write_json(POOL / "evidence" / f"{q['id']}.json",
                            {"plan": {"mode": "research", "subquestions": q.get("subquestions", [q["question"]]),
                                      "search_queries": [], "seconds": 0}, "docs": docs})
                _write_json(POOL / "gold" / f"{q['id']}.json", {
                    "supporting_titles": q["supporting_titles"],
                    "supporting_indices": [i for i, d in enumerate(docs) if d["title"] in q["supporting_titles"]],
                    "answerable": q["answerable"]})
    lines = ["# False-premise spot-check sample", "", "Derived from explicit source facts. Each reference answer rejects the premise and states the true fact.", ""]
    for i, q in enumerate(false_items[:20], 1):
        lines += [f"{i}. **Q:** {q['question']}", f"   **A:** {q['answer']}", ""]
    (POOL / "false-premise-sample.md").write_text("\n".join(lines), encoding="utf-8")
    manifest = {"name": "pool-v1", "seed": seed, "total": len(selected), "train": len(train), "dev": len(dev),
                "sources": SOURCE_INFO | {"downloads": downloads},
                "counts": {"source": _counts(selected, "source"), "type": _counts(selected, "type"),
                           "split": {"train": len(train), "dev": len(dev)}},
                "dropped": dict(sorted(dropped.items())),
                "contamination": {"eval_files": [str(x) for x in EVAL_FILES], "fuzzy_word_jaccard": 0.6,
                                  "frames_title_overlap": "drop when two or more supporting titles match one FRAMES question"},
                "false_premise": {"count": len(false_items), "method": "derived from explicit, title-named year facts",
                                  "answerable": False, "spot_check": "false-premise-sample.md"}}
    _write_json(POOL / "manifest.json", manifest)
    return POOL


def check(path: Path = POOL) -> dict:
    manifest = json.loads((path / "manifest.json").read_text(encoding="utf-8"))
    questions = []
    for file in sorted(path.glob("train-*.yaml")) + sorted(path.glob("dev-*.yaml")):
        questions.extend((yaml.safe_load(file.read_text(encoding="utf-8")) or {}).get("questions", []))
    issues, ids, question_texts = Counter(), set(), set()
    frame_url = (manifest.get("sources", {}).get("downloads", {}).get("frames_check", {}).get("url") or FRAMES_URL)
    try:
        frame_data = httpx.get(frame_url, timeout=120).text
        frame_titles = _frame_titles(frame_data)
    except Exception:
        frame_titles = []
        issues["frames_unavailable"] += 1
    for q in questions:
        if q["id"] in ids: issues["duplicate_id"] += 1
        ids.add(q["id"])
        key = norm_text(q.get("question", ""))
        if key in question_texts: issues["duplicate_question_text"] += 1
        question_texts.add(key)
        if contamination(q.get("question", ""), _read_blocked_questions(), frame_titles, q.get("answer", "")): issues["contamination"] += 1
        if frame_title_overlap(q.get("supporting_titles", []), frame_titles): issues["frames_title_overlap"] += 1
        if q.get("type") == "false-premise" and (q.get("source") != "false-premise" or q.get("answerable") is not False):
            issues["bad_false_premise_flags"] += 1
        evidence_path = path / "evidence" / f"{q['id']}.json"
        if evidence_path.exists():
            evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
            if sum(len(str(d.get("text", "")).split()) for d in evidence.get("docs", [])) > 12000:
                issues["evidence_over_12000_words"] += 1
            if any(d.get("source") != "web" or not d.get("url") for d in evidence.get("docs", [])):
                issues["bad_evidence_metadata"] += 1
        if not evidence_path.exists(): issues["missing_evidence"] += 1
        if not (path / "gold" / f"{q['id']}.json").exists(): issues["missing_gold"] += 1
    result = {"questions": len(questions), "issues": dict(issues), "manifest": manifest.get("counts", {})}
    print(json.dumps(result, indent=2))
    if issues: raise SystemExit(1)
    return result


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m swarm.training_pool")
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build"); b.add_argument("--n", type=int, default=3000); b.add_argument("--seed", type=int, default=20261003)
    sub.add_parser("check")
    args = ap.parse_args(argv)
    if args.cmd == "build": print(asyncio.run(build(args.n, args.seed)))
    else: check()
    return 0


if __name__ == "__main__":
    sys.exit(main())
