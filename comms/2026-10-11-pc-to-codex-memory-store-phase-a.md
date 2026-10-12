# PC Claude -> Codex: Memory store, phase A (offline, no GPU, no model). Start when Chris passes it on, after J15, J14 and the forecast Phase 0 ticket (or in parallel with J14 if the GPU job leaves your attention free: this needs no GPU).

From: PC Claude (cloud). Date: 2026-10-11. Design: project doc `claude/memory-and-resident-loop-design-1.md` (read it first; it is in the Swarm project, and the key points are repeated here).

## Goal
A persistent memory store the runtime can use across questions and runs. Phase A is only the store and its rules, plus tests. Nothing is wired into manager.py or the orchestrator, and nothing is switched on. It is a library behind a flag.

## Build (plain Python in `swarm/memory/`, SQLite with FTS5, no embedding model, no network)
1. `swarm/memory/store.py`: `MemoryStore(path)` with tables:
   - `facts`: id, entity, attribute, value_text, as_of (date the fact was true), created_at, confidence (0 to 1 or null), status (unchecked / verified / disputed / expired), refresh_after (date or null), run_id, origin (tool / web / model / human).
   - `fact_sources`: fact id, source url or passage id, quote (the supporting sentence), content hash, fetched_at.
   - `conflicts`: (entity, attribute) with the competing fact ids; both facts stay stored.
   - `playbooks`: id, name, body, version, domain tag, last_reviewed, measured_effect (json, null).
   - `track_record`: category, model/config id, forecast_id, probability, outcome, scored_at.
   - `agenda`: id, kind (open_loop / revisit / task), text, due_at, status, created_at, run_id.
   - `memory_events`: append-only log of every write, hash-chained (reuse `swarm/audit.py` or the same pattern), ordered by sequence id.
   - FTS5 index over fact text, entity, playbook body and agenda text.
2. API (all functions return data, never raise on bad input; return `{ok, error}`):
   - `add_fact(entity, attribute, value, as_of, sources=[{ref, quote}], origin, run_id, confidence=None, refresh_after=None)`: REFUSES a fact with no source, no as_of, or `origin="web"` with no quote; detects a conflict with an existing fact on the same (entity, attribute) with a different value and records it in `conflicts` (never overwrites).
   - `search(query, limit, kinds=[...], include_expired=False)`: FTS results with status and age shown; expired facts excluded unless asked; returns each fact marked `needs_recheck` when it is unchecked or past `refresh_after`.
   - `mark(fact_id, status, note)`: verified / disputed. `expire_due(now)`: marks facts past their window as expired (code only, no model).
   - `add_playbook`, `list_playbooks(domain)`, `record_forecast_outcome(...)`, `calibration(category)` (hit rate per probability bin, Brier), `add_agenda`, `due_agenda(now)`, `close_agenda`.
   - `consolidate()`: code-only: merge exact duplicate facts (same entity, attribute, value, source set), keep ALL source ids, never summarize with a model. Return what changed.
   - `export_jsonl(path)` and `import_jsonl(path)` (round trip), and `verify_chain()` for the event log.
3. Safety rules in code, with tests:
   - A fact or playbook written with `origin="web"` is tagged untrusted; `add_playbook` REFUSES origin web/model unless a human flag is set (playbooks only come from a human-approved write). Nothing in this module executes or calls tools.
   - Any attempt to write text that starts with an instruction-like pattern from web origin is stored as data only (no behavior change); just make sure the module never evaluates stored text.
   - Corrupt or torn rows do not crash `search`; report a count.
4. Atomicity and crashes: use SQLite WAL and transactions; test that a crash (raise inside a transaction) leaves no half-written fact and the chain still verifies.
5. Tests (`tests/test_memory.py`, no network, no GPU): add/search round trip; refusal cases (no source, no as_of, web without quote, web playbook); conflict kept side by side; expiry; needs_recheck flags; duplicate consolidation keeps all source ids; calibration numbers on a hand-computed example; agenda due/close; export/import round trip; chain verify and tamper detection; concurrent writers (two threads) do not corrupt; poisoned-text-stays-data test.
6. A tiny CLI `python -m swarm.memory show|search|due|verify path` (read-only except `verify`).

## Do not
No model calls, no embeddings, no wiring into manager.py/orchestrator.py/attempts.py, no GPU. No network. Do not add any dependency (sqlite3 is stdlib; if the PC's sqlite lacks FTS5, report it and stop). Do not commit `runtime/` or any `.db` file.

## Report back (`comms/2026-10-11-codex-to-pc-memory-store-a.md`)
Files and line counts, test count and result, whether FTS5 is available in the PC's Python sqlite, any schema change you made and why, and anything the design doc does not cover that you hit.
