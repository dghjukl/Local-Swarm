# Night loop v2 (supersedes the roles/stop sections of night-loop.md)

## Roles
- PC Claude decides and queues the next APPROVED work, then Codex executes it and reports evidence.
- Claude checks comms/ on its own interval. It writes the next instruction only into NIGHT_QUEUE.md (one named item at a time) or a clearly named ticket. It stays quiet when nothing changed. It writes only on: a completion, a failure, a next action, or a request for Chris.
- Claude queues only from the menu Chris approved in NIGHT_QUEUE.md (or one retry of a failed step). Core code changes, pushes and new kinds of action wait for Chris.
- Codex owns: detecting job completion, writing result reports, marking prerequisites done. Codex never invents queue items.
- Claude treats a ticket as complete only when Codex's report explicitly says so, with evidence paths.
- Queue edits are atomic (write temp file, rename) and touch only the named item.

## J14 completion
Detect from run artifacts, not from a missing process: the J14 results files for all 126 runs exist (done.json per question or the final results file) AND the J14 report file is written. State which artifacts you checked in the report.

## Smoke test gate
Item 1 stays blocked until BOTH: the J14 report exists AND the GPU lock is free. Re-check each cycle; do not wait in a loop.

## Loop ends when ANY of
- queue exhausted (no ready items)
- six items run
- two consecutive failures
- comms/STOP exists
- a test regression
- 07:00 local morning cutoff (Chris may edit this time in NIGHT_QUEUE.md header)
On end: write comms/night-summary.md, disable the schedule.
