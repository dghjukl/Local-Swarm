# PC Claude -> Codex: J11, search A/B: entity-open step + shorter-query retry. Start when Chris passes this on (after J10 is fine to run in parallel; this one needs the GPU alone).

From: PC Claude (cloud). Date: 2026-10-10.

Offline analysis of J7b: 59% of the articles FRAMES lists are never reached by the team, and 63% of those are named in the question or in a passage the team already has. Picking is not the problem (1% lost). This job tests two search changes on the 100-question set.

## What changed (cloud copy; deploy under fresh filenames, verify md5s)
- `swarm/tools.py`: new `wikipedia_titles(titles, skip_urls)` opens named Wikipedia articles directly (redirects followed; falls back to the top search hit).
- `swarm/manager.py`: opt-in `manager.open_entities` (coordinator may name up to 2 article titles in a new `open` field per turn) and `manager.short_retry` (if a search returns nothing and has over 4 words, retry once with its 4 key words). Both default off. Log entries record `open`.
- `evals/configs.yaml`: `mgr-ex-base-open` and group `search-open` = [mgr-ex-base, mgr-ex-base-open].
- `tests/test_integration.py`: two new tests.
- New `Search-Open-AB.bat` (both configs, 100 questions, saved sources 20261004-2126, GPU/RAM logs, toast).

## Steps
1. Deploy, run the full suite (expect all passing). Stop and report if anything fails.
2. Run `Search-Open-AB.bat`. Nothing else on the GPU. Expect about 4 to 5 hours. Same stop rules as J9 (freeze, RAM under 1.5 GB available, question over 25 min).
3. Afterwards, run `python runtime/analysis/cand_check3.py runtime/evals/<RUN>` on the new run for each config and include the output.

## Report back (comms/2026-10-10-codex-to-pc-j11-search-ab.md)
Run folder, grades per config (judge recheck as configured), seconds per question, how many opens the coordinator asked for and how many returned an article, how many short retries fired and how many found something, the cand_check3 output, any errors.

## Do not
Do not change config values; do not start other GPU jobs; do not commit `runtime/`.

## Where the files are
Staged in the repo root with a `.j11` suffix: `manager.py.j11` -> swarm/manager.py, `tools.py.j11` -> swarm/tools.py, `configs.yaml.j11` -> evals/configs.yaml, `test_integration.py.j11` -> tests/test_integration.py, `Search-Open-AB.bat.j11` -> Search-Open-AB.bat (keep CRLF). md5s are in `j11-md5.txt`. Remove the `.j11` files after deploying.
