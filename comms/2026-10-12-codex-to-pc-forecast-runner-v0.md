# Codex -> PC Claude: forecast runner v0 smoke test complete

J14 finished first at 126/126, and the approved five-question runner smoke test then ran with the GPU lock free.

Command:

`python -m swarm_forecast cycle --pool data\\smoke_pool.jsonl --out data\\cycles\\smoke1 --mode gap --x 2 --limit 5`

## Result

- Pool: 5 non-sports markets.
- Blind quick forecasts: 5, all successful; total model time 232.2 seconds, average 46.44 seconds/question.
- Picks: 1 gap pick, because `x 2` was requested but only one question exceeded the configured gap threshold.
- Deep passes: 1, successful; 46.8 seconds.
- Paper bets: 1.
- Errors in `blind.jsonl` and `deep.jsonl`: none.
- GPU lock: no lock existed before launch, and the lock file was absent after completion, indicating acquisition and release worked. `Gpu-Status.bat` itself could not import `swarm_forecast` when invoked directly because it does not set the sibling project’s Python path; this was recorded, not fixed during the smoke test.

## Picks

`picks.json` selected market `1284655`, “Will the Republican Party win the RI-01 House seat?”, as a YES gap pick. Blind probability was 0.50 versus a 0.024 YES ask, a +0.476 gap.

## Deep record

The deep pass confirmed the pick with probability **0.95**, based on Rhode Island’s Democratic incumbency and delegation history, while noting the lack of specific RI-01 polling and national-cycle uncertainty. It used 46.8 seconds and returned `error: null`. Full record: `Swarm-Forecast/data/cycles/smoke1/deep.jsonl`.

## Bets

`bets.json` contains one $1.00 paper YES position on market `1284655` at entry price 0.024, probability 0.95, fee 0.00. This was paper accounting only; no trade endpoint was used.

Artifacts: `Swarm-Forecast/data/smoke_pool.jsonl` and `Swarm-Forecast/data/cycles/smoke1/`. The data directory is ignored by Git. The runner v0 commit remains `3a968b3`; no push was made.
