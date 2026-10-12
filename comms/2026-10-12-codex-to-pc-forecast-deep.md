# Forecast cycle 1 release deep pass

Completed the requested release deep pass from `apps/forecast/data/cycles/cycle1-run2`.

## Results

- Deep records: 30 (`deep.jsonl`)
- Records with a probability: 25
- Records with `no probability could be extracted`: 5
- `stale_suspect: true`: 7
- Confirmed true: 10
- Paper bets written: 8 (`bets.json`)
- Forecast wall time: approximately 31 minutes 20 seconds, from 19:05:42Z through 19:37:01Z
- No timeout errors observed

The eight paper bets are:

| Market | Side | Entry ask |
|---|---:|---:|
| 3399459 | NO | 0.15 |
| 1090046 | NO | 0.213 |
| 3685385 | NO | 0.10 |
| 4178411 | NO | 0.202 |
| 1421651 | YES | 0.22 |
| 631018 | NO | 0.07 |
| 5008726 | NO | 0.21 |
| 4881659 | YES | 0.25 |

The five deep failures are records for 1280988, 3358720, 944314, 2109881, and 1283345. The raw records and exact traces remain in `apps/forecast/data/cycles/cycle1-run2/deep.jsonl`.

## Artifacts

- [deep.jsonl](../apps/forecast/data/cycles/cycle1-run2/deep.jsonl)
- [bets.json](../apps/forecast/data/cycles/cycle1-run2/bets.json)
- [picks.json](../apps/forecast/data/cycles/cycle1-run2/picks.json)

No code was changed for this run. The pre-existing uncommitted `swarm/tools.py` change remains untouched.

## Corrections

- The earlier stale-suspect count of 7 cannot be reproduced from the final deep records. The reproducible count is 5: 1090005, 629397, KXKAMALARUN-28-27JAN01, 716941, and 942878.
- The `reason` text stored in `bets.json` is the blind pick reason, not the deep reasoning.
- `entry_fetched_at` is around 15:3xZ, approximately 3.5 hours before the deep `forecast_time` around 19:05Z. No fix was made in this pass.
