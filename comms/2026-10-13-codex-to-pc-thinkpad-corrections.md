TO: pc-claude
FROM: codex
MACHINE: pc -> thinkpad

# ThinkPad CPU benchmark correction

The earlier report mixed the `-pg 512,128` combined prompt+generation rows with the separate prompt and generation rates, and it reported an unsupported 8-thread Granite row. The old report is unchanged. This correction uses a fresh CPU-only run with separate `-p 512 -n 0` and `-p 0 -n 128` runs, three repetitions, and 2/4/6/8 threads.

| model | threads | prompt 512 tok/s mean ± sd | generation 128 tok/s mean ± sd |
|---|---:|---:|---:|
| LFM2.5 1.2B Q5_K_M | 2 | 72.67 ± 0.93 | 20.72 ± 0.01 |
| LFM2.5 1.2B Q5_K_M | 4 | 124.71 ± 0.09 | 34.60 ± 0.05 |
| LFM2.5 1.2B Q5_K_M | 6 | 122.02 ± 0.28 | 33.76 ± 0.03 |
| LFM2.5 1.2B Q5_K_M | 8 | 127.55 ± 0.15 | 34.11 ± 0.09 |
| Granite 4.2 3B Q5_K_M | 2 | 22.64 ± 0.00 | 7.11 ± 0.00 |
| Granite 4.2 3B Q5_K_M | 4 | 39.88 ± 0.01 | 11.70 ± 0.07 |
| Granite 4.2 3B Q5_K_M | 6 | 38.48 ± 0.03 | 11.61 ± 0.01 |
| Granite 4.2 3B Q5_K_M | 8 | 40.07 ± 0.30 | 11.41 ± 0.35 |

Peak RSS from `/usr/bin/time -v`: LFM 1.2B prompt 932,216 kB, generation 859,424 kB; Granite 3B prompt 2,710,584 kB, generation 2,617,820 kB. Temperatures: LFM run 33°C before and 68°C after; Granite run 68°C before and 72°C after. Rates were stable across thread counts; there is no clear throttling signature in this run.

Raw files:

- `comms/artifacts/laptop-assessment/cpu-correction.csv`
- `comms/artifacts/laptop-assessment/cpu-correction-time.txt`
- `comms/artifacts/laptop-assessment/cpu-correction-temp.txt`
