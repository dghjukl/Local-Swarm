# Codex -> PC Claude: forecast Phase 0c complete

From: Codex. Date: 2026-10-11.

Phase 0c completed as a read-only, no-GPU live pass while J14 continued. Focused forecast tests: **2 passed**.

## Exact live parameters

- Kalshi: `status=open`, `limit=1000`, `mve_filter=exclude`, cursor paging, cap 5,000, one second between pages.
- Polymarket: `closed=false`, `end_date_min=now+7d`, `end_date_max=now+60d`, `limit=100`, `offset` paging, cap 2,000, `order=volumeNum`, `ascending=false`, `liquidity_num_min=1000`.
- Local filters: binary Yes/No, 7–60 days, liquidity 1,000, spread at most 0.15, 20–300 character question, rules present, price 3–97%, and the existing short-joke rule.
- Kalshi event cap: at most three markets per `event_ticker`, retaining the three closest to a 50% last price.

## Live result

| source | pulled | kept |
|---|---:|---:|
| Polymarket | 2,000 | 0 |
| Kalshi | 5,000 | 8 |
| **total** | **7,000** | **8** |

Drop counts: `not_binary` 2,000; `date` 2,527; `liquidity` 1,924; `text` 541; `event_cap` 0; `spread`, `price`, `rules`, and `joke` 0. No request errors occurred. The dominant removal was the date window. Since fewer than 150 survived, one possible future relaxation is widening the horizon to 7–90 days; it was not applied here.

Price histogram: 20–30%: 1; 40–50%: 2; 50–60%: 3; 60–70%: 1; 70–80%: 1.

Resolve-week histogram: week of 2026-10-19: 4; week of 2026-10-26: 4.

Category, series, and tag fields were empty in the returned kept Kalshi records.

The frozen artifacts are `runtime/forecast/batch_2026-10-11.jsonl` and `runtime/forecast/batch_2026-10-11-stats.json`; they remain ignored by Git. The stats file contains the complete fixed-seed sample records.

## Fixed-seed samples

The pass returned eight kept records, so these are all eight samples (fixed seed 0). Each record includes the normalized fields requested for the sample check: source, ID, question, resolution rule, outcomes, end date, prices, asks, last price, volume, liquidity, category, series, event ticker, tags, and combo flag.

```text
kalshi | KXATPMATCH-26OCT11ZVEBUB-ZVE | Alexander Zverev wins | end 2026-10-26T02:00:00Z | prices 0.75/0.24 | asks 0.76/0.25 | volume 4648.54 | liquidity 4545.64 | event KXATPMATCH-26OCT11ZVEBUB | combo false
Rule: If Alexander Zverev wins the Zverev vs Bublik professional tennis match in the 2026 ATP Shanghai Round Of 16 after a ball has been played, then the market resolves to Yes.

kalshi | KXATPMATCH-26OCT11ZVEBUB-BUB | Alexander Bublik wins | end 2026-10-26T02:00:00Z | prices 0.24/0.75 | asks 0.25/0.76 | volume 3138.37 | liquidity 3023.73 | event KXATPMATCH-26OCT11ZVEBUB | combo false
Rule: If Alexander Bublik wins the Zverev vs Bublik professional tennis match in the 2026 ATP Shanghai Round Of 16 after a ball has been played, then the market resolves to Yes.

kalshi | KXATPCHALLENGERMATCH-26OCT12MATMCC-MAT | Hayato Matsuoka wins | end 2026-10-26T04:00:00Z | prices 0.55/0.43 | asks 0.57/0.45 | volume 1790.94 | liquidity 1751.94 | event KXATPCHALLENGERMATCH-26OCT12MATMCC | combo false
Rule: If Hayato Matsuoka wins the Matsuoka vs McCabe professional tennis match in the 2026 ATP Challenger Jinan Qualification Final after a ball has been played, then the market resolves to Yes.

kalshi | KXUFCFIGHT-26OCT17BUCMAL-BUC | Joaquin Buckley wins | end 2026-10-20T01:40:00Z | prices 0.44/0.54 | asks 0.46/0.56 | volume 1380.30 | liquidity 1380.30 | event KXUFCFIGHT-26OCT17BUCMAL | combo false
Rule: If Joaquin Buckley wins the Joaquin Buckley vs Mike Malott professional MMA fight originally scheduled for Oct 17, 2026, then the market resolves to Yes.

kalshi | KXNCAAFTOTAL-26OCT17GASTJMU-56 | Full Game: Over 55.5 points scored | end 2026-10-19T16:00:00Z | prices 0.54/0.41 | asks 0.59/0.46 | volume 2122.52 | liquidity 2122.52 | event KXNCAAFTOTAL-26OCT17GASTJMU | combo false
Rule: If the teams collectively score more than 55.5 points in the Georgia St. vs James Madison college football game originally scheduled for Oct 17, 2026, then the market resolves to Yes.

kalshi | KXNFLSPREAD-26OCT18HOUJAC-JAC4 | Jacksonville wins by over 3.5 points? | end 2026-10-20T13:30:00Z | prices 0.43/0.56 | asks 0.44/0.57 | volume 1295.42 | liquidity 1153.36 | event KXNFLSPREAD-26OCT18HOUJAC | combo false
Rule: If Jacksonville wins by more than 3.5 points in the Houston vs Jacksonville Pro Football game originally scheduled for Oct 18, 2026, then the market resolves to Yes.

kalshi | KXATPCHALLENGERMATCH-26OCT12RODGUL-GUL | Svyatoslav Gulin wins | end 2026-10-26T08:00:00Z | prices 0.60/0.39 | asks 0.61/0.40 | volume 2050.96 | liquidity 2050.96 | event KXATPCHALLENGERMATCH-26OCT12RODGUL | combo false
Rule: If Svyatoslav Gulin wins the Rodenas vs Gulin professional tennis match in the 2026 ATP Challenger Catania Qualification Final after a ball has been played, then the market resolves to Yes.

kalshi | KXNFLTOTAL-26OCT18HOUJAC-44 | Full Game: over 43.5 points scored? | end 2026-10-20T13:30:00Z | prices 0.50/0.49 | asks 0.51/0.50 | volume 2199.08 | liquidity 2199.08 | event KXNFLTOTAL-26OCT18HOUJAC | combo false
Rule: If Houston and Jacksonville collectively score more than 43.5 points in the Houston vs Jacksonville Pro Football game originally scheduled for Oct 18, 2026, then the market resolves to Yes.
```
