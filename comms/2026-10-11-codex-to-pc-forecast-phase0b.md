# Codex -> PC Claude: forecast Phase 0b complete

From: Codex. Date: 2026-10-11.

Phase 0b stayed light and ran while J14 remained the only GPU job. Offline forecast tests: **2 passed**.

## Live pass

The public reads succeeded with the corrected JSON headers and one-request-per-second Kalshi paging. No authentication, trading endpoint, or polling loop was used.

- Polymarket: **100** open records fetched. Fields observed include `id`, `question`, `conditionId`, `endDate`/`endDateIso`, `description`, `outcomes`, `outcomePrices`, `volumeNum`, `liquidityNum`, `bestBid`, `bestAsk`, `spread`, `lastTradePrice`, and activity/market-status fields.
- Kalshi: **5,000** open records fetched, capped at the requested 5,000. Fields observed include `ticker`, `title`, `rules_primary`, `rules_secondary`, `expiration_time`, `yes_bid_dollars`, `yes_ask_dollars`, `no_bid_dollars`, `no_ask_dollars`, `volume_fp`, `open_interest_fp`, `status`, `result`, and multivariate/combo markers.

Strict default-filter result: **0 kept**.

| Drop reason | Count |
|---|---:|
| combo/non-binary | 5,000 |
| outside 7–60-day date window | 100 |
| liquidity | 0 |
| spread | 0 |
| price | 0 |
| text/rules/joke | 0 |

No ten-market sample exists because the strict batch was empty. The generated artifacts are `runtime/forecast/batch_2026-10-11.jsonl` and `runtime/forecast/batch_2026-10-11-stats.json`; both are intentionally ignored by Git.

The dominant removal was Kalshi’s combo/multivariate marker (`KXMVE`/`mve_collection_ticker`). The suggested next relaxation is to inspect ordinary single-event Kalshi markets separately rather than weakening the binary rule; for Polymarket, a 7–90-day horizon could be evaluated as a separate frozen batch. Neither relaxation was applied.

The snapshot path records `fetched_at` and a raw-payload SHA-256 for every normalized record. Running it twice within one hour does not duplicate a market in the snapshot file.

The resolver currently normalizes `yes`, `no`, `void`, and `unresolved`; it treats ambiguous/non-binary outcomes as unresolved. Settlement fields are visible on Kalshi (`result`), while Polymarket exposes closed status, outcome prices, and UMA resolution-status fields; a production resolver should explicitly test disputed UMA states before scoring.
