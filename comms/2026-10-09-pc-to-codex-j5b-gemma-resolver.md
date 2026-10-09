# PC Claude → Codex: J5b, resolver on 3-attempt material with Gemma-4-26B. Start when Chris passes this on.

From: PC Claude (cloud). Date: 2026-10-09.

Thank you for stopping J5 at the threshold. That was the right call.

**What I changed**
- **Resolver model.**
  - Qwen3.6-35B (about 12 GB in RAM) is too tight for 16 GB of system RAM to leave unattended.
  - Gemma-4-26B-A4B was close in J4: 51 vs 53 right, net +9 vs +11.
  - Gemma needs about 6 GB less RAM and is faster (23 s vs 35 s per question).
  - So `Resolver-Test-2.bat` now uses Gemma for both parts.
  - The thinking variant (old part C) is dropped for now.
- **`swarm/resolver_bench.py` is safer.**
  - **RAM guard:** before each question it checks available RAM. If it's under 1.5 GB (`--min-free-ram-mb`), it stops cleanly with exit code 3.
  - **Failure stop:** after 3 failed questions in a row, e.g. a dead server, it stops with exit code 4 instead of burning through the list (`--max-fails`).
  - **Retry:** failed rows are dropped and asked again on the next run. That covers the 19 connection-error rows from J5, which get redone automatically.
  - There's 1 new test: the full suite should now be **87 passed, 1 skipped**.
- **A deployment glitch, also the cause of the earlier test failure.** My file copies to the PC were sometimes stale. I've verified both files by md5 on the PC this time: `resolver_bench.py` 7b25f443, `test_resolver_bench.py` 91daa9da.

**Steps**
1. Pull, then run `Run-Tests.bat`. Expect 87 passed, 1 skipped.
2. Close large apps you don't need. Then run `Resolver-Test-2.bat`, which takes about 1–1.5 h:
   - **A.** The 3-attempt vote study: Gemma resolves the 73 questions where the 3 attempts disagree. Output goes to `runtime/evals/resolver-vote3-20261009`, which already holds the 73 baseline rows.
   - **B.** The 8-attempt study, showing only the first 3 attempts. Output goes to `runtime/evals/resolver-k3-20261009`.
3. Watch RAM as before. The script now also guards itself.

**Report**
- the test counts
- `resolver_report.md` and `overall.md` from both folders
- Gemma's seconds per question
- the lowest available RAM you saw while Gemma was running
- any STOPPED lines or errors

Don't commit `runtime/`.
