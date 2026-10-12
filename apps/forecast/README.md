# Swarm-Forecast

Forecast application for the Local Swarm monorepo. The original sibling repository remains outside this repo as a backup; this copy is the app used by the monorepo.

Run the app through `run_pinned.bat forecast-base-0 cycle ...`. It creates or reuses a detached worktree at `..\\..\\Local Swarm_pinned\\forecast-base-0`, links the existing local `Bin` and required model directories without copying model files, puts that frozen checkout first on `PYTHONPATH`, and records its commit/tag in each forecast stamp.

The app imports the swarm from the pinned worktree at runtime; editing the live monorepo cannot silently change a running forecast cycle.
