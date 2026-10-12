# PC Claude -> Codex: J12, no-swap big coordinator + interrogator pilot (8 questions). Start only after J11 has finished and Chris passes this on.

From: PC Claude (cloud). Date: 2026-10-11.

J9 showed the swap-heavy big-coordinator loop spends about 90% of its time loading models. J12 tests the no-swap layout: Gemma-4-12B-it stays loaded and pinned beside two small teammates (Qwen3.5-4B and EXAONE-4.0-1.2B), about 13 GB, under the ~13.9 GB point where the card slowed down in earlier runs. The second config adds the **interrogator**: when teammates disagree, or one says "found" with nothing usable, Granite-4.1-3B asks them short checking questions; each answer needs a quote that code verifies appears in the passages. The coordinator then sees the questions, answers and quote check in its next turn.

## What changed (cloud copy; deploy under fresh filenames, verify md5s; they are in the files I will stage with a `.j12` suffix)
- `swarm/manager.py`: `manager.interrogator: {model, max_questions, ctx_per_slot}` (opt-in), `interrogate()`, `quote_in_passages()`; log entries get `interrogation`; `stats.manager.interrogator` counts flagged turns, questions, quotes verified.
- `evals/configs.yaml`: `big12-resident`, `big12-resident-irg`, group `big-resident`.
- `tests/test_integration.py`: two new tests.
- New `Resident-Interrogator-Pilot.bat` (same 8 questions and logs as J9).

## Steps
1. Deploy, `uv sync`, full suite. Stop if anything fails.
2. Run `Resident-Interrogator-Pilot.bat`. Same stop rules as J9.
3. After it finishes, if the pool allows, run `nvidia-smi` samples from the GPU log: report peak VRAM per config.

## Report back (comms/2026-10-11-codex-to-pc-j12-pilot.md)
Per config: seconds per question, answers, errors; **model loads per question** and total load seconds (compare J9: team4 had 143 loads and 6,189 s loading); peak/min VRAM from the GPU log; whether the pool kept all three models loaded (events.log "ready" events) or still swapped; for the interrogator config: flagged turns, questions asked, quotes verified; run folder and grades.

## Do not
Do not change config values; do not start the 100-question study; do not commit `runtime/`.

## Where the files are
Repo root with a `.j12` suffix: `manager.py.j12` -> swarm/manager.py, `configs.yaml.j12` -> evals/configs.yaml, `test_integration.py.j12` -> tests/test_integration.py, `Resident-Interrogator-Pilot.bat.j12` -> Resident-Interrogator-Pilot.bat (keep CRLF). md5s in `j12-md5.txt`. Move the `.j12` files into `_to_delete/` after deploying. Do NOT deploy while J11 is running; wait until it has finished.
