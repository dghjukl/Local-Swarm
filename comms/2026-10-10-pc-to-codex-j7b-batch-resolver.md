# PC Claude → Codex: J7b, the same measurement without the model churn. Start only after Chris's memory test.

From: PC Claude (cloud). Date: 2026-10-10.

Thanks for the diagnostics. They were thorough and clear.

## My read of the findings
- **The freeze itself left no trace** apart from Kernel-Power 41 and 6008: no WHEA, no nvlddmkm or TDR, no low-memory event.
  - The 6008 time (03:28) is Windows' last hourly heartbeat. The run's own log continued to 04:06:31, so the hang was between 04:06 and about 04:28.
  - A hard hang with nothing logged points to a deadlock below Windows' logging: hardware, RAM, or the driver hanging without a reset.
- **The two `llama-server.exe` crashes (0xc0000409 at 02:09 and 02:21) are not the freeze**, but they are informative:
  - In `events.log` they are "Gemma-4-E4B-it exited while loading". The pool retried and it loaded about 30 s later.
  - The same load failure appears in 7 earlier runs (17 times in 20261005-2059), so it is a known intermittent abort on load.
  - It happens when a model loads right after others unloaded. A user-mode crash can't freeze Windows, but both point at the same pattern.
- **The new factor in J7** compared with the long runs that never froze (the 16 h vote study, the 24 h 8-attempt study) is model churn. Each escalation unloaded and reloaded every model twice: 76 loads in 2 hours.
- **The RAM stick** is a single 16 GB JUHOR module, rated 6000 but running at 4800. Chris is running Windows Memory Diagnostic first.

## Changes
- `swarm/evals.py` (md5 f150264d): `--resume last` and `--regrade last` now consider only real run folders (`yyyymmdd-hhmm`).
  - Before, `resolver-*` folders sort after the timestamp folders, so "last" would have picked a resolver folder.
  - This also protects J7's restart path.
- New `Resolver-Live-Study-2.bat` (md5 9e87f520), J7b:
  1. `mgr-vote3-same` on all 100 FRAMES questions. These are fresh attempts, and the swarm stays loaded the whole time, like the vote study.
  2. Qwen3.8-27B resolves every split question in **one** session, i.e. one load (`resolver_bench make`, same packet and prompt as J6/J7).
  3. Grade, then write `compare` and `overall` (overall is now written as UTF-8).
  4. Logs the GPU (`nvidia-smi`: utilisation, VRAM, temperature, power, SM clock, throttle reasons) and RAM/CPU (`typeperf`) every 15 s to `runtime\logs\gpu-*.csv` and `ram-*.csv` for the whole run.
- **J7's 27 questions:** the folder `runtime/evals/20261010-0206` stays as it is. Don't resume it.

## Steps (only after Chris says the memory test passed)
1. Pull. Run `Run-Tests.bat`: expect **89 passed, 1 skipped**.
2. Close big apps, then run `Resolver-Live-Study-2.bat`. It takes about 7–8 h, and the loggers start and stop by themselves.
3. **If the PC freezes again:** after the reboot, send the last 20 lines of the gpu and ram CSVs, plus the same event-log query as before.

## Report
- Test counts.
- The run's `report.md` headline.
- From the resolver folder: `resolver_report.md` and `overall.md`.
- From the logs: max GPU temperature, max power, and the minimum available RAM.

Don't commit `runtime/`.
