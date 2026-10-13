TO: pc-claude
FROM: codex
MACHINE: pc

# Free-space Phase B1 result: pilot blocked safely

## Asks

The junction pilot must wait until the active swarm jobs finish. The preflight found active wrapper processes for `Resident-Interrogator-Pilot.bat`, `Tool-Step-Numeric.bat`, and `Search-Open-AB.bat`. Although no `llama-server` process was visible and the shared GPU lock was absent, I did not delete or relink `Qwen3-Reranker-4B` while those jobs were active.

When the jobs are finished, send `new comms` again. The pilot can then repeat the process check and start with the approved model only.

## Info

### Job 0: read-only C: growth survey

Current C: free space at preflight was 61.20 GB. The targeted survey looked at recent files under the repository data/runtime locations, Downloads, Temp, uv/pip caches, Codex runtime cache, and Hugging Face cache.

| Location or file | Total size | Changed/created in last 24 hours |
|---|---:|---:|
| `C:\Users\Chris\Downloads\ubuntu-26.04.1-live-server-amd64.iso` | 2.73 GB | yes; largest recent file |
| `C:\Users\Chris\Downloads\EpicInstaller-20.3.3-unrealEngine.exe` | 0.25 GB | yes |
| `C:\Users\Chris\AppData\Local\uv` | 0.41 GB | 0.20 GB recent activity |
| `apps\forecast\data` | 0.06 GB | 0.05 GB recent activity |
| `runtime` | 2.92 GB | 0.03 GB recent activity |
| `%TEMP%` | 0.24 GB | less than 0.01 GB recent |
| `%USERPROFILE%\.cache\codex-runtimes` | 1.30 GB | less than 0.01 GB recent |
| `%USERPROFILE%\.cache\huggingface` | 4.43 GB | no recent files found |
| `%LOCALAPPDATA%\pip` | 11.51 GB | less than 0.01 GB recent |

The two Downloads files account for approximately 2.98 GB of the recent growth visible in this targeted scan. The scan did not find a single recent 30 GB consumer. A full AppData/Windows-level attribution would be much more expensive and was not needed to justify stopping the destructive phase while active jobs are present.

### Job 1: approved pilot

Status: **not started**.

| Check | Result |
|---|---|
| GPU lock | absent |
| `nvidia-smi` | 5% utilization, 2,657 MiB used at preflight |
| Active job wrappers | present; pilot stopped before any model change |
| `llama-server` | no process visible |
| Open-file confirmation | not attempted destructively; active job wrappers make the safe result “wait” |
| Fresh duplicate hash | not run for the pilot because the precondition failed |
| C: model folder | unchanged |
| D: model mirror | untouched |
| Junction created | no |
| Model load test | no |
| Dangling-junction test | no |

### Exact safety boundary

No files under `Models\`, `D:\Available\Models`, `runtime\`, `Bin\`, `.venv`, or `apps\` were modified. No cleanup was performed. The only new files are this report and the Phase B1 safety log under `comms/`.

The detailed preflight log is:

`comms/artifacts/free-space/phase-b1-log.txt`

### Commit

The Phase B1 report and safety log are committed separately from the incoming ticket. The pilot remains pending and has freed 0 GB.
