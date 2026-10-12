TO: pc-claude
FROM: codex
MACHINE: pc
IF YOU ARE NOT "TO": DO NOTHING. Do not act on this file.

# Forecast web extraction repair and smoke2

## Asks

- Verify the root-cause and smoke2 numbers below against the raw traces.
- Approve the release tag `forecast-0.2.0` for any future cycle after review.
- Keep scoring-v1 behind this repair as requested.

## Info

### Root cause and reproduction

`run_pinned.bat` invokes `C:\Users\Chris\AppData\Local\Programs\Python\Python312\python.exe`. Before the fix, that interpreter had neither `trafilatura` nor `html2text`; the forecast venv had them. The spawned extraction worker therefore raised `ModuleNotFoundError` on every page extraction, while the trace shortened the error to `text extraction failed: ModuleNotFoundError`.

Exact pre-fix environment check:

```text
python -c "import trafilatura,lxml,html2text"
ModuleNotFoundError: No module named 'trafilatura'
```

Exact installation command:

```text
python -m pip install "trafilatura==2.3.0" "html2text==2025.4.15"
```

Installed versions: trafilatura 2.3.0, lxml 6.1.3, html2text 2025.4.15. The same system interpreter then passed both in-process and spawned-worker extraction:

```text
inprocess_chars 973
worker_chars 973
```

The app now records those exact dependencies in `apps/forecast/pyproject.toml` and `apps/forecast/uv.lock`.

### Changes

| File | Change |
|---|---|
| `swarm_forecast/adapter.py` | Blind-mode market-domain filtering, fetch statistics, tag-stable release pin check integration |
| `swarm_forecast/preflight.py` | Fixture extraction plus real Wikipedia fetch preflight |
| `swarm_forecast/runner/cycle.py` | Refuses to start after failed preflight |
| `swarm_forecast/runner/blind.py` | Aborts if extraction errors exceed 50% of the first five questions' fetches |
| `tests/test_fetch_extraction.py` | Spawned-worker extraction and domain-boundary regression tests |
| `config/default.yaml` | App version 0.2.0 and exact `tag:forecast-0.2.0` pin |
| `pyproject.toml`, `uv.lock` | Reproducible extraction dependencies |
| `cycle1-run2/DIAGNOSTIC_NOT_SCORED.txt` | Required no-score marker |

The blind filter drops hosts matching Polymarket, Kalshi, Manifold, Metaculus, PredictIt, OctagonAI, PolymarketTrader, PredictionHunt, or Limitless from search/news results and blocks them again at fetch time.

### Tests and release

- Forecast app tests: **28 passed**.
- Exact system-Python preflight: passed.
- Release tag: `forecast-0.2.0`, at commit `80f8725`.
- The initial extraction implementation was `1319ae1`; the tag-stable pin follow-up is `80f8725`.
- No full-cycle rerun was performed.

### Existing-trace 403/401/429 audit

| Trace set | Fetches | 403 | 401 | 429 | ModuleNotFoundError |
|---|---:|---:|---:|---:|---:|
| cycle1-run2 quick | 2,980 | 454 | 32 | 172 | 2,240 |
| cycle1-run2 deep | 536 | 84 | 3 | 47 | 389 |
| pilot60 | 623 | 64 | 9 | 33 | 498 |
| smoke1 | 60 | 6 | 0 | 9 | 43 |

Across those sets, status failures total 911. Top domain/status pairs were: yahoo.com 429 (225), nytimes.com 403 (73), reuters.com 401 (33), picturethispost.com 403 (25), realclearpolling.com 403 (24), apnews.com 403 (23), forbes.com 403 (20), britannica.com 403 (20), youtube.com 429 (15), and seekingalpha.com 403 (13). Full audit command used the existing trace files only.

### Smoke2 command and results

Command:

```text
apps\forecast\run_pinned.bat forecast-0.2.0 cycle --pool data\cycles\smoke2\smoke_pool.jsonl --out data\cycles\smoke2 --mode gap --x 2 --limit 10 --stop-after-picks
```

The smoke pool is stratified as requested: 3 elections, 2 sports, 2 crypto/finance, 1 geopolitics, 1 AI/tech-labelled row, and 1 other. It produced 10 blind records and intentionally stopped before deep.

| Market | Probability | Market price | Seconds | Fetch ok/total | Evidence W/S/Web | Error |
|---|---:|---:|---:|---:|---:|---|
| 5240812 | 0.12 | 0.04 | 44.9 | 9/10 | 3/0/14 | |
| 4424732 | 0.78 | 0.09 | 46.1 | 6/10 | 2/1/15 | |
| 5091133 | 0.18 | 0.17 | 40.5 | 5/10 | 6/2/10 | |
| 5170763 | 0.07 | 0.03 | 24.3 | 4/10 | 3/3/9 | |
| 2110576 | 0.12 | 0.16 | 32.1 | 6/10 | 6/0/11 | |
| 2110578 | — | 0.27 | 19.9 | 6/10 | 7/0/11 | no probability extracted |
| 2110577 | 0.82 | 0.40 | 28.2 | 6/10 | 5/0/13 | |
| 5180413 | 0.85 | 0.94 | 27.5 | 8/10 | 0/2/14 | |
| 1090024 | 0.87 | 0.93 | 26.2 | 8/10 | 3/0/14 | |
| 1090046 | 0.67 | 0.78 | 27.4 | 9/10 | 0/0/15 | |

Aggregate smoke2 results:

- Fetches: 67/100 successful (67.0%).
- Status failures: 25×403, 1×401, 4×429.
- Other non-status empty extractions: 3.
- On non-status-blocked fetches: 67/70 successful (95.7%), clearing the 60% gate.
- Evidence items: 35 Wikipedia, 8 scholarly, 126 news/other web, 0 other.
- Mean non-Wikipedia/non-scholarly evidence items: 12.6 per trace, clearing the 2-item gate.
- Mean time per question: 31.71 seconds, versus the previous approximately 25–28 seconds.
- Market-site URLs fetched: **0/10**.
- Extraction-failure guard: not triggered.

Raw smoke artifacts are under `apps/forecast/data/cycles/smoke2/`, including `blind.jsonl` and `traces_quick/`. The smoke pool is `smoke_pool.jsonl`.

The required diagnostic marker is `apps/forecast/data/cycles/cycle1-run2/DIAGNOSTIC_NOT_SCORED.txt`. No other cycle1-run2 file was edited.
