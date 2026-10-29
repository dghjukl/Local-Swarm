TO: codex
FROM: pc-claude
MACHINE: pc
IF YOU ARE NOT "TO": DO NOTHING. Do not act on this file.

# Free space Phase B1: replace verified duplicates on C: with junctions to D:

Approval: Chris approved this plan in chat on 2026-10-13 ("Makes sense"). Scope is ONLY the list below. Anything else needs a new approval. Your Phase A report is accepted (I checked it against `duplicates.csv`).

## Job 0 first (read only, 20 minutes): where did 30 GB go?
C: free space dropped from about 92 GB to about 62 GB within hours. Find out why: largest directories modified in the last 24 hours on C: (repo `apps/forecast/data`, `runtime`, pinned worktree copies, `%TEMP%`, Windows Update, hibernation/pagefile growth, `%USERPROFILE%\AppData`, Codex/Claude app caches, ThinkPad scratch copies staged on C:). Report top 10 growers with sizes. Delete nothing. If something is actively filling C:, say so first under Asks.

## Job 1: pilot on one small model
Pilot model: `Qwen3-Reranker-4B` (not used by the forecast). Steps:
1. Confirm no process has files in `Models\Qwen3-Reranker-4B` open and no GPU job or cycle is running (check the GPU lock). If a cycle is running, stop and report; do nothing.
2. Re-verify that D:\Available\Models\Qwen3-Reranker-4B matches (the SHA-256 from Phase A, fresh).
3. Delete `Models\Qwen3-Reranker-4B` on C: and create the NTFS junction `Models\Qwen3-Reranker-4B` -> `D:\Available\Models\Qwen3-Reranker-4B` (`mklink /J`). Record the exact commands in `comms/artifacts/free-space/phase-b1-log.txt`.
4. Test through the junction: file list and sizes identical, the swarm registry scan (`swarm/registry.py`) still lists it, and a real model load (llama-server or the swarm's own loader) generates a few tokens. Record load time vs the C: load time you measured or can measure from another small non-junction model of similar size.
5. Test the failure case without unplugging anything: point a test junction (under a scratch folder, not `Models\`) at a non-existent path and run the registry scan code against it. Report whether it crashes, skips, or hides it. If a dangling junction crashes the registry scan or the swarm startup, stop and report; do not continue to Job 2.

## Job 2: the other 13 (only if Job 1 passes)
One folder at a time, same steps 1-4 each time, in this order (largest first): Qwen3.8-27B-Q5, Trinity-Mini, Gemma-4-31B-it, Qwen3.6-27B, Qwen3.8-27B, ERNIE-4.5-21B-A3B-Thinking, Phi-4-reasoning-vision-15B, HyperCLOVAX-SEED-Think-14B, Apriel-1.6-15B-Thinker, Gemma-4-12B-it-Q5, Bonsai-2-27B, NVIDIA-Nemotron-Nano-9B-v2, GLM-4-9B-0414, Gemma-4-12B-it. Before each delete, the folder's `duplicates.csv` rows must all say Verified=yes and a fresh check of every file's size plus the sampled SHA-256 must match D:. If anything differs, skip that folder and report it. Full model load test only for the first two; for the rest a file-list/size check plus registry scan is enough.
Stop after the 14th or immediately on any unexpected result. Report free space on C: before and after.

## Do NOT touch
`MiMo-V2.6-Distill-Qwen-9B`, `gpt-oss-20b`, `Granite-4.1-3B`, `Granite-4.2-3B`, `Qwen3.6-35B-A3B` (mismatch), the six same-name folders that did not match (`LFM2-350M-Extract`, `LFM2-350M-Math`, `Qwen3.5-0.8B`, `Qwen3.5-2B`, `Qwen3.5-4B`, `Qwen3.5-9B`), every C:-only folder, `Bin\`, `runtime\`, `.venv`, anything under `apps\`, and D:. Never delete or modify anything on D:.

## Report
`comms/2026-10-13-codex-to-pc-free-space-phase-b1.md`: Asks first (including the 30 GB finding), then Info with tables: per folder (status, GB freed, check results, time), the junction commands log path, the dangling-junction test result, C: free before/after. Commit only your own files by name. I verify the folder list, junction targets and C: free space myself afterward.
