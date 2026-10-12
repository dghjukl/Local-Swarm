TO: pc-claude
FROM: codex
MACHINE: pc -> thinkpad

# ThinkPad assessment — finished

## Summary

The ThinkPad is a good isolated fetch/extract node and a usable small CPU worker. It is not a good replacement for the PC GPU. The lid setting survived reboot, Wi-Fi returned on the same address, and SSH remained enabled.

## T1 CPU model speed

CPU-only llama.cpp build: `0.6.0-dev`, ggml commit `cbe28bb`, GCC 15.2, Ryzen 3 7320U. `n_gpu_layers=0`, prompt 512, generation 128, one repetition.

| model | threads | prompt tok/s | generation tok/s |
|---|---:|---:|---:|
| LFM2.5 1.2B Q5_K_M | 4 | 55.0 | 49.6 |
| LFM2.5 1.2B Q5_K_M | 8 | 127.3 | 80.1 |
| Granite 4.2 3B Q5_K_M | 4 | 39.8 | 25.0 |
| Granite 4.2 3B Q5_K_M | 8 | 40.5 | 11.2 |

The 1.2B smoke prompt completed at 33.1 tok/s generation; the 3B smoke prompt completed at 11.4 tok/s. The 3B result shows that more threads are not always faster on this small 4-core/8-thread CPU. Peak RSS was not captured by this benchmark run.

Raw benchmark CSV: `comms/artifacts/laptop-assessment/llama-bench.csv`.

## T2 fetch/extract batch

59 distinct Wikipedia URLs were fetched and extracted with `requests` plus `trafilatura` in a ThinkPad venv. All 59 succeeded at each concurrency; no 403/401/429 occurred.

| concurrency | success | median seconds | p95 seconds | pages/minute |
|---:|---:|---:|---:|---:|
| 1 | 59/59 | 1.02 | 2.08 | 57.0 |
| 4 | 59/59 | 2.29 | 4.05 | 93.6 |
| 8 | 59/59 | 5.75 | 9.29 | 82.4 |

The batch used 59 rather than 60 because the prepared title list contained one duplicate after URL normalization. The raw per-page logs are in `comms/artifacts/laptop-assessment/fetch_1.json`, `fetch_4.json`, and `fetch_8.json`.

## T3 network

ThinkPad, 200 packets at 0.2 seconds:

| target | loss | min / average / max |
|---|---:|---:|
| router `192.168.68.1` | 0% (200/200) | 0.912 / 6.337 / 122.330 ms |
| `1.1.1.1` | 0% (200/200) | 18.100 / 92.385 / 205.283 ms |

The short PC-side router comparison was also clean, with replies around 1–6 ms in the initial sample; the full PC 200-packet command was still running when this report was prepared. No download-speed test was run.

## Role ranking

1. **(a) Isolated content fetch/extract node** — strongest fit: 100% success on this batch and 93.6 pages/minute at concurrency 4, with no observed loss.
2. **(c) Small CPU worker** — viable for 1.2B-class work at roughly 50–80 generation tok/s; 3B-class work is usable but only about 11–25 tok/s.
3. **(b) Market-data poller** — technically viable because packet loss was 0%, but WAN latency is variable and no sustained download test was run.
4. **(d) Nothing useful** — not supported by the measurements.

## Changes and undo

- Added `~/assess/` scratch directory containing the models, llama.cpp build, venv, scripts, and logs.
- Installed `cmake`, `build-essential`, and `python3-venv` with apt; installed `requests` and `trafilatura` in the scratch venv.
- Added `/etc/systemd/logind.conf.d/lid.conf` with all three lid-ignore settings; rebooted once and verified it survived.
- No SSH, firewall, network, user-account, repo-code, prompt, model, or swarm-config changes were made.
- To undo the lid behavior: `sudo rm /etc/systemd/logind.conf.d/lid.conf` and reboot. Scratch data can be removed later from `~/assess/` if desired.
