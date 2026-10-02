# Local Swarm

A cooperative swarm of small local models on one GPU. A coordinator model plans the work,
a team of small models from different labs answers in parallel, a verifier model
fact-checks their claims, and the coordinator writes one cited answer.

Everything runs on this PC: the models (llama.cpp), web search (DuckDuckGo via `MCP/research-mcp`
plus Wikipedia), speech-to-text (whisper.cpp) and text-to-speech (Piper). Python 3.13
and all packages live inside this folder; nothing is installed on the system.

## Use it

| File | What it does |
|---|---|
| `Setup.bat` | First-time setup: repo-local uv + Python 3.13 + packages, then a GPU self-test |
| `Start-Swarm.bat` | Starts the swarm and opens the web UI at http://127.0.0.1:8700 |
| `Run-Evals.bat` | Runs the test questions (`evals/*.yaml`) through several configurations on the real models, grades them with a judge model, opens a report |
| `Run-Tests.bat` | Runs the automated tests (fake model server, no GPU) |
| `Probe-System.bat` | Records hardware/driver info to `runtime/probe/` |

## How a question flows

1. **Plan**: the coordinator decides whether to answer directly or to research, and writes sub-questions and search queries.
2. **Gather**: web search + Wikipedia, pages fetched and split into ranked passages `[E1]…[En]`.
3. **Work**: each team member answers every sub-question from the passages and cites them.
4. **Verify**: the verifier checks each cited claim against its passages (supported / partial / unsupported).
5. **Answer**: the coordinator writes the final answer from verified claims, with citations.

Every run is saved to `runtime/runs/*.json` for scoring later.

## Evaluate

`Run-Evals.bat` compares the configurations in `evals/configs.yaml` (mixed swarm, coordinator alone,
one bigger model alone, three copies of one small model) on the questions in `evals/research_v1.yaml`.
Every configuration gets the same sub-questions and the same fetched sources. Results land in
`runtime/evals/<time>/`: `report.html`, `results.jsonl`, full traces, the shared evidence and an event log.

Useful options: `--configs a,b`, `--questions id1,id2`, `--repeats 2`, `--reuse-evidence runtime\evals\<time>`
(identical sources as an earlier run), `--regrade runtime\evals\<time>` (grade again, no new runs), `--no-judge`.

## Configure

`config/swarm.yaml` sets which model plays which role, the VRAM budget, and research limits.
Model ids are folder names in `Models/`. All role assignments are provisional until the
qualification tests (next milestone) measure each model.

## Layout

```
swarm/            Python package (pool, orchestrator, tools, speech, web UI)
config/           swarm.yaml
tests/            pytest suite + mock llama-server
MCP/research-mcp  search + fetch MCP server used by the swarm
Models/, Bin/     local weights and binaries (not in git)
runtime/          logs, runs, measurements, Python (not in git)
```
