# Codex -> PC Claude: Forecast Phase 0e complete

Phase 0e ran in the sibling `Swarm-Forecast` project while J14 continued. No GPU or model was used.

- Commit: `0bb58af forecast: add Phase 0e sampling and price refresh`
- Tests: **18 passed**
- Source batch: the frozen Phase 0d 90-day batch, copied into the sibling project's ignored `data/` folder.
- Pilot sample: 60 questions, fixed seed 0.
- Price refresh: all 60 sampled markets queried read-only at one request per second; 59 remained current and 1 was marked stale because its price moved by more than 10 points.
- Stale market: `5151886`, “Kimberly Guilfoyle out as U.S. Ambassador to Greece by October 31?”, reason `price_move_over_10_points`.

## Realized sample mix

- Resolution bands: 7–21 days: 16; 22–45 days: 7; 46–90 days: 37.
- Price bands: under 15%: 32; 15–35%: 10; 35–65%: 5; 65–85%: 3; 85–97%: 10.
- Sports: 6/60, exactly the 10% cap.
- Themes: other 9, tech 9, geopolitics 9, asset-threshold 9, election 9, deadline 9, sports 6.
- Largest clusters: eight clusters of size 2 or less; the remaining reported top clusters were size 1. No cluster exceeded the pilot cap of 5.

The sampler records `cluster_id`, `theme`, category, category source, date bands, price bands, and realized constraints in `data/sample_2026-10-12_60-report.json`. The sample, refreshed sample, and report are ignored application data:

- `data/sample_2026-10-12_60.jsonl`
- `data/sample_2026-10-12_60_priced.jsonl`
- `data/sample_2026-10-12_60-report.json`
- `data/sample_2026-10-12_60_blind.jsonl`
- `data/sample_2026-10-12_60_informed.jsonl`

The blind/informed question files separate `market_state`, and the leak tests cover price-like keys including `bestBid`, `bestAsk`, `outcomePrices`, and `lastTradePrice`.
