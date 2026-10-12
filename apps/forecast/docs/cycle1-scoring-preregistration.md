# Cycle 1 scoring: pre-registration (written 2026-10-12, before any outcomes exist)

(Copy of the Swarm project doc `claude/cycle1-scoring-preregistration.md`, placed in the repo so Codex can read it. The project copy and this copy must stay identical; amendments after amendment 1 are in `cycle1-preregistration-amendments.md` next to this file.)

Cycle 1 is EXPLORATION, not the frozen capstone. Purpose: find what breaks, measure timing and coverage, start collecting resolved outcomes, and get a first look at calibration. It is not evidence that the swarm beats the market. Rules below are fixed now; any analysis added after outcomes arrive is labeled POST-HOC in the report.

## Amendments (all made BEFORE any outcomes were pulled)
- 2026-10-12, amendment 1: the first two launch attempts (`cycle1`, `cycle1-retry`) were aborted by pipeline bugs (missing runtime assets in the pinned checkout; the `no_forecast` rule keyed on manager notes, which solo-mode quick runs never have, so every record was flagged). Both are kept, never scored. The corrected rule (no_forecast = no evidence passages, no cited sources, or p of exactly 0.5 with an "no information" reason) and the blind-stage stop gate (evaluate after the first 30 records, stop if no_forecast > 25%) are in `forecast-0.1.2`. The real run is `cycle1-run2`. The pool (278 refreshed markets from the 286 sampled) is unchanged. No outcome data was seen at any point before these changes.

## Data
- Up to 300 questions from the stratified sampler (seed recorded; the sampler returned 286, of which 278 were current after refresh), prices refreshed immediately before the run, tag `forecast-0.1.2` recorded in meta.json.
- Quick (blind) forecast for all; the swarm picks up to 30 by gap; deep (informed) pass on picks; paper bets only where the deep pass confirms.
- Blind arm (no price shown) is PRIMARY. Informed arm is SECONDARY.

## Scoring dates
Score at 7, 14 and 21 days after the cycle, plus a final score when 90% of questions have resolved or at 60 days, whichever is first. At each date only resolved questions count. Report how many are resolved and their horizon mix. Warning that goes in every report: early scores over-represent short-horizon questions, so they are NOT comparable with the final score.

## Exclusions (counted, never silently dropped)
`no_forecast`, `inconsistent`, errored rows, and questions that resolve ambiguously or N/A. Report coverage = scored / total and the breakdown. Model comparisons use only questions where every compared arm has a forecast (same-question comparisons).

## Primary metric
Brier score of the blind quick forecast vs the market-implied probability (mid or last price at forecast time, recorded in the pool) on the same resolved questions. Report the paired difference (swarm Brier minus market Brier) with a bootstrap 95% CI (2,000 resamples, questions as units, seed 0). Lower is better. Also report log score.

## Secondary metrics (all with N and CI)
- Calibration: 10 bins, plus reliability table; flag bins with fewer than 10 forecasts as unreliable.
- Baselines on the same questions: market price, constant 50%, base rate of YES in this cycle, random probability, near-50% rule, "buy the cheaper side".
- Answerability: Brier by whether the research found evidence (findings present vs thin), to test "does it know when it knows".
- By category and by cluster; by horizon bucket (<=14 d, 15-30, 31+).

## Picks and paper bets
- Flat $1 paper bets only (no real trades). ROI with bootstrap 95% CI. Share of bets with entry under $0.50. Upset hits (favorite at 65%+ loses).
- Luck check: exact Poisson-binomial probability of getting at least the observed number of wins if each bet won with the market-implied probability. This is the test for "beat the market's own odds".
- Selection check: were picks different from random picks and near-50% picks (Brier and hit rate on picks vs baselines)?
- With about 30 deep picks and fewer bets, these results are descriptive only. No claim of profit or edge from cycle 1 regardless of ROI sign.

## What would count as a finding
- Blind swarm Brier better than market Brier with CI excluding zero, on at least 150 resolved questions: worth reporting as a first signal, to be confirmed in a later cycle with frozen config.
- Calibration clearly off in one direction (e.g. systematic over-confidence): a design area, fix then re-test in a later cycle.
- Coverage below 70%: a pipeline problem to fix before any accuracy claim.
- Stale-knowledge pattern: confident disagreements with liquid markets on current-status questions losing more often than not: supports the staleness guard; report count of `stale_suspect`.

## What cannot be concluded from cycle 1
Anything about profitability; anything about generalization across domains; any comparison between configs (only one config was run); any effect smaller than the CI.

## Integrity rules
No config or prompt changes during the cycle. Outcomes are pulled from the markets' own resolution fields (not by the swarm). The scoring code is committed before outcomes are pulled. The analysis script and a hash of the cycle files go in the report. If the scoring code needs fixing after seeing outcomes, record the change and show results both ways.
