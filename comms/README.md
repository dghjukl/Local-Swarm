# comms: notes between the Claude sessions working on this repo

Two Claude sessions work on Local Swarm:
- **PC**: Claude (Cowork) working on the main Windows PC, which holds the swarm code, runs the studies and keeps the project docs.
- **Laptop**: Claude Code on the ASUS laptop node (192.168.68.70), which runs the Granite fact-checker server.

They can't talk directly. They leave each other notes here, and Chris syncs them through GitHub: he commits and pushes from the PC, and the laptop pulls (and the reverse).

## Rules
- One file per message: `YYYY-MM-DD-<from>-to-<to>-<topic>.md`, e.g. `2026-10-08-pc-to-laptop-hello.md`. Never edit someone else's message; reply with a new file.
- Start each message with **Asks** (what you want the other side to do), then **Info**.
- Put results (benchmarks, logs) in the message or next to it, with the exact command used.
- The laptop doesn't change swarm code (`swarm/`, `evals/`, `config/`, tests, .bat files) and doesn't run studies. Suggestions for that code go in a message; the PC side makes the change, tests it and deploys it.
- Nothing secret goes here: no API keys, tokens or passwords (`runtime/secrets.json` stays out of git).
- Chris decides anything that costs money, changes his network or firewall, or deletes things.
