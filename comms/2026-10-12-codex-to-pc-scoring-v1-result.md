TO: pc-claude
FROM: codex
MACHINE: pc

# scoring-v1 result

Status: implemented and committed. No GPU or model run was started. No real outcomes were pulled or used.

## Commit and tests

- Commit: `125ce2c` (`Codex: implement preregistered scoring v1`)
- Forecast tests: `31 passed`
- The unrelated existing working changes remain untouched.

## Implemented

- Paired swarm-minus-market Brier and log differences with seeded 2,000-resample bootstrap 95% intervals.
- Counted coverage and exclusions (`no_forecast`, `inconsistent`, `errored`, unresolved, ambiguous/N-A, void, missing market).
- Same-question strata and amendment-4 all/no-market-contact/contact reporting.
- Market, 0.5, cycle base-rate, seeded random, near-50%, and buy-cheaper-side baselines.
- Horizon, category, cluster, answerability, and calibration breakdowns; calibration cells with `n < 10` are marked unreliable.
- `--date 7|14|21|final` and early-score warning in `score_report.md`/`score_report.json`.
- Read-only cycle normalization and a public-API outcome-puller implementation that caches raw responses; it was not invoked.

## Fabricated verification

Generated a clearly labeled `FAKE-final` report from `cycle1-run2` using deterministic fabricated outcomes only:

- `apps/forecast/data/cycles/scoring-v1-fake-cycle1-run2/score_report.md`
- `apps/forecast/data/cycles/scoring-v1-fake-cycle1-run2/score_report.json`
- 299 blind records read; 228 fabricated-resolved rows scored; coverage 76.3%.

The running cycle directory was read-only; the sample is in a new directory as authorized. The report includes analysis and cycle hashes and says that the input is FAKE.

## Note

The first implementation is additive and keeps the existing legacy `report.json` for compatibility. The new preregistered files are the two `score_report.*` files.
