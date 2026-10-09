# PC Claude → Codex: J4, resolver test (plan step 4). Start it when Chris passes this ticket to you.

From: PC Claude (cloud). Date: 2026-10-09.

Thanks for J1–J3. The reports were clear and complete. J3 result: the second look raised scores 2–5 points everywhere. Now 8 attempts = 57% and 3 attempts = 60%. Selection is still the weak spot: the oracle is 74%.

## Why this job
In the 8-attempt study the team was "stuck" on 86 of 100 questions: the attempts disagree, or none passed the trust check. On those 86 the coordinator's vote got 43 right, although at least one attempt was right on 60. On the 14 clear questions it got 14/14. J4 tests whether a bigger model, reading the saved research packet, settles the stuck ones better than the vote. No new research or web access is needed.

## Steps
1. `git pull` (or use the shared checkout as is). New files: `swarm/resolver_bench.py`, `tests/test_resolver_bench.py`, `Resolver-Test.bat`.
2. `Run-Tests.bat`. I expect 86 passed, 1 skipped (84 + 2 new). Stop and report if anything fails.
3. `Resolver-Test.bat`. It runs four resolvers one after another into `runtime/evals/resolver-20261009`:
   1. MiMo-9B, thinking. This is a control: the same model as the coordinator, given the packet.
   2. gpt-oss-20b (all on the GPU).
   3. Gemma-4-26B-A4B (about 6 GB from RAM).
   4. Qwen3.6-35B-A3B (about 12 GB from RAM).
   Then it grades everything, with recheck on, and writes `resolver_report.md`.
   - Expect about 5–7 hours. It's safe to stop and restart, because finished questions are kept per model.
   - Nothing else may use the GPU meanwhile.
4. **Watch item 3.4 (Qwen3.6-35B).** With 16 GB of RAM this one is tight. The pool's own RAM guard should refuse rather than crash, but this model once forced two Windows restarts (that was with the workers loaded, which J4 doesn't do).
   - While it runs, check free RAM now and then (Task Manager or `Get-Counter '\Memory\Available MBytes'`).
   - If free RAM stays under ~1 GB, or the PC becomes unresponsive, stop it. Close the window and kill the `llama-server` processes, then run only the grading and compare steps by hand:
     ```
     .venv\Scripts\python.exe -m swarm.evals --regrade runtime/evals/resolver-20261009 --no-open
     .venv\Scripts\python.exe -m swarm.resolver_bench compare runtime/evals/resolver-20261009
     ```
   - Then report how far it got.

## Please report
- Run-Tests counts.
- The table from `resolver_report.md` (per resolver: questions, vote right, resolver right, rescued, broken, average seconds) plus the "by why stuck" lines.
- The Qwen3.6-35B observations: did it load, its seconds per question, the lowest free RAM you saw, any `fit`/offload/error lines in its server log.
- Any errors per resolver (count of rows with an `error`).

Don't commit `runtime/`. The code and bat are committed by PC Claude.
