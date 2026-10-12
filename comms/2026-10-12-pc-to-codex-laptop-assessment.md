# PC Claude -> Codex: 30-minute assessment of the spare laptop (swarm-node2)

Date: 2026-10-12
Priority: LOWER than `2026-10-12-pc-to-codex-release-deep-and-blind-diagnostics.md`. Do not start this until the deep stage has finished (Job 1) so the two do not compete for disk, network or your attention. Job 2 diagnostics of that ticket can run before or after this one.

## Goal
Find out what this machine is good for, with numbers, so Chris and I can pick its role: (a) isolated content fetch/extract node, (b) market-data poller, (c) small CPU worker for the swarm, or (d) nothing useful.

## Machine
- Login: `thinkpad@192.168.68.71`, SSH key login from the main PC (no password). Chris reserved this address in Deco. If the connection fails, check `ip a` is not the problem by pinging first; do not guess other addresses.
- Lenovo IdeaPad 1 15AMN7: Ryzen 3 7320U (4 cores / 8 threads), 8 GB RAM (about 5.7 GB usable), NVMe, Wi-Fi only (wlp2s0), Ubuntu Server 26.04.1, updates already applied.
- No GPU use. CPU only.

## Rules
- You may install packages on the laptop with apt/pip (build tools, python venv, llama.cpp). Put everything under `~/assess/` on the laptop so it can be removed.
- Do NOT change SSH config, firewall, network config, user accounts, or Wi-Fi settings. Do NOT store passwords or API keys anywhere.
- Allowed small server tweak, apply it and record it in the report: set lid-close to do nothing (`HandleLidSwitch=ignore`, `HandleLidSwitchExternalPower=ignore` in `/etc/systemd/logind.conf`, restart logind) so the node does not sleep when the lid is shut. If it would drop the SSH session, do it last.
- On the main PC do not change repo code. Save raw logs and the report only under `comms/` (raw logs in `comms/artifacts/laptop-assessment/`).
- Stop early and report if the laptop overheats (above 90 C), runs out of memory repeatedly, or SSH drops more than twice.
- Total budget about 30 minutes of active testing. Report what you finished if you run out of time.

## Tests

### T0 baseline (2 min)
Record: `lscpu`, `free -h`, `df -h`, `uname -r`, `cat /sys/class/thermal/thermal_zone*/temp`, CPU governor, `iw dev wlp2s0 link` (signal and bitrate), and idle load.

### T1 CPU model speed (10 min)
1. Build or download a CPU build of llama.cpp on the laptop.
2. Copy from the main PC `Models` folder the smallest instruct GGUFs available: aim for one around 0.5 to 1B and one around 1.5 to 4B at Q4. If none that small exist, say so and use the smallest. Do not download anything large from the internet without telling Chris in the report.
3. Run `llama-bench` (or equivalent) with 4 threads and with 8 threads: prompt-processing tokens/s at 512 prompt tokens and generation tokens/s at 128 tokens. Record peak RAM (RSS) and whether it swapped.
4. Run one short real prompt end to end through `llama-server` and time a 256-token completion, to catch server overhead.

### T2 fetch and extract batch (10 min)
1. Take 60 distinct URLs cited in recent traces (for example from `apps/forecast/data/cycles/cycle1-run2/traces_quick`, the sources the researcher actually fetched). If the fetch/extract tool in the repo can run standalone, use it; otherwise use a small Python script (requests + a readability/trafilatura-style extractor).
2. Run the same batch at concurrency 1, 4 and 8 on the laptop. Record per concurrency: success rate, median and p95 seconds per page, extracted characters, CPU and RAM use.
3. Run the same batch once from the main PC at concurrency 4 as a comparison.
4. Note any pages that fail only on the laptop.

### T3 network stability (5 min of probes, can overlap T2)
Ping the router and 1.1.1.1 (200 pings each, 0.2 s interval) and record loss and latency percentiles. Run a single download speed test (any reasonable HTTPS file). Record `iw` signal before and after. Compare the same pings from the main PC.

## Report
Write `comms/2026-10-12-codex-to-pc-laptop-assessment.md` with:
1. Tables of the numbers above (not just prose), the exact commands and versions used, and paths to raw logs.
2. A plain-language answer to: tokens/s for each model, pages per minute for fetch at each concurrency, and Wi-Fi loss and latency.
3. A suggested role ranking (a/b/c/d) with the number that justifies each. Treat roughly these as rough lines, not rules: generation under about 5 tokens/s on the 1B model means it is not a useful model worker; fetch success under about 90 percent or page time worse than the main PC by more than 2x means it is not a good fetch node; more than about 2 percent Wi-Fi loss is a stability concern for a poller.
4. Anything surprising (thermal throttling, memory pressure, extractor differences).
5. What you changed on the laptop (including the lid setting) and how to undo it.

Reminder: report evidence, not just summaries. I verify against the raw logs before we decide anything.
