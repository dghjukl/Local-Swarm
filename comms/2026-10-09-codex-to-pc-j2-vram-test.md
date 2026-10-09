# Codex → PC: J2 VRAM-ceiling test result

## Asks

None. J2 is complete; all test servers were stopped and the GPU returned to about 1.1 GiB used.

## Info

The three servers were started exactly as specified on ports 8201–8203. The nodecheck command was:

```text
.venv\\Scripts\\python.exe -m swarm.nodecheck http://127.0.0.1:<port> --sizes 500,2000,4000
```

The retained second MiMo run and the Qwen run are below. `nodecheck` reports the actual prompt sizes after request formatting (586/1843/3610 for MiMo and 590/1847/3614 for Qwen).

| Phase | Servers | GPU used / SM / power | MiMo read tok/s | MiMo write tok/s | Qwen read tok/s | Qwen write tok/s |
|---|---|---:|---:|---:|---:|---:|
| A: MiMo alone | MiMo 8201 | 7,859 MiB / 450 MHz / 8.82 W | 2,174 / 2,674 / 2,804 | 60.6 / 60.2 / 59.7 | — | — |
| B: full card | MiMo 8201 + Qwen 8202 + Gemma 8203 | 15,820 MiB / 247 MHz / 8.14 W | 2,181 / 2,669 / 2,758 | 60.6 / 60.2 / 59.5 | 1,334 / 3,208 / 3,671 | 91.2 / 94.2 / 92.4 |
| C: Gemma stopped | MiMo 8201 + Qwen 8202 | 11,889 MiB / 232 MHz / 8.30 W | 2,188 / 2,680 / 2,771 | 60.5 / 60.3 / 59.6 | 2,628 / 3,971 / 4,205 | 98.3 / 97.4 / 96.0 |

Phase C Qwen was approximately 19% faster at the middle prompt and 13% faster at the longest prompt than phase B. MiMo was effectively unchanged across phases (within normal run-to-run variation). The test therefore shows a measurable but not catastrophic effect on Qwen when the card is nearly full; it does not show the 30%+ slowdown threshold for MiMo.

No crashes or out-of-memory errors occurred. The server logs contained no `fit`, `offload`, `failed to allocate`, or error lines beyond normal model-loading messages. Final cleanup verified no `llama-server` processes remained and GPU memory was 1,061 MiB.
