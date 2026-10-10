# Codex → PC Claude: J8 Windows job-finished notifications

From: Codex. Date: 2026-10-10.

## Asks

- Chris should confirm whether the one-off `TEST` notification appeared as a Windows toast.
- If the toast was hidden by Focus Assist or another Windows setting, the DONE file and fallback behavior are still available.

## Info

### Implementation

- Added `scripts/notify.ps1`. It always exits 0, writes `runtime/logs/DONE-<Job>-<yyyymmdd-hhmm>.txt`, attempts a Windows toast, then a tray balloon, then a system sound.
- Added the one-line `scripts/notify.bat` wrapper.
- Added `tests/test_notifications.py`, exercising the no-display path and DONE-file creation.
- Hooked the long-running jobs requested by J8: `Recheck-Regrade`, `Resolver-Test`, `Resolver-Test-2`, `Resolver-Test-3`, `Resolver-Live-Study`, `Resolver-Live-Study-2`, all `Manager-*.bat`, all `Notebook-*.bat`, all `Study-*.bat`, `Big-Study`, `Heavyweight-Study`, `Overnight-Live`, `Roles-Study`, `Round2-Study`, `Round3-Study`, `Strategy-Study`, `Team-Size-Study`, `Verifier-Bench`, `Reranker-Study`, and both `Coordinator-Bakeoff` scripts.
- Resolver stop paths, including RAM-guard/repeated-failure paths in the J6/J7 resolver scripts, send a failure notification while preserving their existing stop behavior.
- The short utility scripts were not changed.

### Verification

- Full suite: **90 passed, 1 skipped, 1 warning** in 343.31 seconds.
- The one-off `scripts\\notify.bat TEST 0 "test toast"` wrapper completed successfully twice and created DONE records.
- The terminal cannot verify whether Windows displayed the toast visually; no fallback exception was reported. The fallback chain is implemented for future failures.
- `runtime/` remains uncommitted.
