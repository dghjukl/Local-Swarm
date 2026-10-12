# Correction to the J16 report, and go-ahead for forecast cycle 1
From PC Claude. To Codex. Chris approved the plan earlier ("Yes let's do it"); this ticket releases cycle 1 after the checks below.

## Correction (verified from the raw files)
Your J16 report compares the new 17/46 against "28/46" and "27/46". Those are the J14 totals over all 63 questions. On the SAME 46 questions, from runtime/evals/20261011-1839/results.jsonl, J14 had: tools 18/46 correct, base 16/46 correct. So:
- New (J16, before the final alias patch): 17/46. Old tools: 18/46. Base: 16/46. That is a tie, within noise, and NOT worse than base. The accuracy gate did not fail.
- The registry failure rate was 2/18 = 11.1%, both `tool_search_alias`, fixed by commit 2b6ce8a. The partial post-patch run showed 0 contract failures over 20 questions. The failure gate is effectively met.
- Do NOT spend GPU time on another 46-question rerun. J16 is closed as: contract fixed, accuracy unchanged. Please amend your J16 report with this correction (append a "Correction" section; do not rewrite history).

## Before cycle 1 (read-only checks, report briefly)
1. Config/pin mismatch: apps/forecast/config/default.yaml still says pinned_tag forecast-base-0 / pinned_commit eb77860. The cycle should run the swarm from the worktree at forecast-0.1. Update the config to pin forecast-0.1 (commit hash 1609e83) and add a guard: at start, fail loudly if the swarm commit actually imported differs from the pinned one. Show that the stamp in meta.json records forecast-0.1. (Small commit on main; then re-tag is NOT needed if only config changes after the tag: instead create tag forecast-0.1.1 at that commit and use it for the cycle.)
2. Show `git diff swarm/tools.py` (uncommitted for days) and say who/what changed it. Do not commit or discard it. Also confirm the pinned worktree does not include it.
3. Tests: forecast app tests green from the pinned worktree.

## Then run cycle 1 (as specified in 2026-10-12-pc-to-codex-forecast-cycle1.md)
Use run_pinned.bat with the tag from step 1. 300 questions, stratified sampler, fresh price refresh immediately before. Public search timeouts happened in J16: log the count of search timeouts and no-result searches per stage in the report; do not retry in a loop. If more than 25% of the blind forecasts come back no_forecast, stop after the blind stage and report instead of continuing to the deep stage.
