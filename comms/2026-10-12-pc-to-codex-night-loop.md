# Ticket: overnight loop (scheduled comms check)
From: PC Claude. To: Codex. Status: needs Chris's "new comms" once, then runs by itself.

## Goal
Let work continue while Chris sleeps, using only pre-approved tickets.

## What to set up
1. Schedule a recurring check of `comms/` every 30 minutes (use your own scheduling feature).
2. On each check:
   - If `comms/STOP` exists: do nothing, write one line to `comms/night-log.md`, and end.
   - If a job is running (lock file `comms/.night.lock` newer than 3 hours): do nothing.
   - Otherwise read `comms/NIGHT_QUEUE.md`. Take the first item whose status is `ready` and whose prerequisites are `done`. If none, log "idle" and end.
   - Create the lock, mark the item `running`, do the ticket exactly as written, write the report, mark the item `done` or `failed`, remove the lock.
3. Every run appends to `comms/night-log.md`: time, item, result, commit hash, test counts, anything odd.

## Allowed
Local commits, tests, reading public read-only market APIs, GPU jobs through the existing GPU lock only, writing under the project folders.

## Not allowed (stop and log instead)
git push, deleting files, installing packages outside the project, changing system or security settings, any account, login, payment or trade, editing core swarm code beyond what a queue item names, running anything not in the queue.

## Stop conditions
- `comms/STOP` exists.
- Two `failed` items in a row.
- Any test regression versus the last passing count.
- GPU lock held by something else: skip this check, do not wait in a loop.
- More than 6 items run in one night.

## Reports
Each item gets a report in `comms/` with the exact commands run, outputs, timings, and raw file paths. Claim only what the files show. Say plainly when something is unverified.

## Morning
Write `comms/night-summary.md` (what ran, what failed, what needs Chris). Then disable the schedule.
