# Ticket: push Local Swarm, then three forecast-app fixes
From PC Claude. To Codex. Chris approved pushing ("push if we need to").

## Part 1: push (do first)
Local Swarm main is 7 commits ahead of origin. Working tree has: modified swarm/tools.py (uncommitted), untracked comms/*.md files, three .bat files, _to_delete/.
1. Show me `git diff swarm/tools.py` in your report and say who changed it and why. Do NOT commit it until I reply (it may be a leftover). 
2. Commit the untracked comms/*.md files as one "docs: comms history" commit. Do not commit _to_delete/, *.bat.j11, or data/ outputs.
3. Run the test suite (cloud-known ~7 min). If green, `git push origin main`. Report the pushed hash.
4. Swarm-Forecast has NO remote and is clean. Do not push it. Chris decides on a remote.

## Part 2: forecast-app fixes (Swarm-Forecast only; no core swarm changes). Use a branch `fix-0` so cycle 1 can be pinned to a tag afterwards.
Defects found in smoke1/pilot60 (see comms/claude-morning-note.md):
A. Extraction polarity: the extraction prompt must say explicitly "probability that the market question resolves YES". Add a code check: if the research text contains an explicit "N% probability/estimate", and the extracted value differs by more than 0.20, re-extract once; if still different, mark the record `inconsistent` and exclude it from picks and bets.
B. No default to 0.5: when research has no findings (empty evidence), output `no_forecast` (probability null, reason recorded). Exclude from gap picking, calibration, and bets, but count them in the report (coverage).
C. Staleness guard: if the market side price is 0.85+ or 0.15- (liquid market confident one way) and the swarm disagrees by more than 0.40, require that the deep pass cites at least one source dated within 30 days that supports the swarm's view; otherwise mark `stale_suspect` and do not bet. Always log the case.
Add tests for A, B, C (use the mock path, no GPU). Update CLI score output to show coverage and the counts of inconsistent / stale_suspect.
Do not run the pilot again. Report: diff summary, tests, commit hash on branch fix-0.
