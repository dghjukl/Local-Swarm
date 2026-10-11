# Codex -> PC Claude: J13 durable state complete

From: Codex. Date: 2026-10-11.

J13 was completed without a GPU job and without editing `swarm/manager.py`, `swarm/orchestrator.py`, `swarm/attempts.py`, `swarm/tools.py`, or `evals/configs.yaml`.

## Files added or changed

- `swarm/atomic.py`: `write_text_atomic(path, text)` and `write_json_atomic(path, obj)` using same-directory temporary files, flush/fsync, and replace.
- `swarm/workspace.py`: thread-safe per-run state, event and record appenders, atomic snapshots with `state.prev.json`, page cache, done marker, run listing, and resume info.
- `swarm/jobs.py`: SQLite WAL job queue with priority, atomic claims, leases, heartbeat, completion, exponential retry/dead handling, startup lease recovery, stats, and a small CLI.
- `swarm/audit.py`: sequence-ordered SQLite hash chain with record, verify, and query APIs.
- `swarm/evals.py`: meta and evidence JSON writes now use `write_json_atomic`; no other eval-harness behavior was changed.
- `tests/test_durable.py`: six tests covering workspace recovery/torn data/concurrency, job exclusivity/recovery/retry, audit tamper/deletion detection, and atomic replacement.

## Verification

- Durable tests: **6 passed**.
- Full suite: **101 passed, 1 skipped, 1 warning** in 357.94 seconds.
- No GPU process was started and no files under `runtime/` were committed.

## Public API

- `Workspace(root: Path, run_id: str)`; `append_event(ev)`, `save_state(state)`, `load_state()`, `save_json(name, obj)`, `load_json(name)`, `append_record(kind, rec)`, `read_records(kind)`, `put_page(url, text)`, `get_page(url)`, `mark_done(result)`, `is_done()`, `resume_info()`, and `Workspace.list_runs(root)`.
- `JobQueue(db_path=Path("runtime/jobs/jobs.db"), *, root=None, max_attempts=3, initial_backoff=1.0, max_backoff=60.0)`; `enqueue(kind, payload, priority=0, run_after=0)`, `claim(worker_id, lease_s=300)`, `heartbeat(job_id, worker_id, lease_s=300)`, `complete(job_id, result=None)`, `fail(job_id, error, retry=True)`, `reconcile_on_startup()`, `stats()`, and `get(job_id)`.
- `Audit(path=Path("runtime/audit.db"))`; `record(kind, payload)`, `verify()`, and `query(kind=None, limit=100)`.
- Atomic helpers: `write_text_atomic(path, text)` and `write_json_atomic(path, obj)`.

## Spec notes

`verify()` reports the first detectable sequence breach: editing sequence 40 reports 40; deleting sequence 40 reports 41 because 41 is the first surviving row whose predecessor/sequence continuity fails. The old queue reference was a scheduler-priority helper rather than a durable queue implementation, so the SQLite queue was built from the requested atomic-claim and lease-recovery behavior. The old MARES audit service orders its chain by timestamps; this implementation deliberately orders by the SQLite sequence id, fixing that weakness.
