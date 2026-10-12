# Ticket (queue item 3): diagnose two forecast-runner defects. READ-ONLY. No code or config changes.
From PC Claude. Run only after pilot60 (item 2) has finished and its report is written.

I verified smoke1 against the raw files. Counts and timings in your report are correct. But the files show two defects:

1. Polarity/extraction mismatch (deep stage). smoke1/deep.jsonl, market 1284655 (Republican wins RI-01): the research_summary ends "My estimate: ~20% probability of YES", and the reasons argue Democratic incumbency holds, yet the extracted probability is 0.95. The paper bet in bets.json (YES at 0.024, stake $1) was therefore placed on a probability that contradicts the swarm's own text.
2. Default-to-0.5 on empty research (blind stage). Market 1284655 blind = 0.50 with reasons "no findings recorded". At 12 pilot rows, 7 of 12 blind probabilities were exactly 0.5 (check the final count). A gap picker then favors the cheapest asks, so ignorance gets selected, which is the "picking easy/cheap" artifact we wanted to detect.

## Deliver (analysis only, from pilot60/ and smoke1/ files)
- For every deep and blind row: probability extracted vs any explicit "~N%" / "N% probability" in research_summary. List mismatches > 0.2 with market ids.
- Count of blind rows with probability exactly 0.5, and of those, how many had empty/no findings. Which of the 2 picked markets (or all picks) came from such rows.
- Whether the extraction prompt or the schema (prompts.py: FORECAST_SYSTEM, extraction_user) states "probability that the market resolves YES". Quote it.
- Timing summary for pilot60: per stage, mean/median/p90 seconds, wall total, extrapolation to a 300-question weekly cycle.
- Do NOT edit code or config. Do NOT rerun. Propose fixes in the report; Chris and PC Claude decide.
