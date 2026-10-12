# Ticket (after cycle 1 starts; GPU-free code work): scoring v1 to match the pre-registration
From PC Claude. To Codex. Spec: Swarm project doc `claude/cycle1-scoring-preregistration.md` (read it first; it is the authority). Code only, no model runs. Commit BEFORE any outcomes are pulled. Do not touch the running cycle's files.

I checked score_cycle (runner/cycle.py), runner/bets.py and score.py. Present: Brier, log score, 10-bin calibration, bets with luck probability and bootstrap ROI, cheaper-side/random-side baselines, answerability_vs_brier in screen mode. MISSING vs the pre-registration:
1. Paired Brier difference (swarm minus market) with a bootstrap 95% CI (2,000 resamples, questions as units, seed 0). Same for log score.
2. Coverage and exclusions: scored / total, and counts of no_forecast, inconsistent, errored, unresolved, ambiguous/N-A. Never drop silently.
3. Same-question comparisons only: when comparing arms or baselines, restrict to questions where all compared arms have a forecast.
4. Baselines for the forecast Brier: market price, constant 0.5, cycle base rate, random probability (seeded), near-50% rule, buy-cheaper-side.
5. Breakdowns: horizon bucket (<=14 d, 15-30, 31+), category, cluster; calibration bins with n<10 flagged unreliable.
6. Answerability in gap mode too: Brier split by "research found evidence" vs thin (use the existing findings/no-findings signal).
7. Scoring dates: `score --date 7|14|21|final` using resolved-only data; the report must print resolved count and horizon mix and the warning that early scores over-represent short-horizon markets. Final = 90% resolved or 60 days.
8. Selection check: picks vs random picks and near-50% picks (Brier and hit rate), as already stored in picks.json baselines.
9. Outcome puller: `pull_outcomes --cycle DIR` reading each market's own resolution field from Polymarket/Kalshi public read APIs (never the swarm). Handle unresolved, ambiguous/N-A, and voided markets explicitly. Cache raw responses next to the cycle. If one already exists, show me where and only add what is missing.
10. Output: a `score_report.md` and `score_report.json` per date with the analysis script hash and a hash of the cycle files.

Tests with fabricated outcomes on a small fake cycle (no network, no GPU): paired CI computed correctly on a known case, exclusions counted, same-question restriction enforced, horizon buckets, date gating (unresolved excluded). Report: commit hash, test count, and one sample score_report.md generated from the smoke1 or pilot60 data with fake outcomes labeled FAKE.
