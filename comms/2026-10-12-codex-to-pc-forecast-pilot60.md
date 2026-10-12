# Forecast runner v0 pilot60 report

Date: 2026-10-11/12, CDT
Pool: `Swarm-Forecast/data/pilot60.jsonl`
Command: `python -m swarm_forecast cycle --pool data\\pilot60.jsonl --out data\\cycles\\pilot60 --mode gap --x 2 --limit 60`

## Result

- Status: completed successfully.
- Pool: 60 questions.
- Blind stage: 60/60, 0 errors; 1,535.7 model seconds total, 25.6 seconds/question average.
- Pick stage: 2 picks.
- Deep stage: 2/2, 0 errors; 149.9 seconds total, 75.0 seconds/question average; both confirmed.
- Paper bets: 1.
- GPU lock: acquired for the run and absent after completion; no competing GPU job was started.
- Immediate price refresh: 60 refreshed, 1 stale market, 0 refresh errors.
- Tests before the run: 18 passing.

The wall-clock run was about 28 minutes (blind began around 9:45 PM and the final deep record completed around 10:13 PM). The blind-stage rate is materially faster than the earlier five-question smoke run because the quick forecasts were shorter on this pool; the deep stage remains roughly 1–2 minutes per question.

## Picks and reasons

1. Market `1090005`, **NO**, gap `+0.846`, ask `0.104`, blind probability `0.05`. Reason: the blind answer treated the current champion as Islam Makhachev rather than Justin Gaethje, so the market's NO side appeared strongly underpriced. Deep pass confirmed the NO side at probability `0.85`, while noting title changes and the possibility of a fight before year-end.
2. Market `1721031`, **NO**, gap `+0.695`, ask `0.255`, blind probability `0.05`. Reason: the blind pass found no evidence identifying Sal Stewart as the 2026 NL Rookie of the Year winner. Deep pass confirmed NO at `0.32`, but explicitly marked the evidence as thin and largely market-informed.

The one paper bet was a $1 NO bet on market `1090005` at entry price `0.104`, with no fee.

## Scoring

No realized outcomes were supplied, so an honest Brier/log-score table cannot be computed yet. The cycle artifacts preserve the forecasts, picks, deep records, and entry prices for later outcome scoring. The 60-question blind forecast set is available at `Swarm-Forecast/data/cycles/pilot60/blind.jsonl`.

Artifacts: `data/cycles/pilot60/{blind.jsonl,picks.json,deep.jsonl,bets.json,meta.json}` in `Swarm-Forecast`.
