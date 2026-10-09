# comms: notes between the Claude sessions working on this repo

Three AI sessions work on Local Swarm:
- **PC (Claude)**: Claude (Cowork) working on the main Windows PC, which holds the swarm code, runs the studies and keeps the project docs (claude.ai project "Swarm"). Pulls and pushes through GitKraken on the PC.
- **PC (Codex)**: Codex in the same PC checkout, running natively on Windows. **Runner and researcher:** runs things on the PC that Claude can't (tests in the real venv, GPU benchmarks, short eval runs, nvidia-smi, web research) from job tickets, and reports results. Also reviews. Code changes go through a note here first (see "Shared checkout").
- **Laptop**: Claude Code on the ASUS laptop node (192.168.68.70), which runs the Granite fact-checker server.

File names use `pc`, `codex` or `laptop`, e.g. `2026-10-09-codex-to-pc-review.md`.

They can't talk directly. They leave each other notes here, and Chris syncs them through GitHub: he commits and pushes from the PC, and the laptop pulls (and the reverse).

## Rules
- One file per message: `YYYY-MM-DD-<from>-to-<to>-<topic>.md`, e.g. `2026-10-08-pc-to-laptop-hello.md`. Never edit someone else's message; reply with a new file.
- Start each message with **Asks** (what you want the other side to do), then **Info**.
- Put results (benchmarks, logs) in the message or next to it, with the exact command used.
- The laptop doesn't change swarm code (`swarm/`, `evals/`, `config/`, tests, .bat files) and doesn't run studies. Suggestions for that code go in a message; the PC side makes the change, tests it and deploys it.
- Nothing secret goes here: no API keys, tokens or passwords (`runtime/secrets.json` stays out of git).
- Chris decides anything that costs money, changes his network or firewall, or deletes things.

## Shared checkout (Claude and Codex on the same PC)
- Before changing anything outside `comms/`, post a short "claiming X" note and wait for an OK. A code change can land in the middle of a running study (the bat restarts with `--resume` after a crash and would load the new code).
- Never touch `runtime/` (study outputs) or `Models/`.
- Code changes need passing tests (`Run-Tests.bat`), with a note listing the files and why.
- Commit messages say who wrote the change.

## Job tickets (PC Claude → Codex)
- A job file is named `YYYY-MM-DD-pc-to-codex-job-<id>-<name>.md` and lists: what to run (exact commands), when it may start, expected time, what to record, and stop conditions.
- Codex replies `...-codex-to-pc-job-<id>-result.md` with the numbers, the exact commands run, anything odd, and where output files are.
- **One GPU job at a time.** Before any GPU job, check that no study is running: the newest `runtime/evals/*/events.log` is still growing, or llama-server / python `swarm.evals` processes exist. If one is, wait.
- Jobs over about 1 hour, or anything that downloads big files, need Chris's OK (in chat or in a note here).
