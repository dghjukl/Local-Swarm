# Forecast app monorepo move report

## Result

The sibling application was copied into `apps/forecast/`; the original `C:\Users\Chris\Documents\GitHub\Swarm-Forecast` repository was left untouched as a backup. Forecast data was copied locally under `apps/forecast/data/`, and the app's `.gitignore` excludes it; no data files were staged.

Import commit: `1609e83` (`forecast: import Swarm-Forecast app into apps/forecast`)
Import tag: `forecast-base-0-import`
Frozen app tag: `forecast-0.1`
Pushed branch: `fix-0`

## Pinning and runner

`apps/forecast/run_pinned.bat` creates or reuses a detached worktree at `..\\..\\Local Swarm_pinned\\<tag>`, places that checkout first on `PYTHONPATH`, and then runs the forecast module from `apps/forecast`. The app therefore imports the swarm from the pinned checkout rather than the live working tree. The forecast stamp records the pinned commit/tag. `config/default.yaml` retains the frozen `forecast-base-0` commit and the shared GPU lock path.

## Tests

- Forecast tests from the new location: **21 passed**.
- Local Swarm full suite after dependency sync: **119 passed, 1 skipped, 1 warning**.
- The imported app already contained the previously validated extraction/no-findings/staleness fixes from the sibling `fix-0` work, so the monorepo `fix-0` branch is a pushed verification branch at the frozen import state rather than a duplicate patch series.

## Pushes

- Local Swarm `main`: pushed through import commit `1609e839dc0c75d9eb329405a22fadf882ad816e`.
- `forecast-base-0-import`: pushed.
- `forecast-0.1`: pushed at `1609e83`.
- `fix-0`: pushed.

The pre-existing uncommitted `swarm/tools.py` change, `comms/NIGHT_QUEUE.md` edit, scripts, and scratch files remain outside the commits.
