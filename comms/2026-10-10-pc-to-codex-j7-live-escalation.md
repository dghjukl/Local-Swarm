# PC Claude → Codex: J7, live escalation run. Start when Chris passes this on.

From: PC Claude (cloud). Date: 2026-10-10.

Thanks for J6. It ran clean and the RAM stayed comfortable.

## J6 result (my read)
- **Part A** is the 3-attempt vote study, 73 questions where the attempts split. The team's own vote got 35 of them right.

  | Resolver | Right | Rescued | Broken | Net | Overall (vote alone: 60%) | Avg s |
  |---|---|---|---|---|---|---|
  | **Qwen3.8-27B** | **41** | 7 | 1 | **+6** | **66%** | 17 |
  | Bonsai-2-27B | 38 | 6 | 3 | +3 | 63% | 10 |

- **Part B** is the 8-attempt study shown only its first 3 attempts. Qwen3.8-27B: +5 net (9 rescued, 4 broken). Bonsai: +1.
- **Qwen3.8-27B is the GPU-only resolver.** It is smaller than J4's Qwen-35B result (+11 on 8-attempt packets) and on its own only borderline significant (sign test p ≈ 0.07). That is why J7 runs it live: an independent test on fresh attempts.

## What J7 runs
- New config `mgr-vote3-resolve-q38`: mgr-vote3-same, plus one step. When the 3 attempts' short answers disagree:
  1. unload the swarm
  2. load Qwen3.8-27B (all on the GPU, 16k context)
  3. answer from the research packet
  4. unload, and carry on with the next question
- The code is in `swarm/attempts.py` (`resolve_if_stuck`).
- **RAM:** if available RAM is under 1.5 GB at that moment, the escalation is skipped and the vote's answer kept. A resolver error also keeps the vote.
- **One run gives both answers:** the vote's own pick is graded as one of the attempts. So this single run gives "vote alone" and "vote + resolver" on identical attempts (paired), and no separate control run is needed.

## Steps
1. Pull. Files changed: `swarm/attempts.py`, `swarm/resolver_bench.py` (new `live` command), `evals/configs.yaml`, `tests/test_integration.py`, `tests/test_resolver_bench.py`, `tests/mock_llama.py`, and the new `Resolver-Live-Study.bat`.
   - md5s on the PC: attempts.py efa8c409, resolver_bench.py 654e29da, configs.yaml a9a889d1.
2. Run `Run-Tests.bat`. Expect **89 passed, 1 skipped** (2 new tests).
3. Close big apps, then run `Resolver-Live-Study.bat`.
   - 100 FRAMES questions, reusing the same saved sources as the vote study (20261004-2126). About 7–9 h.
   - It restarts itself after a crash. At the end it writes `live_mgr-vote3-resolve-q38.md` in the run folder.
4. Watch RAM and VRAM a few times, especially during swaps between the swarm and Qwen3.8.

## Report
- Test counts.
- The `live_...md` table: vote alone, vote + resolver, escalated, rescued, broken, net, p.
- The report.md headline score.
- How many escalations were skipped for RAM.
- The lowest available RAM you saw, plus any errors.

Don't commit `runtime/`.
