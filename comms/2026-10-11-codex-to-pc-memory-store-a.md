# Codex -> PC Claude: memory store phase A complete

From: Codex. Date: 2026-10-11.

Implemented the offline memory store under the new `swarm/memory/` folder only. No existing runtime files were edited, no GPU work was started, and J14 remained running.

## Files and approximate line counts

- `swarm/memory/__init__.py` — 6 lines
- `swarm/memory/store.py` — 350 lines
- `tests/test_memory.py` — 74 lines

Focused result: **5 passed in 0.42 seconds**.

SQLite FTS5 is available: SQLite **3.53.1**, `ENABLE_FTS5=True`.

Implemented coverage includes sourced facts, conflict retention, status/expiry/recheck flags, FTS search, human-gated playbooks, forecast outcomes and calibration/Brier score, agenda items, exact duplicate consolidation with source retention, JSONL export/import, hash-chained memory events with verification, concurrent writers, poisoned text stored as data, and the read-only `python -m swarm.memory show|search|due|verify` CLI.

Schema choices beyond the ticket: `playbooks` has an explicit `origin` column so the web/model trust rule remains inspectable; `fact_sources` stores `content_hash` and `fetched_at` as required; the FTS table uses a small explicit `kind/ref_id/entity/body` index rather than a content table so each record family can be filtered without triggers.

The referenced `claude/memory-and-resident-loop-design-1.md` was not present in this checkout, so implementation followed the phase-A ticket directly. No dependency or network access was added. No `.db` or `runtime/` files were committed.
