# PC Claude → Codex: J6 continues without Gemma. Start when Chris passes this on.

From: PC Claude (cloud). Date: 2026-10-10.

Thanks. A clean stop again, and Bonsai and Qwen3.8 both finished 73/73. Median time per question: Bonsai 9 s, Qwen3.8 12 s.

**Decision: Gemma-4-26B is out for this PC.**
- Even with `--no-mmap`, it took available RAM to 1.36 GB.
- That is real use now, not a misleading reading.
- It is too thin a margin for unattended runs on 16 GB.
- From here on, only models that fit fully on the GPU are resolver candidates.

**Changes**
- `Resolver-Test-3.bat` now runs only `Bonsai-2-27B Qwen3.8-27B` (the `MODELS` variable near the top).
- I cleaned `runtime/evals/resolver-vote3-20261009`:
  - Removed the 19 Qwen3.6-35B connection-error rows from J5, and the Gemma entry (no answers), from `results.jsonl` and `meta.json`.
  - Backups: `results.before-cleanup.jsonl` and `meta.before-cleanup.json`.
  - That leaves 73 baseline rows plus 73 each for Bonsai and Qwen3.8.

**Steps**
1. Pull, then run `Resolver-Test-3.bat` again.
   - Part A finds both models already done.
   - It goes straight to grading Part A, then runs Part B for both models and grades it.
   - Expect about 1–1.5 h.
2. No tests needed (no code changes). Same RAM watch as before.

**Report:** `resolver_report.md` and `overall.md` from both folders, plus any STOPPED lines.

Don't commit `runtime/`.
