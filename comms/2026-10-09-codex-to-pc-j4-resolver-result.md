# Codex → PC: J4 resolver benchmark complete

## Asks

None. J4 completed successfully; no runtime files were committed.

## Info

### Tests

Command: `./Run-Tests.bat`

```text
86 passed, 1 skipped, 1 warning in 323.05s (0:05:23)
```

The warning was the existing Starlette/httpx deprecation warning from `fastapi.testclient`.

### Resolver report

The benchmark processed the 86 stuck questions from the 8-attempt study. Results from `runtime/evals/resolver-20261009/resolver_report.md`:

| Resolver | Questions | Vote right | Resolver right | Rescued | Broken | Net | Avg seconds |
|---|---:|---:|---:|---:|---:|---:|---:|
| MiMo-V2.6-Distill-Qwen-9B-think | 86 | 42 | 46 | 6 | 2 | +4 | 9 |
| gpt-oss-20b | 83 | 39 | 36 | 6 | 9 | -3 | 4 |
| Gemma-4-26B-A4B-it | 86 | 42 | 51 | 11 | 2 | +9 | 23 |
| Qwen3.6-35B-A3B | 86 | 42 | 53 | 12 | 1 | +11 | 35 |

By why stuck (questions / vote right / resolver right):

```text
MiMo:  not_ready 1/0/0; split 68/36/40; split+not_ready 17/6/6
gpt:   not_ready 1/0/0; split 66/34/33; split+not_ready 16/5/3
Gemma: not_ready 1/0/0; split 68/36/43; split+not_ready 17/6/8
Qwen:  not_ready 1/0/0; split 68/36/45; split+not_ready 17/6/8
```

### Qwen3.6-35B observations

- It loaded and completed all 86 questions.
- Average time was 35 seconds per question.
- The model log was `runtime/logs/models/Qwen3.6-35B-A3B.log`.
- No `fit`, `offload`, `failed to allocate`, out-of-memory, or error lines were found. The only matching warning was `--cache-idle-slots requires --cache-ram, disabling`.
- The lowest free-RAM value directly captured during the run was 8.36 GB of 15.84 GB, during the MiMo phase. RAM was not sampled while Qwen was actively running, so I cannot claim a precise Qwen minimum; the PC remained responsive and finished without a restart. After cleanup, free RAM was 11.09 GB and GPU memory was 958 MiB.

### Error counts

Parsed `runtime/evals/resolver-20261009/results.jsonl`; rows with a non-null `error` field:

```text
resolver-MiMo-V2.6-Distill-Qwen-9B-think: 0
resolver-gpt-oss-20b: 0
resolver-Gemma-4-26B-A4B-it: 0
resolver-Qwen3.6-35B-A3B: 0
```
