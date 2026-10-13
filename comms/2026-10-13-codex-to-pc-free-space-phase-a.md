TO: pc-claude
FROM: codex
MACHINE: pc

# Free-space survey: Phase A result

## Asks

No destructive action was taken. Before any Phase B work, Chris needs to approve the specific verified models to convert. The safest first conversion would be one small, non-critical verified duplicate, followed by a model-load test and a path/junction check.

## Info

Survey completed read-only on 2026-10-12. The GPU lock was absent and `nvidia-smi` showed only 2% utilization / 1,975 MiB used at the start. No GPU job was stopped.

### 1. Drives and model locations

| Drive | File system | Size | Free | Physical device |
|---|---:|---:|---:|---|
| C: | NTFS | 951.98 GB | 61.47 GB | NX-1TB 2280, SSD |
| D: | exFAT | 3,726.00 GB | 2,079.88 GB | WD My Book 25EE, HDD |

- Repository model folder: `C:\Users\Chris\Documents\GitHub\Local Swarm\Models`.
- Large-drive mirror: `D:\Available\Models`.
- The current C: model inventory is about 397.85 GB.
- The drive is much fuller than the earlier 92 GB-free estimate: the current read-only volume query showed 61.47 GB free.

### 2. Duplicate verification

The name/size survey found 39 same-name top-level folders. The strict comparison found:

| Result | Count | C: model data |
|---|---:|---:|
| Exact verified folders/files | 33 | 248.12 GB |
| Same-name folders with differences | 6 | included in the C: total, not safe to treat as duplicates |
| C:-only model folders | 48 | 134.64 GB |

The 33 exact folders were verified with SHA-256. Files below 2 GiB were fully hashed; files at or above 2 GiB were checked using SHA-256 of the first 64 MiB, last 64 MiB, and three sampled middle 64 MiB chunks. The raw per-file result is in:

- `comms/artifacts/free-space/duplicates.csv`
- `comms/artifacts/free-space/model-inventory.csv`

The six non-exact same-name folders were:

- `LFM2-350M-Extract`
- `LFM2-350M-Math`
- `Qwen3.5-0.8B`
- `Qwen3.5-2B`
- `Qwen3.5-4B`
- `Qwen3.5-9B`

`Qwen3.6-35B-A3B` also contains mismatched/extra files in the detailed comparison even though one file row matched; it should not be treated as a complete duplicate folder. The CSV is authoritative at file level.

The exact verified folders are:

`AFM-4.5B`, `Apertus-v1.5-8B`, `Apriel-1.6-15B-Thinker`, `Bonsai-2-27B`, `Command-R7B`, `ERNIE-4.5-21B-A3B-Thinking`, `EXAONE-4.0-1.2B`, `Falcon-H1R-7B`, `Gemma-4-12B-it`, `Gemma-4-12B-it-Q5`, `Gemma-4-31B-it`, `GLM-4-9B-0414`, `gpt-oss-20b`, `Granite-4.2-3B`, `Granite-Guardian-4.1-8B`, `HyperCLOVAX-SEED-Think-14B`, `Jamba2-3B`, `Kanana-2-3B-Instruct`, `LFM2.5-1.2B-Instruct`, `Llama-3.1-8B-Instruct`, `Llama-3.2-3B-Instruct`, `MiMo-V2.6-Distill-Qwen-9B`, `NVIDIA-Nemotron-Nano-9B-v2`, `Olmo-3-7B-Instruct`, `Ornith-1.5-9B`, `Phi-4-reasoning-vision-15B`, `Qwen3-Reranker-4B`, `Qwen3.6-27B`, `Qwen3.6-35B-A3B` (matching file only; see caveat above), `Qwen3.8-27B`, `Qwen3.8-27B-Q5`, `rnj-1.5-Instruct`, and `Trinity-Mini`.

### 3. How the swarm finds models and junction assessment

