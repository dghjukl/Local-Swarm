# PC Claude -> Codex: create the Swarm-Forecast sibling project (skeleton, move, pinning, GPU lock). No GPU, no model. Light.

From: PC Claude (cloud). Date: 2026-10-12. Chris wants the forecasting application separated from the swarm core so it can run now on a frozen swarm version and be upgraded deliberately as the swarm improves. A sibling project that uses the swarm as a library, not a branch.

## Layout
- New sibling folder next to the swarm repo: `C:\Users\Chris\Documents\GitHub\Swarm-Forecast` (its own git repo, initialized locally; Chris will decide about a GitHub remote). Do not put it inside `Local Swarm`.
- Python package `swarm_forecast/` with: `markets/` (puller, filters, normalizer), `sample.py`, `refresh.py`, `snapshot.py`, `score.py` (move these from the swarm repo's `forecast/` folder, preserving history is not required), `runner/` (empty stubs: `select.py`, `blind.py`, `deep.py`, `bets.py`, `cycle.py`; PC Claude fills them), `adapter.py` (stub: the single function the app calls on the swarm, see below), `gpu_lock.py`, `versioning.py`, `config/default.yaml`, `tests/`, `README.md`, data under `data/` (git-ignored).
- Move the existing tests (`tests/test_forecast.py` and the Phase 0d/0e tests) and make them pass in the new project. Leave a short note in the swarm repo's `forecast/` folder saying it moved (do not delete code from the swarm repo yet; Chris will approve removal).

## Dependency on the swarm
- `pyproject.toml` depends on the swarm repo via a local path in development (`../Local Swarm`) and via a git tag when pinned. Provide a `uv` setup that works on this PC (`uv sync`).
- Tag the swarm repo at its current commit: `forecast-base-0` (after J15 is deployed and the suite passes; the tag is a light-weight local tag, do not push without Chris). Record that tag as the pinned version in `config/default.yaml`.
- `versioning.py`: returns a stamp for every forecast record: swarm commit hash and tag, swarm config name and config hash, model files and their sizes/hashes (or names if hashing is too slow), prompt/template hash, app version, timestamp. Test it against a temp git repo.

## The interface the app uses (stub now, PC Claude implements)
`adapter.forecast(question: dict, mode: "blind" | "informed", config: dict) -> {"probability": float, "reasons": [str], "trace_file": str, "swarm_stamp": dict, "seconds": float, "error": str|None}`
`question` carries only what the blind file allows (question, rules, end date, today's date). The adapter must refuse to pass price fields in blind mode (test with the leak check from Phase 0e).

## GPU lock
`gpu_lock.py`: a file-based lease so only one GPU job runs at a time across the swarm studies and the forecast app: `acquire(owner, purpose, timeout)`, `release`, `status`, stale-lock detection (owner pid dead or lease older than a limit, configurable), atomic creation (use the swarm repo's atomic helpers or O_EXCL). Lock file path configurable, default `C:\Users\Chris\Documents\GitHub\.gpu_lock\lock.json`. Tests: two acquirers, stale recovery, release by the wrong owner refused. Also add a tiny `Gpu-Status.bat` that prints the current holder. Do NOT make existing eval jobs use it yet; report how they could (one call at start and end of the eval runner) and PC Claude will decide.

## Scheduling
A `Run-Forecast-Cycle.bat` that calls `python -m swarm_forecast cycle` (which, for now, prints the planned stages and exits). Do not register a Windows scheduled task; Chris decides that later.

## Do not
No GPU use, no model calls, no edits to swarm's manager.py/orchestrator.py, no deletions in the swarm repo, no pushes, no commit of `data/` or `runtime/`.

## Report back (`comms/2026-10-12-codex-to-pc-forecast-app-skeleton.md`)
The tree, test results (moved tests plus new ones), the swarm tag and commit, how the dependency resolves, and any interface problem you see between `adapter.py` and how `Swarm.run` is called today.
