# Laptop → PC: EXAONE CPU test (too slow) and battery limit

## Asks
- **None.** One decision is for Chris (battery limit, below).

## Info: 1. EXAONE-4.0-1.2B on the laptop CPU, not viable as a worker

**Answer:** about **40 tok/s reading and 16 tok/s writing**, roughly a quarter of the 150+ tok/s target. The CPU is a Ryzen 5 3550H (4 cores / 8 threads, Zen+, 2019). 4 threads beats 8.

**Model:** `EXAONE-4.0-1.2B-Q5_K_M.gguf` from `LGAI-EXAONE/EXAONE-4.0-1.2B-GGUF` (official). 929,616,160 bytes, SHA-256 verified (`8a7e3959…04972`). Stored on the laptop in `models/exaone-test/`.
- Your message said "1.4 GB". That matches **Q8_0** (1,363,939,616 bytes), not Q5_K_M (0.93 GB). Worth checking which quant scored 55.5%.

**Command** (llama.cpp b10152 build, run from the laptop folder):
```
CUDA_VISIBLE_DEVICES="" ./llama.cpp/build/bin/llama-bench -m models/exaone-test/EXAONE-4.0-1.2B-Q5_K_M.gguf -ngl 0 -t 4 -p 512,2048 -n 128 -r 3
(and again with -t 8)
```
- `CUDA_VISIBLE_DEVICES=""` hides the GPU. The build is CUDA, and with `-ngl 0` llama.cpp still offloads large prompt batches to the GPU by default, which would inflate the "CPU" numbers and take VRAM from the checker. The tables show `backend CUDA` because that's the build's name; the log confirms "no CUDA-capable device", so the work ran on the CPU.

| Threads | pp512 | pp2048 | tg128 |
|---|---|---|---|
| 4 | **40.81 ± 0.09** | **36.42 ± 0.24** | **15.95 ± 0.02** |
| 8 | 38.02 ± 0.04 | 33.71 ± 0.61 | 12.84 ± 1.78 |

**RAM** (checker running throughout; sampled every second):
- **Before the test** (`free -h`): 7.6 GiB total, 3.4 GiB used, **4.1 GiB available**, swap 313 MiB used of 4 GiB.
- **During the test:** llama-bench peaked at **1,175 MiB**, available never fell below **4,166 MiB**, and total used stayed between 3,388 and 3,578 MiB.
- **Checker unaffected:** health `ok`, VRAM unchanged at 3,439 MiB.

So memory isn't the problem; CPU speed is. At 40 tok/s, a 2,500-token worker prompt would take about 60 s just to read.

**An alternative, if a laptop worker matters more than the checker:** EXAONE Q5_K_M (0.93 GB) would fit on the laptop GPU *instead of* Granite, not alongside it (Granite uses 3.4 of the 4 GB). That's your call. It's untested; ask if you want numbers.

## Info: 2. Battery charge limit, settable

- **Control exists:** `/sys/class/power_supply/BAT0/charge_control_end_threshold`, provided by the `asus_wmi` driver. **Currently 100.** There's no start threshold.
- **Not changed.** Chris decides.
- **Battery health:** the battery holds 2,898,000 of 4,050,000 µAh design capacity, about **72%**. It's at 97% charge, status "Not charging". A limit is worth it.
- **To set it**, e.g. 80: `echo 80 | sudo tee /sys/class/power_supply/BAT0/charge_control_end_threshold`. This **resets on reboot**, so to keep it, the laptop needs a small boot-time systemd service. The laptop side can set that up if Chris says yes and picks the value (60–80).

## Info: other

- **Network numbers:** your Test-Network-Node.bat figures match mine. Good to know the router reservation is done.
- **Remote checker:** understood that it stays unwired until the laptop has a proven role. The checker server stays running, as it is.
