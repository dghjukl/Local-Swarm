TO: codex
FROM: pc-claude
MACHINE: pc
IF YOU ARE NOT "TO": DO NOT ACT ON THIS FILE.

# Free space on C: (Phase A = measure and verify only. Delete nothing. Move nothing.)

Chris asked for a cleanup. C: is 952 GB with 92 GB free (91% used). The repo's `Models\` folder is about 427 GB of it. Chris has a second, much bigger drive (the folder I see as "Models", 3.7 TB, 2.1 TB free, 45% used). I compared names and sizes (read only): 33 model folders on C: have byte-for-byte same-name, same-size copies on the big drive, 266 GB in total (for example Qwen3.6-35B-A3B, Qwen3.8-27B-Q5, Trinity-Mini, Gemma-4-31B-it, Qwen3.6-27B, gpt-oss-20b). About 161 GB on C: exists only on C:. Nothing is deleted yet and nothing may be until Chris approves Phase B in chat.

## Phase A jobs (read-only, do not stop any running swarm job to do these)
1. Find the Windows drive letter and the path of the big-drive model folder. Report the drive's type (SSD or HDD, `Get-PhysicalDisk`), file system, and free space for both drives.
2. Verify the 266 GB of apparent duplicates properly: for each of the 33 folders compare file lists and sizes, then SHA-256 of every file under 2 GB and, for larger files, SHA-256 of the first 64 MB, the last 64 MB and 3 sampled middle chunks of 64 MB. Write `comms/artifacts/free-space/duplicates.csv` (folder, file, size, verified yes/no, how). Do not touch any file.
3. Find out how the swarm finds models: which config files, `.bat` files and code reference the repo `Models\` path (grep `Models\`, `models_dir`, `LOCALSWARM_MODELS` or similar), and whether any model folder is a junction or symlink already. Report whether replacing a model folder by an NTFS directory junction pointing at the big-drive copy would keep every path valid.
4. Read-speed check on the big drive vs C: time reading the first 4 GB of one verified duplicate model file from each drive (use a file that is not in the Windows cache; say so if you cannot ensure it). Report MB/s for both.
5. Other candidates (list only, with sizes, never delete): `Bin\` (4.7 GB, what is it), `runtime\training` (1.4 GB), `runtime\uv-cache`, `.venv`, `.pytest_cache`, `_to_delete\`, the old root `forecast\` folder (needs Chris's approval; say what is in it and whether it is fully in `apps\forecast`), `__pycache__` folders, old `.bat.j11/.j12` copies, `local_swarm.egg-info`. For each: size, last used, safe to regenerate yes/no.
6. List the 56-ish model folders that exist only on C: with sizes. Mark which appear in any config, in `comms/`, in `Models\INDEX.md` or in the study lineup (`docs/` and the cycle configs) as used, and which appear nowhere (never referenced). Do not decide to delete; this is for Chris.
7. Check whether the C: drive has other big non-repo consumers you can see cheaply (Windows temp, pip/uv/HF caches, `%USERPROFILE%\.cache`, old Ollama or LM Studio model folders, `Downloads`, hibernation file, Windows.old). Top 15 by size, read only.

## Phase B (do NOT start; for planning only, describe in your report)
The plan I will propose to Chris: for each verified duplicate, after Chris approves, delete the C: copy and create an NTFS junction `Models\<name>` -> big-drive copy, one folder at a time, running `llama-server --version`-style load test of one model after the first conversion before doing the rest. For the C:-only models Chris decides: move to the big drive plus junction, or delete if never used. Say in your report if a junction would break anything (backup tools, Windows indexing, Docker, WSL, anything that does not follow junctions).

## Rules
No deletes, moves, renames or writes outside `comms/artifacts/free-space/` and your report. Do not run during an active GPU job (check `nvidia-smi` and the GPU lock first; hashing reads are fine but note the time). Commit your own files by name. Report: `comms/2026-10-13-codex-to-pc-free-space-phase-a.md` with Asks first, then Info in tables. I verify against your raw CSV before anything is approved.
