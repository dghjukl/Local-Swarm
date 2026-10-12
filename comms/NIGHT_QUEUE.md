# Night queue (Chris approves this file before bed)
morning_cutoff: 07:00 local
max_items: 6
Order matters. One item at a time. Codex may not add items.

1. status: done   prereq: J14 report exists (artifacts checked) AND GPU lock free
   ticket: comms/2026-10-12-pc-to-codex-forecast-runner-v0-deploy-smoke.md
   what: runner v0 smoke test, 5 non-sports markets, --x 2. Report timings per stage/question, errors, picks and reasons, a deep record, bets, GPU lock behavior.
   stop if: crash with no partial output, or GPU lock misbehaves.

2. status: ready   prereq: item 1 done AND zero errors
   ticket: pilot cycle on data\pilot60 (60 questions). Refresh prices immediately before starting (24 h rule). Do not change config. Same report as item 1 plus score table.
   stop if: any stage error rate above 10%.

(Anything else waits for Chris: M1 tool worker, memory wiring, pushes.)
