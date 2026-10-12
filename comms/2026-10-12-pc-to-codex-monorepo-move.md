# Ticket: move Swarm-Forecast into the Local Swarm repo (supersedes the Swarm-Forecast addendum)
From PC Claude. To Codex. Chris approved: one repo, so everything is backed up on GitHub together. No separate Swarm-Forecast GitHub repo.

## Order (stop and report if any step fails)
1. Do Part 1 of 2026-10-12-pc-to-codex-push-and-forecast-fixes.md first (swarm/tools.py diff report, comms docs commit, tests, push Local Swarm main). Do not move anything until that push is done and reported.
2. Move: copy the contents of the Swarm-Forecast working tree (not its .git) into `Local Swarm/apps/forecast/`, so the package is `apps/forecast/swarm_forecast/`, with its tests, config, README and .gitignore. Keep the old Swarm-Forecast folder and its git history UNTOUCHED as a backup. Do not delete anything.
   - Copy data/ (smoke_pool, pilot60, cycles, samples) to `apps/forecast/data/` but make sure data/ is git-ignored. Verify with `git status` that no data files are staged.
   - Do not touch the old `forecast/` folder at the repo root (Phase 0 pipeline). Chris approves its removal later.
3. Fix paths: config/default.yaml (gpu_lock path stays the shared one under GitHub\.gpu_lock), docs, CLI examples (`cd apps\forecast` then `python -m swarm_forecast ...`), and the pinned swarm. Currently the app pins the swarm by tag/commit in config. Verify HOW the runner loads the swarm code (which folder it imports). Requirement: a cycle must run from a pinned checkout (git worktree at the tag), so editing the live folder cannot change a run in progress. If that is not already how it works, add `apps/forecast/run_pinned.bat <tag> <args>` that creates or reuses a worktree `..\Local Swarm_pinned\<tag>` and sets the swarm root for the runner. Record the swarm commit in meta.json (already stamped).
4. Run the forecast tests from the new location. Expect the same 18 passing (plus whatever Part 2 adds later). Also run the swarm tests quickly to confirm nothing broke (the cloud-known suite is ~7 min; run it once).
5. Commit as "forecast: import Swarm-Forecast app into apps/forecast" (original 3 commits are described in the message; history is kept in the old folder). Push to origin main. Tag the import `forecast-base-0-import`.
6. Then do Part 2 (the three forecast fixes) on branch `fix-0` inside the monorepo at apps/forecast. Merge, tag `forecast-0.1` on the whole repo (this tag freezes swarm and app together).

## Report
Commit/push hashes, test counts before and after the move, how the runner loads swarm code (and whether run_pinned.bat was added), the final git status (clean?), and the file count/size pushed. Update the cycle-1 ticket paths mentally: all `data\cycles\...` paths are now under `apps\forecast\`.
