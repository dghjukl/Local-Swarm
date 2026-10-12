# Forecast cycle 1 blind diagnostics

Diagnostics completed against `apps/forecast/data/cycles/cycle1-run2/blind.jsonl` and `picks.json`. No code was changed.

## 1. Six disagreement traces

The stored probability is the model/extractor result; the excerpts below are shortened from the research summary/final answer in the raw records.

| Market | Stored p(YES) | Diagnostic |
|---|---:|---|
| 3554313 | 0.35 | Reasons say Claude Opus leads the index, but the final answer says evidence does not support YES. This is a model conclusion versus rationale mismatch; the extractor appears to have captured the low final probability rather than a numeric formatting error. |
| 1283345 | 0.35 | The final answer explicitly says NO / the Democratic Party is not expected to win IL-04. This looks like a low model estimate, not an extractor inversion; the reason text itself contains Democratic-leaning base-rate language. |
| 631018 | 0.35 | The final answer says evidence does not support YES and is thin. The rationale mixes a Democratic-favorable national environment with a low final probability. This is uncertainty/reason mismatch, not a clear parser inversion. |
| 1283544 | 0.22 | The rationale cites a Republican incumbent and stronghold; the final answer says NO. The low probability is directionally consistent with the final answer. |
| 1090005 | 0.05 | The final says NO because the market appears to resolve YES only if Gaethje remains champion, while the rationale says he is current champion. This is primarily a semantic market-resolution problem, not an extraction problem. |
| 1719961 | 0.35 | The rationale cites a strong rookie candidate, while the final answer says the market is unresolved and the probability cannot be estimated reliably. This is uncertainty expressed as a low stored probability. |

Raw traces are in `blind.jsonl`; the six records can be located by their market IDs.

## 2. Opposite-side heuristic across usable rows

There are 228 rows with a probability. A deliberately rough phrase-based scan found:

- 33 rows where an explicit directional phrase appeared to favor the side opposite the stored probability.
- 12 rows where the phrase agreed with the stored probability.
- 183 rows unclear or lacking a sufficiently explicit directional phrase.

This is a triage statistic, not a correctness score. The large unclear bucket means it should not be used to claim that 33 forecasts are wrong.

## 3. Rows without a probability

The file contains 299 records: 228 usable and 71 without a probability. The 71 break down as:

- 50 refusal/insufficient-evidence responses: the model returned language such as “cannot determine,” “no evidence,” “not sufficient,” or “does not support.”
- 21 wrong-format/non-conforming responses: non-empty output without an extractable probability and without the refusal markers above.
- 0 timeouts.
- 0 empty responses under this classification.

The source pool was reported as 278 markets by the cycle handoff, while the output file contains 299 records. That discrepancy should be checked before treating the percentages as a market-level rate; the usable/no-probability counts above are file-row counts.

## 4. Entity overlap in the 30 picks

The picks are not entity-independent. Repeated entities/themes include:

- James Gallagher: 1283321, 1280988, 1281180.
- Flávio Bolsonaro: 3358720, 5329587.
- Israel–Iran ceasefire: 3399459, 5339986.
- Anthropic/model-capability or valuation questions: 2109881, 3554313.
- District-election questions: 942878, 944314, 1283345.

This supports treating the 30 picks as a small clustered portfolio rather than 30 independent bets.

## 5. Recommendation for amendment 4

1. **Minimal change:** retain the current extractor, add a refusal/uncertainty status, and exclude refusal rows from scoring. Lowest cost, but it does not address semantic market-resolution errors.
2. **Recommended:** require a structured final field containing `probability_yes`, `direction`, and `confidence`, then compare it with the extracted probability and flag disagreement. Moderate prompt/parser/test work; directly exposes the six-trace class of issue.
3. **Broader change:** add a market-resolution paraphrase check and cluster/entity deduplication before picks. Highest cost, but it addresses 1090005-type semantic errors and correlated picks.

The next useful experiment is option 2 first, followed by a small resolution/cluster audit. Scoring-v1 and memory-store-phase-b remain pending as instructed.

The pre-existing uncommitted `swarm/tools.py` diff was not modified or committed.

## Corrections

- `blind.jsonl` contains 299 file rows for 278 markets because 21 markets were retried with `attempt = 2`. At market level there are 228 usable markets and 50 without a probability, or 18.0% of 278. Of the 21 retried markets, 10 recovered and 11 still failed.
- The earlier stale-suspect count of 7 cannot be reproduced from the final deep records. The reproducible count is 5: 1090005, 629397, KXKAMALARUN-28-27JAN01, 716941, and 942878.
- The `reason` text stored in `bets.json` is the blind pick reason, not the deep reasoning.
- `entry_fetched_at` is around 15:3xZ, approximately 3.5 hours before the deep `forecast_time` around 19:05Z. No fix was made in this pass.
