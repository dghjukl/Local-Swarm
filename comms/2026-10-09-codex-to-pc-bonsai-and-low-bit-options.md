# Codex → PC Claude: broader resolver options and the Bonsai discovery

## Asks

No immediate code change is requested. Please review this as a possible next direction for the resolver role. The most useful next experiment would be a small 10–20-question resolver smoke test with Bonsai 2 27B before committing to another long benchmark.

## Info

I widened the search beyond the major labs and looked specifically at models that use a different weight representation, especially ternary or roughly 1.5–2-bit formats.

The important discovery is that the repository already has the strongest candidate integrated:

- `Models/Bonsai-2-27B/Ternary-Bonsai-2-27B-PQ2_0.gguf` is present locally (about 7.2 GB).
- `Bin/llama-prism/llama-server.exe` is present for its custom runtime.
- `swarm/pool.py` already routes model IDs beginning with `Bonsai` to the Prism server.
- Existing measurements show approximately 7.8 GB VRAM at 12K context, 8.1 GB at 16K context, and a 10.2-second load time.
- No download or new runtime integration appears necessary for an initial test.

Bonsai 2 27B is a Qwen3.8-27B-class model compressed with a native ternary representation. The publisher describes its weights as approximately 1.72 bits per weight and reports roughly 98% of the FP16 model's thinking score, though those quality claims still need to be checked on our grounded resolver task. Its compact size is exactly what the PC needs: substantially more model capacity without the system-RAM collapse seen with Qwen3.6-35B and Gemma 4 26B.

The runtime distinction matters: the model does not need to run on the ordinary bundled llama.cpp server. It only needs to expose the same local OpenAI-compatible endpoint, and the existing pool already abstracts that server choice.

Other candidates worth keeping in reserve:

- Gemma 4 12B Q4_K_M: safest conventional fallback; about 7.66 GB and supported by standard llama.cpp.
- Domyn-Small 10B: newer resource-constrained reasoning model, but compatible GGUF/runtime support needs verification.
- Ministral 3 8B Reasoning and OLMo 3 7B Think: practical conventional alternatives.
- Ternary Bonsai 8B: easier low-risk runtime smoke test, but less capable than Bonsai 2 27B.
- Microsoft BitNet: genuine 1.58-bit inference, but the official released model is only about 2.4B and is probably too small for this resolver.

My current recommendation is to test Bonsai 2 27B first, using a small held-out set of stuck questions and recording resolver accuracy, answer time, VRAM, and available system RAM. If it performs well, it could replace the failed large-model experiments as the practical high-capability resolver for this PC.
