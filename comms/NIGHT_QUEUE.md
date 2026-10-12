# Night queue (Chris approves this file before bed)
morning_cutoff: 07:00 local
max_items: 6
Order matters. One item at a time. Codex may not add items.

1. status: done   prereq: J14 report exists (artifacts checked) AND GPU lock free
   ticket: comms/2026-10-12-pc-to-codex-forecast-runner-v0-deploy-smoke.md
   what: runner v0 smoke test, 5 non-sports markets, --x 2. Report timings per stage/question, errors, picks and reasons, a deep record, bets, GPU lock behavior.
   stop if: crash with no partial output, or GPU lock misbehaves.

2. status: done   prereq: item 1 done AND zero errors
   ticket: pilot cycle on data\pilot60 (60 questions). Refresh prices immediately before starting (24 h rule). Do not change config. Same report as item 1 plus score table.
   stop if: any stage error rate above 10%.

3. status: blocked   prereq: item 2 done (report written)
   ticket: comms/2026-10-12-pc-to-codex-forecast-defects-diagnose.md
   what: READ-ONLY diagnosis of two defects found in smoke1 (probability 0.95 contradicts the swarm's own ~20% estimate; many blind forecasts default to exactly 0.5 on empty research). No code or config changes.
   stop if: it would require editing code/config or rerunning the model.

(Anything else waits for Chris: M1 tool worker, memory wiring, pushes.)
