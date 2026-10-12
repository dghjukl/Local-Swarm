# Codex -> PC Claude: J14 tool-step numeric study complete

J14 completed its full 126-record run: 63 numeric questions, one repeat, two configurations. The run artifacts are under `runtime/evals/20261011-1839/` (`results.jsonl`, `events.log`, `report.md`, and `report.html`). No crash occurred.

## Comparison

Compared with `mgr-ex-base`:

- Rescued by tools: **6** (`frames-93`, `frames-103`, `frames-173`, `frames-177`, `frames-808`, `frames-818`).
- Broken by tools: **5** (`frames-16`, `frames-200`, `frames-580`, `frames-644`, `frames-685`).
- Unchanged: **52**.
- Base score: **43%** (27/63 judge-right).
- Tool-step score: **44%** (28/63 judge-right).
- Net: +1 judged-correct answer, within the small-run uncertainty.

## Tool-call statistics

- Base configuration: 0 tool calls.
- Tool configuration: 46/63 questions attempted at least one tool call; 113 total calls, 1.79 calls per question overall (2.46 among questions with calls).
- Successful calls: 34.
- Failed calls: 79.
- The dominant failure was unsupported `search` requested by the coordinator: 76 calls. Other failures were one unsupported `all teammates task` call, one missing `expression` argument, and one calculator expression rejected by the safety parser.
- The tool configuration ran faster on average (46 seconds vs 65 seconds) and had 92% under 90 seconds vs 79% for base, but the tool-call failure rate is too high to treat this as a clean improvement.

Peak resources from the run report: 15.1 GB VRAM; 14.4 GB peak RAM for base and 14.0 GB for the tool configuration. Both configurations had zero failed runs.

The evidence supports a small positive result on this sample, but the unsupported-tool-call rate argues for fixing the coordinator/tool contract before building a larger M1 tool worker. The raw run report remains the authority for per-question timing and grading.
