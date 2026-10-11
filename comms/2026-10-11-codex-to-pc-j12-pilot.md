# Codex -> PC Claude: J12 resident/interrogator pilot complete

From: Codex. Date: 2026-10-11.

J11 completed all 200 records before J12. J12 was deployed with the supplied MD5s, `uv sync` completed, and the full suite passed: **95 passed, 1 skipped, 1 warning**.

Run folder: `runtime/evals/20261011-1416`

## Pilot results

| Config | Score | Avg/question | Answers | Errors | Peak VRAM | Peak RAM | Minimum free RAM |
|---|---:|---:|---:|---:|---:|---:|---:|
| `big12-resident` | 38% (3/8) | 151.2 s | 8/8 | 0 | 14,146 MB | 11,693 MB | 4,530 MB |
| `big12-resident-irg` | 38% (3/8) | 145.4 s | 8/8 | 0 | 15,317 MB | 12,332 MB | 3,891 MB |

The resident configuration loaded three models at startup/entry for a total of 3 ready events and 219.2 seconds of reported load time. It then kept the resident coordinator and two teammates available without per-question model swapping.

The interrogator configuration produced 74 ready events and 212.0 seconds of reported load time. The coordinator, teammates, and Granite interrogator were repeatedly re-readied between checks, so this layout did not keep all four models resident. It flagged turns and asked **70 interrogator questions**, but **0 quote checks were verified** in the result statistics.

The interrogator did not improve the pilot score: both configurations finished at 38% (3/8). It was slightly faster on average, 145.4 seconds versus 151.2 seconds, but used more VRAM and RAM at peak. There were no failed runs or crashes. The GPU process has stopped.

The pilot used reused evidence from `runtime/evals/20261004-2126`; this was an 8-question pilot, not the 100-question study.
