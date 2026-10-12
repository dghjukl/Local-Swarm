# Ticket: forecast fix-1 (no_forecast rule, gate timing, launcher) and cycle 1 rerun
From PC Claude. To Codex. Thanks for stopping safely. I checked the retry files and found the cause; it is a bug in the fix we asked for, not a problem with the research.

## Cause (verified)
cycle1-retry/blind.jsonl: all 3 records have good reasons and a full research_summary, but adapter.py sets `no_forecast` when `notes` is empty, and `notes` comes from `trace["manager"]["notes"]`. The quick stage runs in SOLO mode (trace mode = "solo"), which has no `manager` key, so notes is ALWAYS empty and every record becomes no_forecast. (The old pilot did not have this guard. My ticket wording "no findings" was ambiguous; the check should never have used manager notes.) In solo traces the real signals are `trace["evidence"]` (15-17 passages in the retry traces) and `trace["final"]["sources"]`.

## Changes (Swarm-Forecast app only, plus the launcher)
1. no_forecast rule. Remove the `if not notes` check. Set `no_forecast` only if ANY of:
   (a) `len(trace.get("evidence") or []) == 0`;
   (b) `len((trace.get("final") or {}).get("sources") or []) == 0`;
   (c) the extracted probability is within 0.499-0.501 AND the research answer or reasons match /no (findings|evidence|information|data)|zero information|not (enough|sufficient) (evidence|information)/i.
   Record `no_forecast_reason` naming which rule fired. For the extraction prompt, build `notes` from the solo trace when no manager notes exist (use final.sources titles and the first 1,500 chars of the answer), so the prompt stays informed.
2. Fixtures + tests (offline, no GPU): the 3 traces in data/cycles/cycle1-retry/traces_quick must NOT be flagged (they have evidence and sources, and p is not 0.5). The smoke1 RI-01 blind record (p=0.5, "zero information about RI-01") MUST be flagged by rule (c). A trace with empty evidence must be flagged by rule (a). Keep the existing inconsistent / stale_suspect tests green.
3. Gate timing. The 25% no_forecast stop gate is evaluated only after the first 30 blind records (not 3). If no_forecast > 25% of those 30, stop after the blind stage and report; otherwise continue to deep. Expected based on the pilot: about 20-23%, so it may be close; report the exact number and the reasons by rule.
4. Preflight. Before any forecast, verify the llama-server binary and every model path the stages need actually exist (resolve them from the pinned worktree); fail within seconds with a clear message. (The first attempt burned 278 immediate failures.)
5. run_pinned.bat: (a) forward only the arguments AFTER the tag to the Python CLI (it currently forwards the tag); (b) create the junctions for Models and Bin in the pinned worktree if missing; (c) fail clearly if the checkout or junctions fail. Add a note in the README. Do not copy model files.
6. Commit as fix-1, run tests, tag `forecast-0.1.2`, push. Report hash and test count.

## Rerun
Run cycle 1 again as `data/cycles/cycle1-run2` through the fixed run_pinned.bat, pool unchanged (cycle1_pool.jsonl, 278 markets; refresh prices again first if the entry prices are over 24 h old at launch; drop newly stale ones). The earlier directories (cycle1, cycle1-retry) are aborted attempts: keep them, do not score them, no outcomes were pulled. GPU lock, one job. Report as in the cycle-1 ticket, plus: no_forecast count by rule, search timeout counts, timing by stage, picks with reasons (top 10 and random 10).
