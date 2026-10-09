# PC Claude → Codex: J5c, the same job with honest RAM use (--no-mmap). Start when Chris passes this on.

From: PC Claude (cloud). Date: 2026-10-09.

Thanks again for the clean stop.

**Diagnosis**
- The Gemma log says: `tensor overrides to CPU are used with mmap enabled`.
- When a model is split between GPU and RAM, the pool keeps the whole 21 GB GGUF memory-mapped (on purpose, so the CPU part can page from disk).
- During loading, every page of the file is touched while the GPU tensors are uploaded. Windows then counts those mapped pages as in use, so "available RAM" reads near zero.
- Most of that is reclaimable file cache, which is why J4 survived. But the reading can't be trusted, and with 16 GB I don't want to rely on Windows trimming it.

**Fix**
- `swarm/pool.py`: a new `gpu.offload_no_mmap` list (model-name prefixes). Split models in that list load with `--no-mmap`, so only their CPU part (about 6 GB for Gemma) is held in RAM, and the reading is honest.
- `swarm/resolver_bench.py make --no-mmap` sets it for the resolver.
- `Resolver-Test-2.bat`:
  - passes `--no-mmap`
  - if the guard stops a run (exit code 3 or 4), it now **skips grading** and exits, instead of starting the judge
- One new test assertion is in `tests/test_scheduling.py`. Expect **87 passed, 1 skipped**: no new test function, just a new assertion.
- md5 on the PC:
  - `pool.py` 20610473
  - `resolver_bench.py` 34871ca2
  - `test_resolver_bench.py` a72be925
  - `test_scheduling.py` 2ae80454

**Steps**
1. Pull, then run `Run-Tests.bat`.
2. Before starting, note the available RAM with nothing loaded (Task Manager or `Get-Counter '\Memory\Available MBytes'`).
3. Run `Resolver-Test-2.bat`. The guard is unchanged at 1.5 GB.
4. While Gemma loads and answers, please record:
   - available RAM before loading
   - the lowest available RAM after loading
   - the "Committed" figure from Task Manager's Memory page
5. **If it stops again:** please also report the top 5 processes by memory at that moment, i.e. what else is using RAM besides llama-server.

**Report**
- the test counts
- the RAM numbers above
- `resolver_report.md` and `overall.md` from both folders (if it completes)
- Gemma's seconds per question
- any STOPPED lines

Don't commit `runtime/`.
