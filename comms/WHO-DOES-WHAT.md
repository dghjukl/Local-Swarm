# Who does what (read this before acting on any file in comms/)

Written 2026-10-12 by PC Claude at Chris's request, so the three agents and three machines do not get mixed up.

## Machines
| name | what it is | address |
|---|---|---|
| `pc` | main Windows desktop (RTX 5060 Ti), holds the repo and runs all studies and forecast cycles | 192.168.68.53 |
| `thinkpad` | Lenovo IdeaPad 1 15AMN7, Ubuntu Server 26.04, CPU only, no agent of its own | thinkpad@192.168.68.71 |
| `asus` | ASUS TUF FX505DT, Ubuntu 24.04, GTX 1650 4 GB, runs the Granite checker service on port 8090 | 192.168.68.70 |

## Agents (the only three)
| agent (use this name in filenames) | where it runs | what it does | what it never does |
|---|---|---|---|
| `pc-claude` | Claude (Cowork) on the desktop PC | writes tickets, analyses, verifies other agents' reports against the raw files, keeps project docs | does not run jobs on the laptops; does not commit code |
| `codex` | Codex CLI on the desktop PC | runs tickets on `pc`, and runs tickets on `thinkpad` over SSH from the PC; commits and pushes | does not touch `asus` (only if a ticket addressed to `codex` says MACHINE: asus) |
| `laptop` | Claude Code CLI on `asus` | works only on `asus`: services, power settings, the checker, local tests, short reports | does not change swarm code (`swarm/`, `evals/`, `config/`, `apps/`), does not run studies, does not touch `pc` or `thinkpad` |

## Every comms file starts with this header (copy it exactly)
```
TO: codex | laptop | pc-claude
FROM: codex | laptop | pc-claude
MACHINE: pc | thinkpad | asus   (which machine the work happens on)
IF YOU ARE NOT "TO": DO NOTHING. Do not act on this file.
```
- File name stays `YYYY-MM-DD-<from>-to-<to>-<topic>.md`. When the work is on a laptop, put the machine in the topic, e.g. `2026-10-12-pc-claude-to-codex-thinkpad-assessment.md`.
- A file with no header is not for you. Ask Chris.
- `codex` ignores files addressed to `laptop`. `laptop` ignores files addressed to `codex`. Older files named `pc-to-codex` mean `pc-claude` to `codex`; older files named `pc-to-laptop` mean `pc-claude` to `laptop`.
- If a ticket needs two agents, it is two files, one per agent, each with its own header.

## How it moves
- Chris says "new comms" to `codex` and "new comm" to `laptop`. Chris syncs through GitHub: the PC pushes, the Asus pulls (`git pull` first, always), and the reverse for replies.
- `laptop` and `codex` reply with a new file addressed back to `pc-claude`. Never edit someone else's message.
- Nothing secret in comms: no keys, tokens or passwords.
- Chris decides anything that costs money, changes his network or firewall, or deletes things.
