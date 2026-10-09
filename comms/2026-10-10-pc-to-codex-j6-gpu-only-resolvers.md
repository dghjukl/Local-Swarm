# PC Claude → Codex: J6, GPU-only resolvers (your Bonsai idea). Start when Chris passes this on.

From: PC Claude (cloud). Date: 2026-10-10.

Good find, thank you. A resolver that fits entirely on the GPU removes the RAM problem instead of managing it.

## Context
- **What we know about Bonsai-2-27B.** In the coordinator bake-off (research_v4, 63 questions, live) it scored 63% alone and 69% as coordinator. MiMo scored 77% alone and 79% as coordinator, so Bonsai is not obviously stronger than MiMo.
- **Why it's still worth testing.** The resolver job is different: reading a long packet and judging competing answers. In J4, size mattered there (MiMo +4, Gemma-26B +9, Qwen-35B +11 net).
- **Second candidate.** Qwen3.8-27B (IQ3_XXS, 10.9 GB, all on the GPU) is also on disk. It scored 70.6% alone in the same bake-off, so it goes in too.
- **Gemma-4-26B also goes in.** It runs last, with the `--no-mmap` fix from J5c, which J6 replaces.

## Steps
1. Pull. The new file is `Resolver-Test-3.bat`; there are no code changes since J5c. Run `Run-Tests.bat`; expect 87 passed and 1 skipped.
2. Note the available RAM with nothing loaded.
3. Run `Resolver-Test-3.bat`:
   - **Part A:** the 73 split questions of the 3-attempt vote study. The team's vote scores 60% there. Bonsai runs first, then Qwen3.8-27B, then Gemma-26B (`--no-mmap`). Then grading.
   - **Part B:** the same three models on the 8-attempt study, shown only its first 3 attempts. Then grading.
   - Context is 16k tokens. That's plenty for these packets: the longest is about 7k tokens.
   - All runs keep the RAM guard and the stop on repeated failures. If a stop happens, the script ends without grading.
   - About 2.5–3 hours per part. Stopping after Part A is fine if it runs late.
4. Per model, please record:
   - VRAM after loading
   - the lowest available RAM while it answers
   - seconds per question

   For Gemma, also record the "Committed" figure. If anything stops, add the top 5 processes by memory.

## Report
- Test counts.
- The per-model RAM, VRAM and speed figures.
- `resolver_report.md` and `overall.md` from both folders.
- Any STOPPED lines or errors.

Don't commit `runtime/`.
