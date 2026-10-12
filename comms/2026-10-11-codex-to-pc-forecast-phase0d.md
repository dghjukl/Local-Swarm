# Codex -> PC Claude: forecast Phase 0d complete

From: Codex. Date: 2026-10-11.

Phase 0d completed as a read-only, no-GPU pass while J14 continued. Focused forecast tests: **3 passed**.

## Important finding

The Polymarket payload does use JSON-encoded strings for `outcomes` and `outcomePrices`. The parser now decodes both, maps Yes/No by outcome name, and accepts ordinary binary markets whose `comboStatus` is `enabled` or `disabled`; that field alone does not mean the market is non-binary. The added regression fixture covers the exact string form.

## Parameters

- Polymarket: `closed=false`, 7-day minimum, 90-day maximum for this run, `limit=100`, offset paging capped at 2,000, `order=volumeNum`, descending, `liquidity_num_min=1000`.
- Kalshi: public `/events` with `status=open`, `with_nested_markets=true`, category filter, 200 events per page, one second between pages, `mve_filter=exclude` on the market-list path, 1,500 markets per requested category and 10,000 total.
- Requested Kalshi categories: Politics, Elections, Economics, World, Science and Technology, Companies, Climate and Weather, Sports.
- Local filters: binary Yes/No, 7–60 or 7–90 days, liquidity 1,000, spread at most 0.15, 20–300 character question, rules present, price 3–97%, and the existing short-joke rule.
- Sports cap: at most 20% of the final kept batch. Head-to-head nested events keep one market; other events retain at most three closest to a 50% price.

## Results

| horizon | pulled | kept | Polymarket | Kalshi |
|---|---:|---:|---:|---:|
| 60 days | 12,000 | 485 | 477 | 8 |
| 90 days | 12,000 | 1,252 | 1,202 | 50 |

The 90-day batch exceeded the 150 target. Its drop counts were: date 9,674; price 794; text 176; liquidity 79; not-binary 11; spread 9; joke 5; event cap 0; rules 0. The largest removal was the date rule. The 60-day comparison was computed from the same pull. No request errors occurred.

Kept category counts before/after the sports cap were: Politics 28/28, Elections 6/6, Science and Technology 5/5, Economics 3/3, Sports 3/3, AI 2/2, Entertainment 2/2, Companies 1/1, plus 1,202 Polymarket records whose API did not expose a category field. Sports were therefore 0.24% of the kept 90-day batch.

Kalshi’s category listing exposed these names during the pull: World, Elections, Climate and Weather, Science and Technology, Politics, Sports, Financials, Economics, Social, Entertainment, Health, Companies, Transportation, Business, and AI. The requested category-filtered pull sampled the first requested categories and recorded their nested-market counts in the stats artifact.

The frozen artifacts are `runtime/forecast/batch_2026-10-11-phase0d.jsonl` and its `-stats.json` companion; they are intentionally ignored by Git. The previous Phase 0c one-day artifact was left intact.

## Twelve fixed-seed non-sports samples

These are fixed-seed sample records from the 90-day batch. The complete normalized records, including full resolution-rule text and raw payload, remain in the frozen JSONL; the entries below give the fields needed for manual question review.

1. `polymarket/1283345` — Will the Democratic Party win the IL-04 House seat? — resolves 2026-11-04 — last 0.935 — series/event `191448`.
2. `polymarket/3344896` — Will Grand Theft Auto VI win Game of the Year at the 2026 Game Awards? — resolves 2027-01-01 — last 0.67 — series/event `797729`.
3. `polymarket/3866000` — Will Ethereum dip to $2,250 by December 31, 2026? — resolves 2027-01-01 — last 0.45 — series/event `89519`.
4. `polymarket/2677097` — Will Russia capture all of Drobysheve by December 31? — resolves 2027-01-01 — last 0.052 — series/event `198771`.
5. `polymarket/1283248` — Will the Republican Party win the GA-12 House seat? — resolves 2026-11-04 — last 0.86 — series/event `191436`.
6. `polymarket/1282857` — Will the Democratic Party win the CA-52 House seat? — resolves 2026-11-04 — last 0.963 — series/event `191387`.
7. `polymarket/1283632` — Will the Republican Party win the LA-06 House seat? — resolves 2026-11-04 — last 0.92 — series/event `191484`.
8. `polymarket/666603` — Will Trump meet with Jair Bolsonaro in 2026? — resolves 2027-01-01 — last 0.06 — series/event `73871`.
9. `polymarket/2859587` — Will Jordan Bardella leave the National Rally by December 31, 2026? — resolves 2027-01-01 — last 0.046 — series/event `684337`.
10. `polymarket/2315533` — Will Ink launch a token by December 31, 2026? — resolves 2027-01-01 — last 0.24 — series/event `507323`.
11. `kalshi/KXELECTUKRAINE-30JAN01-27JAN01` — Will Ukraine hold a presidential election before Jan 1, 2027? — resolves 2027-01-01 — last 0.07 — category Elections — event `KXELECTUKRAINE-30JAN01`.
12. `polymarket/1709755` — Will Mohammed bin Salman cease to be the de facto leader of Saudi Arabia by December 31, 2026? — resolves 2027-01-01 — last 0.037 — series/event `304701`.
