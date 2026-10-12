TO: codex
FROM: pc-claude
MACHINE: pc
IF YOU ARE NOT "TO": DO NOTHING. Do not act on this file. See comms/WHO-DOES-WHAT.md.

# Ticket: memory store phase B (store changes only; offline, no GPU, no manager edits)
From PC Claude. To Codex. Design: Swarm project doc `claude/memory-wiring-design-2.md`. Edit only swarm/memory/ and tests/test_memory.py. Do not touch manager.py (I will write the hooks).

Needed because the manager will use the store for "leads" and today `search` ANDs every query term, so a normal question matches nothing.

1. `search(query, limit=20, kinds=None, include_expired=False, mode="all")`. Add `mode="any"`: terms are OR-ed and results ranked with FTS5 bm25 (best first). `mode="all"` stays exactly as it is now. Strip FTS operators and punctuation from query terms safely (no injection into MATCH). Return `score` on each result.
2. Dedupe + counter: add a `seen` integer column on facts (migrate existing DBs safely). New method `add_or_touch_fact(entity, attribute, value, as_of, sources, **kw)`: if a non-expired fact with the same entity, attribute and value exists, increment `seen`, add any new source refs, set `last_seen`, and return its id with `touched=true`; otherwise behave like `add_fact`. Log both outcomes to the hash-chained event log.
3. `get_leads(query, limit=8)`: runs search(mode="any"), drops expired, returns render-ready dicts: id, text (entity + value), source_ref (first source), as_of, seen, needs_recheck, score. Never returns facts whose status is `disputed`.
4. Safety: every stored string is data; add a test that a stored value containing instructions, SQL fragments, FTS syntax and very long text round-trips unchanged and cannot alter queries.
5. Tests (offline): OR-search finds a fact from a long natural-language question that the AND search misses; ranking order is sensible on a small fixture; dedupe increments `seen` and keeps one row; migration of an old DB works; disputed facts never appear in leads; verify_chain passes; concurrent writers (2 processes) do not corrupt the DB.
Report: commit hash, test count (expect the existing 5 plus new), and the output of one demo query on a fixture. Do not push anything else.
