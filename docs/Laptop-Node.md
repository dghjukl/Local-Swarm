# Laptop node: the fact-checker server

Notes from Claude Code on the laptop (ASUS TUF FX505DT), 2026-10-07/08, for anyone working on the main PC. Nothing in the swarm code was changed. These are measurements and suggestions.

## What runs there

| | |
|---|---|
| Address | `http://192.168.68.70:8090` (Wi-Fi, address from the router via DHCP; a router reservation is recommended) |
| Model | `granite-4.1-3b-Q5_K_M.gguf` (IBM, 2,437,012,064 bytes) |
| Runtime | llama.cpp **b10152** (same build as the main PC), CUDA 12.0, sm_75 |
| GPU | GTX 1650 Mobile, 4 GB. All 41/41 layers on GPU, about 3,430 MiB used |
| Settings | `-ngl 999 -c 12288 -np 2 --flash-attn on --jinja --reasoning-budget 0 --no-mmap` |
| Per request | **6,144 tokens** (12,288 split over 2 slots), matching `verifier.ctx_per_slot` in `config/swarm.yaml` |
| Service | systemd `swarm-checker`: starts at boot, restarts on failure |
| Firewall | port 8090 open to `192.168.68.0/22` only. No API key |

## Speed

- **Prompt reading:** about 213 tok/s at 570 tokens, 193 at 1,800, and 170 at 3,500.
- **Writing:** about 40 tok/s with one request. With two at once, each one writes at about 32 tok/s.
- **Not throttling:** the GPU stays in P0 at about 1,900 MHz, averages 35 W of its fixed 50 W cap, and peaks at 61 °C.
- **Nothing tried improved prompt speed:** power profile (already on performance), flash attention (already on), `-b/-ub 1024` and `2048` (5–12% slower under 2,000 tokens, 1–2% faster at 3,500), a cuBLAS build and a Pascal-kernel build (both about 3× slower). The GTX 1650 has no tensor cores, and this is about its limit.

## Swarm-style test

Requests were built the way `check_notes()` in `swarm/manager.py` builds them: `VERIFY_SYSTEM` + `VERIFY_SCHEMA`, 4 claims per request, `[E#] (title)` passages, json_schema response format, temperature 0.3, `max_tokens` 600. The passages describe a fictional town, and the 20 claims have known labels.

| | Time for 5 requests | Per request | Reply length | Valid JSON | Correct |
|---|---|---|---|---|---|
| Current prompt, one at a time | 40.7 s | 6.6–10.3 s | 206–314 tok | 5/5 | 16/20 |
| Current prompt, two at a time | 24.1 s | | | 5/5 | 16/20 |
| Reason "at most 10 words", one at a time | 27.2 s | 4.6–6.0 s | 122–144 tok | 5/5 | 17/20 |

- **Writing the reply takes most of the time.** A 4-claim request is only about 260–430 prompt tokens, about 2 s to read. The per-claim reasons take 5–8 s to write.
- **Misses were all borderline "partial" cases:** partial→unsupported twice, supported→partial once, and partial→supported once. Twenty claims is a small sample. The 98% on the 400-claim verifier bench is the better accuracy figure.

## Suggestions for the main PC

1. **The swarm doesn't use the laptop yet.** `config/swarm.yaml` has no `gpu.remote_models`. To use it:
   ```yaml
   gpu:
     remote_models:
       Granite-4.1-3B: {url: "http://192.168.68.70:8090", ctx_per_slot: 6144, parallel: 2}
   ```
2. **Run `Test-Network-Node.bat`** to confirm speed over the real network. This also confirms the laptop's firewall rule from Windows.
3. **Shorter reasons:** changing `Give a short reason.` to `Give a reason of at most 10 words.` in `VERIFY_SYSTEM` made each request about 1/3 faster on the laptop. Check accuracy on the verifier bench before adopting it.
4. **The trade-off:** the 5060 Ti would run Granite much faster. Running it on the laptop frees about 3.4 GB of VRAM on the main PC and lets fact-checks run alongside the workers. The project brief notes the fact-checker gave no score gain so far, so it's worth deciding where, or whether, it should run.

## Laptop housekeeping

Paths are in `~/Desktop/Swarm Node Asus Laptop/` on the laptop. Its `README.md` covers start/stop/logs (`journalctl -u swarm-checker -f`), and `bench/` holds the benchmark script and results.
