# PC Claude -> Codex: J13, durable state modules (workspace, job queue, audit chain, atomic writes). No GPU. Start when Chris passes this on.

From: PC Claude (cloud). Date: 2026-10-11.

Context: Chris wants a real runtime around the swarm's agent loop (plan: Claude project doc `runtime-plan-draft-1.md`; summary below). Milestone M2 is "durable state": a question that dies from a power flicker must resume at the turn it stopped, and every tool call and result must be recorded. I am building M0 (tool layer) in the same files area in parallel, so **do not edit `swarm/manager.py`, `swarm/orchestrator.py`, `swarm/attempts.py`, `swarm/tools.py` or `evals/configs.yaml`**. Write only NEW modules plus their tests, and the small `evals.py` change in item 4. I will wire them into manager.py afterwards.

## Build (all standard library; Python 3.13; no new dependencies)

### 1. `swarm/workspace.py`: per-run workspace on disk
`Workspace(root: Path, run_id: str)` creating `root/<run_id>/`. API (sync, thread-safe with a lock):
- `append_event(ev: dict)`: append one JSON line to `events.jsonl`, flush and `os.fsync`.
- `save_state(state: dict)`: atomic write to `state.json` (write tmp in the same folder, fsync, `os.replace`), with an increasing `seq` and `saved_at` inside. Keep the previous one as `state.prev.json`.
- `load_state() -> dict | None`: read `state.json`; if it is missing or torn, fall back to `state.prev.json`.
- `save_json(name, obj)` / `load_json(name)`: atomic named files (for notebook.json, plan.json...).
- `append_record(kind, rec)` for `tool_calls.jsonl`, `passages.jsonl`, `notes.jsonl`: JSON lines, flushed.
- `read_records(kind) -> list[dict]`: tolerate a torn last line (skip it, count it in `self.torn`).
- `put_page(url, text)` / `get_page(url)`: page-text cache keyed by sha256(url) under `pages/`, atomic.
- `mark_done(result: dict)` writes `done.json`; `is_done()`.
- `list_runs(root)`: run ids with state and whether done, newest first.
Provide `Workspace.resume_info()` returning `{run_id, seq, cycle (from state), done, torn}`.

### 2. `swarm/jobs.py`: durable job queue
Port the idea of `GitHub2/Agent/src/staff_runtime/queue.py` (67 lines, atomic claim) plus lease recovery from `GitHub/NULL.Prime/ember/slices/job_task_execution/recovery.py`, `retry.py`, `state_machine.py` (read them on the PC; do not copy code you don't understand). SQLite in WAL mode, `runtime/jobs/jobs.db`.
- States: queued, running, done, failed, dead.
- `enqueue(kind, payload, priority=0, run_after=0) -> id`; `claim(worker_id, lease_s=300)` atomic (single UPDATE ... WHERE id=(SELECT ...)); `heartbeat(id, worker_id)`; `complete(id, result)`; `fail(id, error, retry=True)` with exponential backoff and `max_attempts` (then `dead`); `reconcile_on_startup()` re-queues `running` jobs whose lease expired; `stats()`.
- Include a tiny `python -m swarm.jobs` CLI: `enqueue`, `list`, `reconcile`.

### 3. `swarm/audit.py`: hash-chained append-only log
Port the idea of `GitHub/MARES/mar/src/mar/audit/service.py` (99 lines). **Fix its weakness:** order the chain by an autoincrement sequence id, not by timestamp. SQLite file `runtime/audit.db`. `Audit(path).record(kind, payload: dict) -> id`, `verify() -> {intact, records, first_breach}`, `query(kind=None, limit=100)`. Each record's hash covers the canonical JSON of (seq, ts, kind, payload, prev_hash). No row limit in `verify`.

### 4. Atomic writes in the eval harness
In `swarm/evals.py` make `meta.json` and `evidence/<qid>.json` writes atomic (tmp + fsync + replace) using a shared helper `swarm/atomic.py: write_text_atomic(path, text)` and `write_json_atomic`. Do not change anything else in evals.py. Also use the helper inside `workspace.py`.

## Tests (new `tests/test_durable.py`)
- workspace: round trip; torn last line in each jsonl; torn `state.json` falls back to `state.prev.json`; simulated crash between tmp write and replace leaves the old state intact; concurrent writers from 4 threads produce valid lines.
- jobs: claim is exclusive with 8 threads; expired lease gets re-queued by `reconcile_on_startup`; retry backoff then `dead`; heartbeat extends a lease.
- audit: `verify()` is intact after 200 records; editing one payload in the DB makes `verify()` report the right `first_breach`; deleting a middle row is detected.
- atomic: `write_text_atomic` never leaves a partial file when the process is killed (simulate by raising between steps).
Run the full suite after; all existing tests must still pass.

## Report back (`comms/2026-10-11-codex-to-pc-j13-durable.md`)
Files added, test results, the exact public API (signatures) as built, anything you changed from the spec and why, and anything in the old projects' code that surprised you (bugs, stubs). Commit as usual; do not commit `runtime/`.

## Do not
Do not wire these into manager/orchestrator/attempts. Do not start any GPU job. Do not add dependencies.
