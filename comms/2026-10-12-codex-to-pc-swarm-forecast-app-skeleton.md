# Codex -> PC Claude: Swarm-Forecast skeleton complete

The sibling application is at `C:\Users\Chris\Documents\GitHub\Swarm-Forecast` as its own local Git repository. It has not been pushed or given a remote.

## Local Swarm pin

- Local tag: `forecast-base-0`
- Tagged commit: `eb77860a5fbbbb211b609b94069a1515e71bf624`
- The tag is local only. The only Local Swarm working-tree addition was `forecast/README.md`; the original forecast code remains in place and was not deleted.

## Sibling tree

- `swarm_forecast/markets/`: copied market pullers, normalizers, filters, and category puller.
- `swarm_forecast/snapshot.py`, `score.py`: copied forecast storage/scoring code.
- `swarm_forecast/sample.py`, `refresh.py`: explicit placeholders for the later runner work.
- `swarm_forecast/runner/{select,blind,deep,bets,cycle}.py`: stage stubs; `cycle` prints the planned stages.
- `swarm_forecast/adapter.py`: one-function boundary stub with blind price-field rejection.
- `swarm_forecast/gpu_lock.py`: atomic lease, stale recovery, status, owner-checked release.
- `swarm_forecast/versioning.py`: commit/tag/config/model/prompt/app timestamp stamp.
- `config/default.yaml`: records the pinned tag and commit.
- `Run-Forecast-Cycle.bat`, `Gpu-Status.bat`, `pyproject.toml`, `uv.lock`, and ignored `data/`/`runtime/`.

The copied forecast test plus new adapter, lock, stale-recovery, and versioning tests pass: **7 passed**. `python -m swarm_forecast cycle` prints all four planned stages. `uv lock` resolves the local `../Local Swarm` dependency; offline `uv sync --dev` reached dependency installation but was blocked only because the uncached `pyarrow` wheel was unavailable offline.

## Interface note

The current swarm has `Swarm.run(question, emit, force_research=False, prepared=None, save_dir=None)`, but construction requires a config, `ModelPool`, model cards, and optional research client. Its result is a run/trace dictionary rather than the forecast contract `{probability, reasons, trace_file, ...}`. PC Claude’s adapter will need to own that construction and map the final swarm answer/trace into the stable forecast result; the skeleton deliberately does not guess at that mapping.
