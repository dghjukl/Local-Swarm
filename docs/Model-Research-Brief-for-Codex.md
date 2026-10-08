# Task for Codex: find the best current models for each Local Swarm role (research only)

**Do not download, install or change anything.** Produce one report: `docs/Model-Research-2026-10.md`.

## The PC (hard limits)
- GPU: RTX 5060 Ti, **16 GB VRAM**. The swarm budgets about 14.5 GB for models.
- RAM: **16 GB, single stick (single-channel DDR5)**. Only about 8–10 GB is usable for a model split between GPU and RAM, and split models run slowly.
- CPU: i5-14400F. Windows 11.
- Runtime: **llama.cpp `llama-server`** (CUDA build b10152; we can update the build if a model needs it). Models must exist as **GGUF** and run in llama.cpp. Say if a model needs a newer llama.cpp build or a fork.
- **Quantization floor: Q5** (Q5_K_M or better). Google's official QAT 4-bit releases are acceptable as an exception because they are trained for 4-bit. Do not recommend Q4 or lower otherwise.

## What the models are for
A local research swarm. A coordinator (currently **MiMo-V2.6-Distill-Qwen-9B**, a Qwen3.5-9B fine-tune) runs a research loop: it hands one task at a time to worker models ("search for X, read these passages, report the fact, its source, what's missing"). Workers report back, a fact-checker verifies claims against source passages, and the coordinator writes the final answer. We test on **FRAMES** (multi-hop questions over Wikipedia) and a set of 2026 news questions.

Find candidates for these roles:

| Role | Size / fit | What matters most |
|---|---|---|
| **A. Expert worker** (called when the small workers are stuck) | 9–15B dense at Q5, must fit **next to MiMo** (≈7 GB) → ≤ about 8.5 GB file | Web research / browsing agents, multi-hop reading, reasoning, honest "not found" |
| **B. Small workers** | 1–5B at Q5 (≤ about 4 GB file) | Reading passages accurately, extracting facts with sources, following a JSON format, instruction following |
| **C. Fact-checker / verifier** | 1–8B at Q5 | Groundedness: deciding whether a passage supports a claim (hallucination detection) |
| **D. Coordinator alternatives** | 8–15B dense at Q5 | Planning, multi-step reasoning, deciding next steps, judging when an answer is complete |
| **E. Teacher for distillation** (runs alone, may be split GPU+RAM, slow is OK) | up to about 30B dense at Q5 **or** MoE whose Q5 file fits ≤ about 24 GB total GPU+RAM | Best possible answers on research/multi-hop/reasoning tasks |
| **F. Distillation students** | 0.5–4B base or instruct models that are good targets for LoRA fine-tuning | Strong base quality for their size, permissive license, active fine-tuning ecosystem (Unsloth support) |

## Which models to consider
- Released or updated **January 2026 or later** (note anything older that still beats newer ones).
- Check the **full lab list**, not just the big names:
  - Top tier: Qwen, Google (Gemma), Meta, Mistral, DeepSeek, Microsoft (Phi), NVIDIA (Nemotron), IBM (Granite), OpenAI (gpt-oss)
  - Second tier: Ai2 (OLMo), Xiaomi (MiMo), Zhipu (GLM), Baidu (ERNIE), AI21 (Jamba), Kakao (Kanana), NAVER (HyperCLOVA X), ServiceNow (Apriel), Swiss AI (Apertus), Essential AI, TII (Falcon), Zyphra, InternLM, Liquid AI (LFM), OpenBMB (MiniCPM), LG (EXAONE), Upstage, Cohere, Arcee, Nous, Ornith AI, XiaomiMiMo, Aleph Alpha, Prism ML (Bonsai)
  - Plus anything trending on Hugging Face in these size ranges.
- Include strong **fine-tunes/distills** (like MiMo-Distill or Ornith) if they publish evals.

## Already on the PC (compare against these; don't re-recommend unless clearly better)
MiMo-V2.6-Distill-Qwen-9B, Qwen3.5 (0.8B/2B/4B/9B), Qwen3.8-27B (IQ3), Gemma-4 (E2B/E4B/12B QAT/26B-A4B/31B QAT), Apertus-v1.5-8B, EXAONE-4.0-1.2B, Falcon-H1R-7B, Granite (4.1-3B, 4.2-3B/8B, Guardian-4.1-8B), LFM2.5 (1.2B/2.6B), Ministral-3 (3B/8B/14B), Phi-4-mini, Olmo-3-7B, Nemotron-Nano-9B-v2, gpt-oss-20b, Ornith-1.5-9B and Gemma-4-12B-it Q5 (being added).

## Benchmarks to report (when available)
- **Research / agentic:** BrowseComp, FRAMES, WideSearch, SimpleQA, HotpotQA/MuSiQue
- **Reasoning / knowledge:** GPQA Diamond, MMLU-Pro, HLE
- **Instruction following:** IFEval / IFBench
- **Long context:** RULER, AA-LCR
- **Groundedness / hallucination** (for verifiers): e.g. LLM-AggreFact, FaithBench, HHEM-style leaderboards

## Output format
For each role, a table of the top 3–5 candidates:

| Model | Lab | Released | Params (dense/MoE, active) | Best GGUF repo + exact file at Q5 | File size | Fits our role? | Key benchmarks (with source) | License | Architecture notes |

Then for each role, one paragraph: your top pick and why.

**Rules:**
1. **Cite a source for every benchmark number** (model card, paper, leaderboard URL), and mark whether it is **self-reported by the lab** or **independent** (e.g. Artificial Analysis, LMArena, Open LLM Leaderboard, third-party evals). Flag claims that look too good for the size.
2. Give **exact GGUF file names and byte sizes** from the Hugging Face repo, and prefer the lab's own repo, ggml-org, unsloth or bartowski. Note if no Q5 GGUF exists.
3. **Architecture notes:** attention type and KV-cache cost. Hybrid/linear attention (like Qwen3.5) or sliding-window (like Gemma 4) is cheaper for long context than standard attention. Also note context length, thinking/no-thinking switch, and chat-template quirks.
4. **llama.cpp compatibility:** confirm the architecture is supported in llama.cpp (and since which build), or say it is not.
5. **Diversity:** note each model's base model/lineage (e.g. "fine-tune of Qwen3.5-9B"). We want workers from **different families**, so lineage matters as much as score.
6. Keep it factual. If something can't be verified, say "unverified".
