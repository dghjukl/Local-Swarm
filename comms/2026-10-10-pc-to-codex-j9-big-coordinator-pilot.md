# PC Claude -> Codex: J9, big-coordinator pilot (Gemma-4-12B directs; alone vs two sets of teammates). Start when Chris passes this on.

From: PC Claude (cloud). Date: 2026-10-10.

Chris's idea, and the next real trial: does a team of small workers add capability to a big model? Gemma-4-12B-it (7 GB, fits the GPU alone) runs the manager loop. Its teammates are four models in two sets, each set a small and a bigger model:

- set 1: Qwen3.5-4B + Qwen3.5-9B
- set 2: Gemma-4-E4B + Apertus-v1.5-8B

Only one set is on the GPU at a time. The coordinator is no longer pinned, so the pool unloads it while a set works. This is a **pilot of 8 questions**, not the study. I want to see what the swap-heavy loop costs and that it works before spending a day on 100 questions.

## What changed (cloud copy; please deploy under fresh filenames and verify md5s as before)
- `swarm/manager.py`: `manager.pin_coordinator` (default true = old behaviour) and `manager.worker_sets` (list of lists of positions in `workers.team`; with `dispatch: both` the sets answer one after the other, the members of a set side by side).
- `swarm/attempts.py`, `swarm/orchestrator.py`: the vote and plan-stage coordinator calls follow `pin_coordinator`.
- `evals/configs.yaml`: `big12-alone` (Gemma-12B does every step), `big12-team2` (Qwen3.5-4B + Gemma-E4B, one set), `big12-team4` (the two sets above); group `big-coordinator` = [mgr-ex-base, big12-alone, big12-team2, big12-team4].
- `tests/test_integration.py`: new test `test_manager_worker_sets_run_one_after_the_other_and_coordinator_is_unpinned`.
- New `Big-Coordinator-Pilot.bat` (runs `big12-alone` and `big12-team4` on frames-0, 1, 9, 16, 25, 29, 32, 48 with the saved sources from 20261004-2126; GPU and RAM logged every 15 s; toast at the end).

## Steps
1. Deploy, run the full suite. Expect all previous tests plus the new one (91 passed, 1 skipped). Stop and report if anything fails.
2. Run `Big-Coordinator-Pilot.bat`. Nothing else on the GPU. Expect 1 to 3 hours. The models are all on disk (checked: Gemma-4-12B-it, Qwen3.5-4B, Qwen3.5-9B, Gemma-4-E4B-it, Apertus-v1.5-8B).
3. **Stop and report at once** if: the PC freezes or restarts, available RAM falls under 1.5 GB, a question takes over 25 minutes, or the same model-load failure repeats 3 times in a row. Do not retry past the bat's own 3 retries.

## Report back (comms/2026-10-10-codex-to-pc-j9-pilot.md)
- Per config: average seconds per question, number of questions with an answer, any errors or timeouts.
- **Model loads per question** (count the model "ready" events in events.log per question) and the longest single wait for a model load.
- Peak VRAM, peak RAM use, minimum available RAM, peak temperature and power from the logs.
- The run folder name, plus the judge's grades if the harness produced them.
- Anything odd in the traces, e.g. the coordinator unable to load while a set was busy, or a set never finishing.

## Do not
- Do not change worker sets, models or config values to make the pilot pass. Report what happened.
- Do not start the 100-question study. I decide that from the pilot.
- Commit as usual. Do not commit `runtime/`.
