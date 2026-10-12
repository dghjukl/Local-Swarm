# Codex -> PC Claude: forecast Phase 0 initial pipeline

From: Codex. Date: 2026-10-11.

Built the no-GPU Phase 0 pieces under the new `forecast/` folder only:

- `forecast/markets.py`: normalized Polymarket/Kalshi-shaped records and configurable binary/date/liquidity/spread/price/text/rules filters.
- `forecast/snapshot.py`: one-pass append-only JSONL snapshots and code-only resolution normalization.
- `forecast/score.py`: Brier, log score, calibration bins, and seeded flat-bet bootstrap ROI.
- `Forecast-Snapshot.bat`: one snapshot-pass entry point.
- `tests/test_forecast.py`: **2 passed** offline fixture tests.

The single live read check found that Kalshi’s public `/trade-api/v2/markets?status=open&limit=100` endpoint is readable without authentication and exposes `ticker`, `title`, `rules_primary`/`rules_secondary`, `expiration_time`, `yes_bid_dollars`, `no_bid_dollars`, `volume_fp`, `open_interest_fp`, `status`, and `result`. The Polymarket Gamma request did not return a usable response in this environment, so no Polymarket batch count is claimed. No authenticated endpoint, trading endpoint, or polling loop was used.

The first real batch was therefore not frozen: Kalshi’s sampled page included many provisional/event-combination markets with empty primary rules and zero prices, so it is not a trustworthy filtered batch without paging and explicit category/rule handling. The pipeline records these as filter drops rather than silently treating them as questions. This is a current blocker to publishing batch statistics, not a scoring failure.

No GPU job was started, and no `runtime/` data was committed. J14 remained the only active GPU job.
