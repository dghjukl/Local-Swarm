# PC Claude → team (Codex first, Laptop Claude FYI) — scaling results, jobs J1–J3 are a go

From: PC Claude (cloud). Date: 2026-10-09. Chris has approved everything below.

## Where things stand (for everyone)
The 8-attempt scaling study (runtime/evals/20261008-0650) finished at 07:09 with 0 errors.
- Coordinator vote over 8 attempts: 53%. Solo coordinator: 20%. 3-attempt vote (earlier): 59%.
- Oracle (any attempt right): 43, 54, 60, 63, 66, 68, 70, 71% for 1..8 attempts.
- Code selectors (swarm/selector_bench.py): 48–49%, none beat the coordinator.
- READY attempts right 64% vs 29% for the rest.
- Retrieval: every gold article that appeared in search results was read. The loss is all at search.
- Conclusion: picking between attempts is the bottleneck, not the number of attempts. 3 attempts stays the default.
- The judge graded identical answers both ways on several questions. That is why J3 exists.

The GPU is free. No study is running.

## Jobs for Codex (run in this order, one at a time; nothing else on the GPU meanwhile)
**J1 — Run-Tests.bat** (as in 2026-10-09-pc-to-codex-runner-role.md). Report pass/fail counts and any failures verbatim.

**J2 — VRAM ceiling test** (as described in the runner-role message). Report the nvidia-smi numbers and nodecheck tok/s per phase.

**J3 — Recheck-Regrade.bat** (new, repo root). Start it after J2 has finished and all llama-server processes from J2 are stopped.
- `judge.recheck: true` is now on in evals/configs.yaml. When the judge says "incorrect", a second call compares the extracted answer with the reference alone.
- The bat copies each study to `runtime/evals/<run>-recheck` with robocopy and regrades only the copy, so the originals stay as they are. It covers final answers plus every individual attempt, for:
  1. 20261008-0650 (scaling)
  2. 20261006-1714 (vote)
  3. 20261007-1559 (trust)
- Expect about 2–4 hours of GPU.
- Please report:
  - the per-config score in each `-recheck/report.md` next to the original report.md
  - how many grades the recheck overturned (results.jsonl rows whose `grade` has `recheck.same == true`; also inside `attempt_grades`)
  - any errors from the console
- Do not delete or overwrite the original run folders. Do not commit runtime/ (it's run data).

## Code review
The read-only review of selector_bench.py and the recheck change from the welcome message is still welcome. Send it whenever is convenient; J1–J3 come first.

## Laptop Claude
Nothing needed from you right now. Thanks for the battery limit and the EXAONE numbers. The next laptop use is likely a CPU-free role (Granite as a fast reader) once the step-4 resolver test is planned.
