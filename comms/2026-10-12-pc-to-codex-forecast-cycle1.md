# Ticket (queue item): forecast cycle 1, exploration (NOT the frozen capstone)
From PC Claude. To Codex. Prereq: the fix-0 branch is merged into Swarm-Forecast main, tests pass, and tagged `forecast-0.1`. Chris has approved (message "Yes let's do it") the plan: first real cycle, labeled exploration.

## Steps
1. Sample 300 questions with the Phase 0e stratified sampler (seed recorded, categories and clusters capped as already configured). Refresh prices for all selected markets immediately before the run (24 h rule). Drop stale ones and replace from the reserve.
2. `python -m swarm_forecast cycle --pool <file> --out data\cycles\cycle1 --mode gap --x 30` with config unchanged from tag forecast-0.1. Record the swarm commit and forecast-0.1 in meta.json.
3. GPU lock, one job, resumable. Expected about 2.1 h blind + 40 min deep.
4. Report: counts (blind, no_forecast, inconsistent, stale_suspect), timing by stage, picks with reasons (top 10 and a random 10), deep confirmations, bets and the bet-side distribution, the bet price distribution (how many under $0.50), clusters. Include a table of the first picks next to their market asks.
Do not score (no outcomes yet). Schedule `score` for 7, 14 and 21 days after the cycle using the outcomes API pull; write the dates in the report.
