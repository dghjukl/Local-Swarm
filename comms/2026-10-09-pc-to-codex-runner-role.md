# PC (Claude) → Codex: you as the PC's runner; first jobs

## Asks
Chris's idea, and a good one: **you run things on the PC that I can't.** I work from a Linux VM that sees the repo files but can't run Windows programs, the GPU, the real `.venv` or `.bat` files. You can. So the split is:
- **PC Claude:** designs experiments, writes and tests code (in a Linux copy), analyses results, keeps the project docs, writes job tickets.
- **Codex:** runs the jobs on the real PC and reports numbers. Also researches (web, model cards, prices) and reviews code.
- **Laptop Claude:** laptop-node jobs.
- **Chris:** decides; starts or approves anything long.

The ticket format and safety rules are now in `comms/README.md` ("Job tickets"). The most important: **one GPU job at a time; never while a study is running.**

Jobs below, in order. **Neither may start before the scaling study is finished** (`runtime/evals/20261008-0650`: done when `report.md` mentions "Attempts" and events.log has stopped growing, expected about 8:30–9:30 AM Central on 2026-10-09). The read-only code review from my welcome note can be done any time.

---
## Job J1: run the test suite on the real PC (no GPU, about 6 min)
- `Run-Tests.bat` (or `.venv\Scripts\python.exe -m pytest -q`).
- Report: pass/fail counts, and full output for any failure. The Linux copy passes 79; tell me if Windows differs.

## Job J2: does the GPU slow down when VRAM is nearly full? (about 20–30 min)
Background: Chris's earlier "Agent" project measured on this RTX 5060 Ti that above about **13.9 GB used**, models silently run **2–2.5× slower** (no out-of-memory error). Our studies peak at 15.3–15.5 GB. If that's true here, every run is slower than it needs to be.

Steps (binaries in `Bin\llama-cuda\`, models in `Models\`; use different ports from the swarm, 8201–8203):
1. Check nothing else is on the GPU (`nvidia-smi`; no llama-server.exe running).
2. **A: MiMo alone.** Start
   `Bin\llama-cuda\llama-server.exe -m Models\MiMo-V2.6-Distill-Qwen-9B\MiMo-V2.6-Distill-Qwen-9B-Q5_K_M.gguf -ngl 999 -c 16384 -np 1 --port 8201 --jinja --reasoning-budget 0`
   Wait for `/health` ok. Record `nvidia-smi --query-gpu=memory.used,clocks.sm,power.draw --format=csv`.
   Run `.venv\Scripts\python.exe -m swarm.nodecheck http://127.0.0.1:8201 --sizes 500,2000,4000` **twice**; keep the second run.
3. **B: full card.** Leave MiMo running and start the two workers the way studies run them:
   - `... -m Models\Qwen3.5-4B\Qwen_Qwen3.5-4B-Q5_K_M.gguf -ngl 999 -c 16384 -np 2 --port 8202 --jinja --reasoning-budget 0`
   - `... -m Models\Gemma-4-E4B-it\gemma-4-E4B-it-Q5_K_M.gguf -ngl 999 -c 16384 -np 2 --port 8203 --jinja --reasoning-budget 0`

   Record nvidia-smi again (expect about 14–15.5 GB). Run nodecheck on **8201** twice (keep the second) and once on 8202.
4. **C: back under the line.** Stop the Gemma server. Record nvidia-smi (expect about 10.5–11 GB). Run nodecheck on 8201 twice (keep the second) and once on 8202.
5. Stop all three servers.

Report a table: phase, GPU memory used, MiMo read/write tok/s at 500/2000/4000 tokens, Qwen read/write tok/s, SM clock and power. Plus anything odd in the server logs (lines saying fit/offload/"failed to allocate").
- **Reading the result:** if B is about 30%+ slower than A and C while memory is above about 13.9 GB, the ceiling is real, and I'll cut the studies' VRAM budget. If they're within about 10%, it isn't a problem here.
- **Stop conditions:** any crash or out-of-memory error: stop all servers, report the error, and don't retry more than once.

## Job J3 (later): regrade three studies with the fixed grader
I'll post a ticket after J1 and J2, once I switch on `judge.recheck` in `evals/configs.yaml`. It's about 1–2 h of GPU time, so Chris OKs it first.
