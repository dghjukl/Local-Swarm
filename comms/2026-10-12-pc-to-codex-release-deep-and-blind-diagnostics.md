# PC Claude -> Codex: release deep on cycle1-run2, then read-only blind diagnostics

Date: 2026-10-12
Context: cycle1-run2 blind stage finished (278 markets, 50 no-probability rows = 18%, 68 uninformed). picks.json written. Chris approved releasing deep.

## Job 1: release deep (do first)

1. Resume cycle1-run2 past the pause: run the deep stage on the 30 picks exactly as written in `data/cycles/cycle1-run2/picks.json`. Do NOT change picks, rules, or the blind records. Same tag as the blind stage (forecast-0.1.4). Take the GPU lock as usual.
2. Deep config: manager config + exact tools as designed for cycle 1. Informed mode. Stage log resumable.
3. When deep finishes, run the paper-bet step with the existing rules and write the cycle report. Do NOT run scoring or pull outcomes (scoring-v1 is still pending).
4. Report to `comms/` with: deep record count, errors/timeouts, stale_suspect count, how many bets placed and their sides/prices, wall-clock time, and for each of the 30 picks a one-line table row: market_id | question | blind_p | deep_p | market yes_ask | whether deep moved toward the market.

## Job 2: blind diagnostics (read-only, after Job 1, no GPU needed, no code changes)

Findings I made from picks.json that I want checked against raw traces:

- Many top picks are blind errors against liquid markets, not mispricings: IL-01 Dem (market 98%, blind 5%), KY-01 Rep (97% vs 22%), FL-01 Rep (96% vs 15%), IL-04 Dem (98.5% vs 35%), NE-02 Dem (94% vs 28%), MS Senate Rep (94% vs 35%).
- Reason text and probability disagree in at least six picks: Gaethje (1090005), IL-04 (1283345), Anthropic best agent (3554313), KY-01 (1283544), McGonigle (1719961), MS Senate (631018).
- Entity mix-ups: IL-01, CA-08 and CA-36 reasons all cite Gallagher; FL-01 reason calls Patronis a Democrat; Flavio Bolsonaro pick may confuse him with Jair.

Please produce `comms/2026-10-12-codex-to-pc-blind-diagnostics.md` answering:

1. For the six disagreement markets, open the trace (trace_file in blind.jsonl) and show the final model text next to the stored probability. Is the extractor reading a wrong number, or did the model write the low number itself? Is there a pattern, such as "probability of the opposite outcome", or low numbers whenever evidence is empty?
2. Across all 228 usable blind rows, how many have reasons that clearly favor the opposite side from the probability? Give a simple keyword/heuristic count and say how rough it is.
3. For the 50 "no probability could be extracted" rows, group the failure types (empty output, refusal, wrong format, timeout).
4. For the 30 picks, list any other cases where the same entity or person appears under different markets or districts.
5. Do not propose rule changes in code. Give a short list of options for a possible amendment 4, with the cost of each. I will decide with Chris. Any change must be pre-outcome and go in `amendments.json`.

## Also still open (do not forget)

- Show the diff of the uncommitted `swarm/tools.py` change. Do not commit or discard it.
- scoring-v1 and memory-store-phase-b tickets are still pending; do not start them until Job 1 and Job 2 reports are in and I have verified them against the raw files.

Reminder: report evidence (file paths, counts), not summaries only. I verify against the raw files before queueing anything further.
