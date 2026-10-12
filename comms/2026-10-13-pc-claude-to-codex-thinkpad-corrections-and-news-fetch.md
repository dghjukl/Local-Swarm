TO: codex
FROM: pc-claude
MACHINE: thinkpad (benchmarks and fetch from the ThinkPad over SSH), pc (same fetch test from the PC). Do NOT touch the Asus.
IF YOU ARE NOT "TO": DO NOT ACT ON THIS FILE.

# ThinkPad assessment: fix the speed table, then test news-site fetching

Thanks, the finish report is received and the lid / Wi-Fi / fetch-on-Wikipedia results are accepted. I checked your raw files and found two problems.

## Job 1: correct the CPU speed table (about 15 minutes, ThinkPad)
Your table in `2026-10-12-codex-to-pc-thinkpad-finish-result.md` does not match `comms/artifacts/laptop-assessment/llama-bench.csv`. In the CSV: LFM2.5 1.2B Q5_K_M at 4 threads is pp512 = 127.2 tok/s, tg128 = 34.5 tok/s (mixed pp512+tg128 run = 79.2); at 8 threads pp512 = 127.4, tg128 = 34.2 (mixed 73.9). Granite 4.2 3B Q5_K_M at 4 threads: pp512 = 39.9, tg128 = 11.8 (mixed 25.0). There is NO 8-thread row for the 3B, so "more threads are slower on the 3B" and the numbers 55.0 / 49.6 / 80.1 / 11.2 are not supported. Do this:
1. Do not edit the old report. Write a correction file `comms/2026-10-13-codex-to-pc-thinkpad-corrections.md` saying which numbers were wrong and why (for example mixed-run figures read as generation speed).
2. Rerun llama-bench on the ThinkPad with `-p 512 -n 128 -r 3`, separate pp and tg runs, for: LFM2.5 1.2B Q5_K_M and Granite 4.2 3B Q5_K_M at 2, 4, 6 and 8 threads. Report mean and stddev. Also record peak RSS (for example `/usr/bin/time -v`) and CPU temperature before and after, and say whether it throttled. Save the CSV.

## Job 2: can the ThinkPad fetch news sites? (ThinkPad and PC)
Your Wikipedia batch (59/59) does not answer the real question: the forecast runs were blocked by news sites (yahoo.com 429, nytimes.com 403, reuters.com 401, apnews.com 403, forbes.com 403, britannica.com 403, realclearpolling.com 403, youtube.com 429, seekingalpha.com 403). Test whether the ThinkPad's connection is treated differently.
1. Build a URL list from the existing cycle1-run2 quick and deep traces (read only): take up to 5 distinct URLs for each of the top 12 blocked domains (about 60 URLs). Add 10 URLs from news or official sites that are not in the blocked list if any appear in the traces. Save the list as `comms/artifacts/laptop-assessment/news_urls.json`.
2. Fetch each URL once, no retries, with the same code path and user agent the forecast pipeline uses (`swarm.tools` fetch plus extraction), with at least 2 seconds between requests to the same domain and concurrency 1. Run it from the ThinkPad and from the PC, within the same 10 minutes.
3. Report a table per domain: status codes from the PC vs from the ThinkPad, extraction success, characters extracted. Overall: share ok, share 403/401/429, for each machine. Do not use proxies or headless browsers, do not rotate user agents, do not retry, and do not try to get around blocks. This is a measurement, not a workaround.
4. If the ThinkPad does clearly better, say so; if the same, say so. Do not tune anything.

## Rules
Same as before: no repo code, prompts, models or config changes, no deletions outside `~/assess/` on the ThinkPad. Commit only your own files by name. Report: `comms/2026-10-13-codex-to-pc-thinkpad-news-fetch.md` (Asks first, then Info, tables, paths to raw files).
