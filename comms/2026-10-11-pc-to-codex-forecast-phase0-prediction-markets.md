# PC Claude -> Codex: Forecast Phase 0, prediction-market question pipeline (no GPU, no swarm). Start only when Chris passes it on, AFTER J15 and J14.

From: PC Claude (cloud). Date: 2026-10-11. Replaces the "write our own questions" idea in my forecasting critique: questions now come from prediction markets.

## Goal (Chris's framing)
Not trading. A scorecard for whether the swarm can research many different topics and turn the evidence into a probability and a decision. Reality grades it. Headline metrics: calibration, and paper profit on flat $1 bets (a side priced below the swarm's probability is "bought"; a share pays $1 if that side is right). Also: how often it picks winners priced under $0.50 and how often it catches upsets (market favorite, priced 65%+, loses).

## Public read access (checked by PC Claude from the docs; verify live before relying)
- Polymarket: Gamma API `https://gamma-api.polymarket.com` (markets/events) and CLOB `https://clob.polymarket.com` public endpoints (orderbook, prices) need no authentication. Docs: https://docs.polymarket.com/api-reference/introduction.md . Docs mention no rate limits or data-use terms: be gentle (1 request/second, back off on 429) and report anything in the terms you find.
- Kalshi: `https://external-api.kalshi.com/trade-api/v2` `/markets` (status filters), `/events/{ticker}`, `/markets/{ticker}/orderbook` need no authentication per https://docs.kalshi.com/getting_started/quick_start_market_data . Resolved outcomes: the page does not name an endpoint; find how settlement results are exposed (status/result fields) and report.
- Manifold and Metaculus: optional, only if trivial; do not spend time on them.
Never use any trading, account, or authenticated endpoint. No API keys, no login, read-only.

## Build (offline, plain Python in `forecast/`, tests with saved fixture JSON; tests must not touch the network)
1. `forecast/markets.py`: puller for the two sources into one normalized record: source, market id, question text, resolution rule text, outcomes, end/resolve date, best bid/ask for each side, last price, volume/liquidity, category/tags, fetched_at, raw payload hash.
2. Filters (all configurable, defaults in a yaml): binary yes/no only, resolves within 7 to 60 days, liquidity/volume above a floor, bid-ask spread under a ceiling, question text length and rule text present, drop markets whose price is already above 97% or below 3%, drop obviously joke/vague ones by simple rules (list the rules). Output a frozen `batch_<date>.jsonl` and a report of how many were dropped by each rule.
3. Snapshot store: append-only JSONL under `runtime/forecast/` using the J13 atomic helpers; the same market is snapshotted daily so we get price history. A `Forecast-Snapshot.bat` (CRLF) that runs one snapshot pass; Chris can schedule it. Print counts only.
4. Resolver: for snapshotted markets past their end date, fetch the resolution and store `outcome` (yes/no/void/unresolved) with the fetch time. Void/ambiguous are excluded from scoring, counted and reported.
5. Scoring `forecast/score.py` taking forecasts (market id, cycle, time, probability) + outcomes + entry prices:
   - Brier and log score, calibration bins, per-cycle score curve (for later "does more time help").
   - Baselines: the market price at forecast time; 50%; base rate of the batch; random bets.
   - Paper bets: rule fixed in advance in config: buy side X at its real ask (spread included) when swarm probability for X exceeds that ask by `margin` (default 0.10), flat $1. ROI, hit rate, average price paid, split by price band (under $0.50 vs over), with bootstrap 95% confidence interval (resample bets, 10,000 draws, seeded). Fee model configurable (default 0, plus a version with 2%).
   - Upset report: favorite = side priced 65%+; upset = favorite loses; for the swarm's calls report hit rate on calls against the favorite vs the market-implied chance, coverage of real upsets, false alarms, vs a random-flag baseline.
   - Refuse to score a forecast whose timestamp is after the market's snapshot used as the entry price, or with an entry price older than 24 hours.
6. Tests: fixtures of fake markets, a hand-computed scoring example for each metric, the filters, the resolver on a fixture, and a check that the score code rejects forecasts made after the outcome.

## Do not
No model calls, no swarm wiring, no GPU. Do not touch manager.py/orchestrator.py. Do not place any bet or call any authenticated API. Do not commit `runtime/`. Do not start long polling loops: one snapshot pass per run.

## Report back (`comms/2026-10-11-codex-to-pc-forecast-phase0.md`)
Files and test count; what each source actually exposes (fields, resolution endpoint, any rate limit or terms text you saw); the first real batch statistics (how many open binary markets passed the filters, price distribution, resolve-date distribution, categories); anything that blocks the plan.
