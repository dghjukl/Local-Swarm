# Forecast Cycle 1 report

Date: 2026-10-12
Status: stopped at the blind-stage no-forecast gate; no deep stage or bets ran.

## Pin and preflight

- Forecast config now pins swarm tag `forecast-0.1`, commit `1609e839dc0c75d9eb329405a22fadf882ad816e`.
- App/config packaging and the import guard were recorded in local commit `c0ba567`; tag `forecast-0.1.1` marks that app release state. The cycle used the exact swarm checkout required by the config, `forecast-0.1`.
- Forecast tests: 22 passed.
- The wrapper `run_pinned.bat` has an argument-forwarding bug: it creates the requested worktree but forwards the tag to the Python CLI. The cycle was run directly with the same pinned worktree instead; the wrapper was not edited during this run.
- The pinned worktree needed junctions to the existing local `Models` and `Bin` directories because those large, ignored runtime assets are not in the worktree. Only the required model directories and `Bin` were linked; no model files were copied or changed.

## Pool and refresh

- Phase 0e sampler requested 300 and selected 286 from the 1,254-record Phase 0d batch. The sampler report records the shortfall caused by the cluster/theme/sports caps.
- All 286 selected markets were refreshed read-only at one request per second. There were 8 stale markets and 0 refresh errors.
- The runnable pool is `apps/forecast/data/cycle1_pool.jsonl`: 278 current markets, with refreshed top-level quotes, and 8 stale records excluded. No reserve replacements were available.
- Stale market IDs: `4294627`, `5151886`, `5407561`, `5166884`, `4951225`, `5476380`, `5170735`, `3072353`.

## Run results

- First attempt: `data/cycles/cycle1`, 278/278 immediate failures because the pinned worktree lacked `Bin/llama-cuda/llama-server.exe`. The failed artifact is preserved.
- Retry: `data/cycles/cycle1-retry`, using the shared runtime junction. Three blind records completed before the stop: 3/3 were `no_forecast`, 0 usable probabilities. Research traces contained prose and reasons, but the runner's `notes` field was empty, so the guard marked them `no_forecast` and emitted `no probability could be extracted`.
- Because 100% of observed blind records were `no_forecast`, exceeding the ticket's 25% threshold, the run was stopped before the remaining blind questions. Deep and bets did not run. No score was produced.
- GPU lock was released after the interrupted run; it is currently free.

## Needs follow-up

The forecast extraction/notes contract needs repair or an explicit decision before rerunning Cycle 1. The swarm is returning research prose, but the forecast app is treating empty manager notes as no findings. The wrapper argument bug should also be fixed before the next operational run.

