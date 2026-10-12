# Cycle1-run2 retrieval audit

Read-only audit of 278 distinct blind markets and 299 blind file rows. No code, trace, or pinned blind record was modified. Raw/near-raw outputs are in `comms/artifacts/retrieval-audit/`.

## 1. Source mix

The scan counted URLs in `search.results` and `fetch` events. It found 11,481 URL observations across 1,856 distinct domains. The full top-40 list and compact category/theme tables are in [source-mix.txt](artifacts/retrieval-audit/source-mix.txt).

| Class | URL observations |
|---|---:|
| other | 5,423 |
| aggregator | 1,546 |
| wikipedia | 1,402 |
| mainstream news | 972 |
| scholarly | 919 |
| social/video | 345 |
| polls/election data | 260 |
| prediction-market/forecast | 221 |
| crypto/finance data | 156 |
| government/official | 120 |
| sports data | 117 |

The largest domains were en.wikipedia.org (1,308), doi.org (754), msn.com (585), yahoo.com (416), finance.yahoo.com (347), youtube.com (199), polymarket.com (190), arxiv.org (150), nytimes.com (137), and 270towin.com (129).

## 2. Market-site contact

[blind_audit.json](artifacts/retrieval-audit/blind_audit.json) contains one entry per distinct market, with trace file, market-site domains, blind probability, market last price, and absolute gap where both values exist.

| Blind group | Markets | Usable | Mean absolute gap | Median absolute gap |
|---|---:|---:|---:|---:|
| Market-site contact | 88 | 56 | 0.2399 | 0.15 |
| No market-site contact | 190 | 162 | 0.2520 | 0.16 |

Contact was defined as any URL host matching Polymarket, Kalshi, Manifold, Metaculus, PredictIt, or a forecast site. This is URL contact only, not proof that prices entered the model context. A rough search of the research text for the same market ID or formatted last-price literal found 0/88 flagged rows with a direct match; this does not rule out indirect leakage. The deep arm contacted such sites in 11/30 traces, as expected for informed mode.

## 3. Scholarly use

There were 854 scholarly evidence passages across 278 traces. The trace schema has no separate `final.sources` field; therefore explicit citation count is not recoverable as a field-level measure. Searching the research summaries for evidence IDs associated with scholarly passages found 0 unambiguous citations under that conservative test. Scholarly passages by category were: AI 3, politics 161, other 115, sports 42, geopolitics/war 58, crypto 233, elections 85, tech/AI 151, entertainment 6.

## 4. Recency and query formulation

The evidence snippets contained 2,613 date-bearing items under a simple year/month regex; 851 were marked recent by a 2025-12/2026 date heuristic. Date-less evidence items: 0 under this snippet-only scan, which should be treated cautiously because many snippets are generated metadata. 20/278 traces had zero fetched mainstream-news domains. 2,573/3,355 search events contained a year or month name.

## 5. Resolution-source contact

The pool includes many empty `raw.resolutionSource` fields. The audit therefore did not invent a source-domain mapping when no source was named. For non-empty source fields, the matching-domain check should be read from the raw pool and trace URL tables; no reliable aggregate was produced from the inconsistent source strings. This is a data-quality limitation, not a claim of zero contact.

## 6. Failure sample

[failure-sample.tsv](artifacts/retrieval-audit/failure-sample.tsv) contains 30 stratified examples: 15 no-probability rows and 15 usable rows whose uncertainty text suggests missing/uncertain evidence. It includes question, queries, top fetched domains, and a rough labelled diagnosis.

## 7. Config and tools

The exact research config is in [config-research.json](artifacts/retrieval-audit/config-research.json): builtin backend, four search queries, five results per query, two Wikipedia results, ten pages, three fetch workers, scholarly enabled with OpenAlex/arXiv/PubMed/Crossref/ADS, and six maximum papers.

The configured trace shows `news`, `web`, `wikipedia`, `openalex`, `arxiv`, `pubmed`, `crossref`, and `ads` search events. The repo also contains additional tool/backend code in `swarm/tools.py`; this audit did not change it. The important observation is that the forecasting config uses the builtin research path and does not enable a separate dedicated official-source, market-site-blocklist, or entity-resolution pass.

## Three most concerning findings

1. Prediction/forecast domains appeared in 88/278 blind markets, including 190 Polymarket URL observations. That is a concrete blind-boundary risk even though this audit did not prove price text entered the prompt.
2. Wikipedia, scholarly and aggregators dominate the URL mix: 1,402 + 919 + 1,546 = 3,867 observations, while only 120 were classified government/official. This is a source-quality imbalance.
3. 20/278 traces had no fetched mainstream-news domain, and 2,573/3,355 search events contained a date/year term; the pipeline is broad but not consistently anchored to current primary reporting.

## Fix options

- Add a URL/domain denylist and strip market-site results from blind research: low-to-moderate cost; rerun the blind arm to verify.
- Add an official-source preference and category-specific source policy: moderate cost; requires config and tests.
- Add explicit source provenance, citation accounting, and date extraction fields: moderate-to-high cost; improves auditability.
- Add entity/resolution-source matching before final forecasting: high cost; targets the wrong-entity and semantic-resolution failures.

No fix was implemented. Any change should use a new tagged cycle version or a separately approved amendment.
