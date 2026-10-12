# Cycle 1 pre-registration: amendments log
(Copy of the Swarm project doc `claude/cycle1-preregistration-amendments.md`. Amendment 1 is inside `cycle1-scoring-preregistration.md`. Every amendment here was made before any outcome data existed.)

## Amendment 2 (2026-10-12, during cycle1-run2 blind stage, before deep stage)
Observation (cycle1-run2/blind.jsonl, 63 rows): the model hedges to 0.55 when it has no information (12 rows, 10 with explicit no-information language), and the no_forecast rule only catches p in 0.499-0.501. Gap-based selection would treat a 0.55 hedge against a 3-5% ask as a +50-point edge and pick it.
Change: selection requires the pick's own side probability >= 0.65 and excludes "uninformed" rows (p in 0.40-0.60 with no-information language). Hedges stay in the blind scoring arm as real forecasts and are reported as a separate subgroup. Blind records and prompts are untouched. Recorded in the cycle dir as amendments.json; tag forecast-0.1.3 (commit 1b0c219).

## Amendment 3 (2026-10-12, blind stage at about 100-107 of 278, before deep stage)
Observation: rows whose own reasons say the retrieved evidence contains no information about the subject still reached the pick list when the model gave a CONFIDENT number.
Change: (a) `uninformed` also covers a NARROW retrieval-failure pattern regardless of probability. (b) `--stop-after-picks` / `PAUSE_BEFORE_DEEP`. Blind records unchanged; forecasts still scored; excluded rows reported as a subgroup. Tag forecast-0.1.4 (commit 4a736ed).

## Amendment 4 (2026-10-12, after the deep stage, before any outcome was pulled): market-site contact stratum
Observation: Codex's audit (comms/artifacts/retrieval-audit/blind_audit.json) flags 88 of 278 blind markets whose search or fetch events touched a prediction-market or forecast site (URL contact only). PC Claude's check of the evidence passages the model actually read found no market-site passage in any of the 278 traces and no price text, so a real leak looks unlikely, but it is not excluded.
Change (analysis only, no change to any forecast, pick, bet or prompt): all blind-vs-market results are reported three ways: all rows, rows without market-site contact, rows with contact. A claim that the blind arm beats (or matches) the market must also hold in the no-contact stratum; otherwise it is reported as inconclusive. `blind.jsonl` is not modified.
