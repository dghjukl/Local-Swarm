# Codex → PC: J5 aborted on RAM safety limit

## Asks

Please treat J5 as incomplete. The Qwen3.6-35B phase must be redesigned or given a stricter RAM guard before retrying; I stopped it at the ticket's safety threshold.

## Info

The fixed prerequisite suite passed:

```text
86 passed, 1 skipped, 1 warning in 322.41s (0:05:22)
```

`Resolver-Test-2.bat` began phase A (the 73-question 3-attempt vote study). While Qwen3.6-35B was loading/running:

- GPU memory reached 15,006 MiB.
- Available system RAM fell to 0.17 GB of 15.84 GB.
- This was below the ticket's 1 GB stop threshold, so I immediately stopped the llama-server process.
- After cleanup, available RAM recovered to 10.19 GB and GPU memory to 845 MiB.

The wrapper then continued emitting connection failures, so I interrupted and terminated it. Partial artifacts:

- `runtime/evals/resolver-vote3-20261009/results.jsonl` contains 92 rows: 73 vote-baseline rows and 19 resolver rows.
- All 19 resolver rows have `LLMError: request to http://127.0.0.1:8200 failed: All connection attempts failed`.
- No `resolver_report.md` or `overall.md` was produced.
- Phases B and C did not start.
- `crash.log` is empty; the wrapper's `events.log` only records the interrupted grading attempt.

No GPU or llama-server processes remain. I did not commit `runtime/`.
