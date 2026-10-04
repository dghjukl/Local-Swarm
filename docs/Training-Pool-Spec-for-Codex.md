# Task for Codex: build the training question pool (for LoRA strategy distillation)

## Context
Local Swarm (this repo) will later train LoRA adapters that make each model's best reasoning strategy native (see the "Main use" section of the LoRA plan). That step needs a **training question pool** that is completely separate from the evaluation sets, with saved evidence so traces can be generated offline and deterministically.

**This task only builds the pool.** Do not generate traces, train anything, or change the swarm's runtime behavior.

## Deliverables
1. `swarm/training_pool.py`, a CLI in the style of `swarm/benchmarks.py` (httpx downloads, yaml output, `RUNTIME` paths):
   - `python -m swarm.training_pool build --n 3000 --seed 20261003`
   - `python -m swarm.training_pool check` (re-runs the contamination checks on an existing pool)
2. `Build-Training-Pool.bat`, matching the other .bat files (uses the repo's uv / venv the same way they do).
3. Output under `runtime/training/pool-v1/`. `runtime/` is gitignored; dataset content must never be committed.
4. Tests in `tests/test_units.py` (or a new `tests/test_training_pool.py`). They must run offline with small fixture rows; no network in tests.
5. A short section in `README.md` on what the pool is, how to build it, and that it must never be mixed with eval sets.

## Sources (train splits only)

| Source | Use | Approx. count | Notes |
|---|---|---|---|
| MuSiQue-Ans (train) | 2/3/4-hop composition | 1,200 (balanced by hop count) | Includes `question_decomposition`. Use it as the plan's sub-questions. Has answer aliases. |
| MuSiQue-Full (train), unanswerable items | "the evidence doesn't say" | 300 | Teaches models not to invent answers |
| 2WikiMultiHopQA (train) | comparison, inference, compositional, bridge-comparison | 800 (balanced by type) | |
| HotpotQA (train, distractor setting, level "hard") | bridge and comparison | 600 | |
| False-premise slice | trap questions | 100–200 | Find a suitably licensed false-premise QA dataset (e.g. CREPE or similar), or derive by negating a fact in a MuSiQue/2Wiki question with a clear premise flag. Record which method was used. |

- **Verify each dataset's license** before using it, and record it in the manifest (I believe MuSiQue is CC BY 4.0, HotpotQA CC BY-SA 4.0 and 2Wiki Apache 2.0, but check).
- Download from Hugging Face or the official release. If a token is needed, read `HF_TOKEN` from `runtime/secrets.json`; never print, log or commit it. No paid APIs.
- Record each download's URL and sha256 in the manifest.

## Hard exclusions (contamination guard)
Never include anything from:
- FRAMES (any row: FRAMES has only a test split, all of it is off-limits, not just our 100)
- GAIA
- `evals/research_v*.yaml`
- any `runtime/benchmarks/*.yaml`

Checks:
1. Normalized exact match and fuzzy match (word Jaccard ≥ 0.6) of each question against every eval question.
2. Drop any candidate whose supporting Wikipedia article titles share **2 or more** titles with any single FRAMES question (FRAMES' `wiki_links` column; fetch the FRAMES TSV the same way `benchmarks.py` does, only for this check).
3. Drop questions about events in 2026, since the 2026 eval set covers those (filter on "2026" in question/answer text).
4. `check` reports counts dropped per rule, and fails (exit 1) if any overlap remains.

## Output format
Must load with the existing `load_set()` and work with `python -m swarm.evals --reuse-evidence`.

```
runtime/training/pool-v1/
  manifest.json                 sources, licenses, URLs, sha256, seed, counts per source/type/split, exclusion counts
  train-001.yaml ... train-NNN.yaml   shards of 100 questions
  dev-001.yaml ...              held-out split (10%, stratified) for testing adapters later
  evidence/<id>.json            one per question
  gold/<id>.json                supporting-paragraph labels (analysis only, never shown to models)
```

**Question YAML** (same shape as `runtime/benchmarks/frames-100.yaml`):
```yaml
meta: {name: pool-v1-train-001, benchmark: "training pool v1", grading: judge, sample_seed: 20261003,
       note: "TRAINING ONLY. Never use for evaluation claims."}
questions:
- id: musique-2hop-000123          # <source>-<type>-<n>, unique and stable for a given seed
  question: ...
  answer: ...
  answer_aliases: [...]            # when the dataset has them
  source: musique | 2wiki | hotpotqa | false-premise
  type: 2hop | 3hop | 4hop | comparison | inference | compositional | bridge | bridge-comparison | unanswerable | false-premise
  answerable: true
  supporting_titles: [...]
```

**Evidence JSON** (same schema as `runtime/evals/20260928-1323/evidence/*.json`):
```json
{"plan": {"mode": "research", "subquestions": ["..."], "search_queries": [], "seconds": 0},
 "docs": [{"url": "https://en.wikipedia.org/wiki/<Title>", "title": "<Title>", "text": "...",
           "source": "wikipedia", "error": ""}]}
```
- `docs` = gold paragraphs + the dataset's distractor paragraphs, **shuffled with the seed** (gold must not always come first).
- `subquestions`: MuSiQue's decomposition where available, else `[question]`.
- Gold/supporting flags go only in `gold/<id>.json`.

## Requirements
- Deterministic: the same seed gives byte-identical output.
- Stratified 90/10 train/dev split by source × type.
- Questions with missing or empty paragraphs are dropped (count them in the manifest).
- Keep total evidence per question under about 12k words; trim distractors first, never gold.
- Don't touch existing eval files, configs.yaml, frozen configs or `swarm/evals.py` behavior.
- Run the full test suite (`Run-Tests.bat`); all existing tests must still pass.

## Out of scope (later steps, don't build)
Trace generation, filtering by grade, LoRA training, adapter loading.
