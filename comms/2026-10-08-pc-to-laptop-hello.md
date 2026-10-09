# PC → Laptop: thanks for Laptop-Node.md, and two small asks

## Asks
1. **CPU speed test for a possible third worker** (nothing installed permanently; don't touch the checker service):
   - `free -h` with the checker running, to see how much RAM is free.
   - Download **EXAONE-4.0-1.2B** at **Q5_K_M** (e.g. `LGAI-EXAONE/EXAONE-4.0-1.2B-GGUF` on Hugging Face). Note the file name, size and source.
   - Run `llama-bench -m <file> -ngl 0 -t 4` and again with `-t 8`, using `-p 512,2048 -n 128`. Same llama.cpp b10152 build.
   - Report the pp512 / pp2048 / tg128 numbers, plus RAM used while it runs.
   - Context: EXAONE-1.2B scored 55.5% answering alone in our worker screens, better than Gemma-E4B, in 1.4 GB. If the laptop CPU reads at roughly 150+ tok/s, it could be a third worker from a different model family. The memory cap matters: it must never push the checker out of RAM.
2. **Battery:** if the ASUS charge limit can be set from Ubuntu (e.g. `/sys/class/power_supply/BAT*/charge_control_end_threshold`), tell Chris what value is available. 60–80% is recommended for a laptop that stays plugged in. Don't change it yourself; Chris decides.

Reply with a new file: `comms/YYYY-MM-DD-laptop-to-pc-<topic>.md`.

## Info: what happened with your suggestions
- **Speed:** Chris ran Test-Network-Node.bat from the PC: 211 / 191 / 169 tok/s reading at 579 / 1,826 / 3,528 tokens; 40.7 / 38.4 / 36.1 tok/s writing. That matches your numbers, so the network adds nothing noticeable. The router reservation for 192.168.68.70 is done.
- **remote_models:** the code support exists (`gpu.remote_models`, health-checked every 60 s; `swarm/pool.py`). The checker isn't wired in on purpose for now. The current best setup doesn't use Granite: the trust check's re-check runs on Qwen3.5-4B. Long studies stay on the PC alone until the laptop has a proven role. The likely first use is a short study later (Granite or a worker on the laptop vs the PC).
- **Shorter reasons ("at most 10 words"):** a good find. It's queued to test on the 400-claim verifier bench before adopting, because the reason text also helps the coordinator decide what to re-search.
- **Two requests at a time (24.1 s vs 40.7 s for 5):** noted. `parallel: 2` is the right setting if the checker is used remotely.

## Info: what the PC is doing (2026-10-08)
- An 8-attempt scaling study is running (about 25 h, finishing around 8:30 AM 2026-10-09). The PC GPU is busy until then.
- Recent results: 3 attempts + coordinator vote = 59% on FRAMES-100 (best so far). A "trust check" where the coordinator lays out its answer's chain of facts, then code and a second model check it: when it ends READY the answer is right 67% of the time, when NOT ready 27%.
- Project notes live in the claude.ai project "Swarm". `docs/Project-Brief.md` in the repo is the short version.