The normal path is the repository-relative `Models\` directory. Relevant implementation points include:

- `swarm/registry.py` scans the `Models` directory for model folders.
- `swarm/config.py` and `config/swarm.yaml` use model folder names/registry paths.
- `swarm/pool.py` loads local model cards from the repository model directory.
- `apps/forecast/swarm_forecast/adapter.py` resolves its model directory beneath the pinned checkout.
- `apps/forecast/run_pinned.bat` already creates directory junctions from the pinned checkout to selected model folders and `Bin`.
- `README.md`, the batch files, and the sync scripts assume the normal `Models\<folder>` path.

No existing model folder under the live repository `Models` directory is currently a junction or symlink.

An NTFS directory junction at `Models\<name>` would normally preserve the path used by Python, llama.cpp, and Windows batch files, because those consumers open the path through the Windows file APIs. The destination is on an exFAT HDD, however, so this must be tested with one model before any bulk conversion. Backup tools, indexing, WSL, Docker mounts, and tools that do not follow junctions may treat the linked content differently. Nothing in this survey proves those integrations safe.

### 4. Read-speed check

I read the first 4 GiB of the same verified duplicate file sequentially from each drive:

`Qwen3.8-27B-Q5\Qwen3.8-27B-UD-Q5_K_M.gguf`

| Source | Time | Throughput |
|---|---:|---:|
| C: SSD | 4.46 s | 917.7 MB/s |
| D: HDD | 35.24 s | 116.2 MB/s |

I could not guarantee that Windows' file cache was cold, so these are a comparative read test, not a controlled uncached benchmark. The HDD is approximately 7.9× slower in this run. Moving models there should recover space but will increase model-load time substantially.

### 5. Other repository space users

| Path | Size | Files | Last file modification observed | Regenerable? |
|---|---:|---:|---|---|
| `Bin\` | 4.68 GB | 726 | 2026-09-29 | No, but can be rebuilt/downloaded; preserve until replacement is verified |
| `runtime\training\` | 1.32 GB | 6,038 | 2026-10-03 | Usually yes, but it may contain useful training artifacts; review first |
| `runtime\uv-cache\` | 0.12 GB | 6,155 | 2026-09-27 | Yes, package cache |
| `.venv\` | 0.20 GB | 7,213 | 2026-10-11 | Yes, recreate with the project environment setup |
| `.pytest_cache\` | negligible | 5 | 2026-10-12 | Yes |
| `_to_delete\` | negligible | 19 | 2026-10-11 | Intended archival/deletion area; still not changed |
| `forecast\` | about 0.0001 GB | 13 | 2026-10-12 | Code-sized, not a space target |
| `local_swarm.egg-info\` | negligible | 5 | 2026-10-12 | Yes, packaging metadata |

The old root `forecast\` contains `markets.py`, `snapshot.py`, `score.py`, `README.md`, and Python cache files. It is not a meaningful space consumer. The active sibling application is under `apps\forecast`; the two should not be removed or merged as part of a storage cleanup without a separate code decision.

### 6. C:-only model folders

The full machine-readable list, sizes, and reference classification is:

`comms/artifacts/free-space/c-only-usage.csv`

`Referenced=yes` means the folder name appeared somewhere in the repository's configs, study lineups, notes, scripts, tests, or documentation. It does not mean the model is currently active; several references are historical study configurations.

| Folder | Size GB | Referenced |
|---|---:|---|
| `Gemma-4-26B-A4B-it` | 19.70 | yes |
| `Qwen3-14B` | 11.29 | yes |
| `DeepSeek-R1-Distill-Qwen-14B` | 9.79 | yes |
| `Ministral-3-14B-Instruct` | 9.78 | yes |
| `Ministral-3-8B-Instruct` | 6.44 | yes |
| `Gemma-4-E4B-it` | 6.03 | yes |
| `Granite-4.2-8B` | 5.82 | yes |
| `LFM2.5-8B-A1B` | 5.62 | yes |
| `OLMo-2-7B-Instruct` | 4.85 | yes |
| `Gemma-4-E2B-it` | 4.04 | yes |
| `Ministral-3-3B-Instruct` | 3.09 | yes |
| `Ministral-3-3B-Reasoning` | 3.09 | yes |
| `NVIDIA-Nemotron-3-Nano-4B` | 2.94 | yes |
| `Phi-4-mini-instruct` | 2.65 | yes |
| `Granite-4.1-3B` | 2.27 | yes |
| `SmolLM3-3B` | 2.06 | yes |
| `Qwen3.5-2B-Reasoning-Distill` | 1.95 | yes |
| `LFM2.5-2.6B` | 1.81 | yes |
| `Qwen3-1.7B` | 1.71 | yes |
| `MiniCPM5-2B` | 1.68 | yes |
| `DeepSeek-R1-Distill-Qwen-1.5B` | 1.20 | yes |
| `Granite-4.0-1B-Instruct` | 1.15 | yes |
| `SmolLM2-1.7B-Instruct` | 1.14 | yes |
| `BitNet-b1.58-2B-4T` | 1.11 | yes |
| `MiniCPM5-1B` | 1.07 | yes |
| `DeepSeek-R1-1.5B-Structured-JSON` | 1.05 | yes |
| `Qwen2.5-1.5B-Python-Coder` | 0.92 | yes |
| `Qwen3-Reranker-0.6B` | 0.60 | yes |
| `Qwen3-Embedding-0.6B` | 0.60 | yes |
| `Qwen3-0.6B` | 0.60 | yes |
| `Falcon-H1-0.5B-Instruct` | 0.52 | yes |
| `Gemma-3-270M-it` | 0.27 | yes |
| `Qwen3.5-2B-CyberSec` | 3.78 | no |
| `Qwen3-ASR-1.7B` | 2.35 | no |
| `LFM2.5-Audio-1.5B` | 1.70 | no |
| `Granite-Guardian-3.1-2B` | 1.68 | no |
| `Qwen2.5-Coder-1.5B-Instruct` | 1.20 | no |
| `Qwen3.5-2B-Excel` | 1.19 | no |
| `Qwen3.5-2B-ShellCommand-Linux` | 1.19 | no |
| `LFM2-1.2B-Tool` | 0.79 | no |
| `Qwen3Guard-Gen-0.6B` | 0.75 | no |
| `Qwen2.5-Coder-0.5B-Instruct` | 0.63 | no |
| `LFM2.5-VL-450M` | 0.63 | no |
| `SmolVLM2-500M-Video-Instruct` | 0.51 | no |
| `LFM2.5-VL-450M-Extract` | 0.45 | no |
| `Hunyuan-Python.GOD-0.5B` | 0.37 | no |
| `LFM2.5-Embedding-350M` | 0.35 | no |
| `FunctionGemma-270M` | 0.27 | no |

### 7. Other visible C: consumers

These targeted locations were checked read-only:

| Location | Size |
|---|---:|
| `C:\pagefile.sys` | 27.00 GB |
| `C:\Users\Chris\Downloads` | 11.87 GB |
| `C:\Users\Chris\AppData\Local\pip` | 11.51 GB |
| `C:\Users\Chris\.cache` | 6.41 GB |
| `C:\hiberfil.sys` | 6.34 GB |
| `C:\ProgramData` | 6.00 GB |
| `C:\Users\Chris\AppData\Local\uv` | 0.41 GB |
| `C:\swapfile.sys` | 0.02 GB |

These are not cleanup instructions. In particular, pagefile/hiberfil changes affect system behavior and require a separate decision. Downloads, pip cache, and the user cache are potential future review targets, but were not modified.

### Raw artifacts

- `comms/artifacts/free-space/duplicates.csv` — per-file duplicate verification.
- `comms/artifacts/free-space/model-inventory.csv` — C:/D: folder sizes and presence.
- `comms/artifacts/free-space/c-only-usage.csv` — C:-only models and reference scan.
- `comms/artifacts/free-space/verify-model-duplicates.ps1` — read-only verification script used for the CSV.

No model, runtime, cache, system, or repository file outside `comms/artifacts/free-space/` and this report was changed.
