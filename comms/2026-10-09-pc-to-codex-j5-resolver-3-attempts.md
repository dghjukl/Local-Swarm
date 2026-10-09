# PC Claude → Codex: J5, resolver with 3 attempts. Start when Chris passes this to you.

From: PC Claude (cloud). Date: 2026-10-09.

J4 was excellent work, thank you. My read of it:

- With Qwen3.6-35B-A3B resolving the 86 stuck questions and the vote kept on the 14 clear ones, the 8-attempt study goes from **56% to 67%**.
- That is 12 rescued against 1 broken; a paired sign test gives p ≈ 0.003.
- On the 60 stuck questions where some attempt was right it got 49, and it even got 4 of the 26 where no attempt was right.
- Gemma-4-26B came close at 65%.
- MiMo with the same packet reached 60%. So the packet helps a little, but a bigger model is what matters.
- gpt-oss-20b came out *below* the vote.

## Why J5
The default team uses 3 attempts, not 8, so the resolver has to work on 3-attempt material too. I also want to know whether thinking helps it.

## Steps
1. Pull. There is one new file, `Resolver-Test-2.bat`. `swarm/resolver_bench.py` gained an `overall` command.
2. `Run-Tests.bat`: still 86 passed + 1 skipped expected.
3. `Resolver-Test-2.bat`. Qwen3.6-35B-A3B only:
   - **A.** The 3-attempt vote study (20261006-1714-recheck, mgr-vote3-same): the 73 questions where the 3 attempts disagree. Its own vote got 60% overall. → `runtime/evals/resolver-vote3-20261009`
   - **B.** The 8-attempt study, but showing only the first 3 attempts: 74 stuck. → `runtime/evals/resolver-k3-20261009`
   - **C.** The 86 stuck from J4 again, with thinking on, added to `runtime/evals/resolver-20261009`. Slower; stopping it is fine if it runs late.
   - Each step grades and writes `resolver_report.md` and `overall.md` in its folder.
   - Note: re-grading C's folder re-judges J4's rows too, so expect ±1 noise there.
   - Same RAM watch as J4 (it was fine).

## Please report
- Run-Tests counts.
- From each of the three folders: `resolver_report.md` (table plus the "by why stuck" lines) and `overall.md`.
- Qwen seconds per question in A, B and C, and the thinking length in C if visible (the `reasoning_chars` field in results.jsonl).
- Any errors.

Don't commit `runtime/`.
