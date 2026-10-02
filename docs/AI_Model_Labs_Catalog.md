<!-- Converted from AI_Model_Labs_Catalog.docx (Codex, sources checked 2026-10-01) so it is searchable and diffable. The .docx is the original. -->

Original model creators with downloadable weights

Version 1 • Sources checked October 1 2026

This reference contains 59 creator and research-project entries. It
covers familiar companies, smaller labs, nonprofits and academic
collaborations that have released their own pretrained model lineages.
It is designed to help you find distinct model families for local
testing.

The main language-model entries include a plausible small or quantized
local option. Specialized image, video and audio creators are included
too, with hardware limits clearly marked. A separate watchlist covers
large models and cases needing additional verification.

# Admission rule

A creator must have evidence of original foundation or base-model
training and downloadable weights in its own lineage. A fine-tune,
merge, wrapper or distillation of an external base does not establish
admission by itself. A lab that also makes derivatives can still qualify
through an independent model.

Reusing an architecture, tokenizer, dataset or training framework does
not automatically make a model derivative. For multimodal systems, the
original generative or perception backbone is distinguished from reused
encoders and codecs.

# What this edition establishes

This is a broad, source-linked first edition, not a complete census of
every university team or a ranking. Model examples prove a lineage and
provide a starting point; they are not claims about the smallest,
largest or newest model currently available. Founding dates and current
staffing are not inferred.

Open-weight means the weights can be obtained under stated terms. It
does not always mean unrestricted open source, commercial permission or
immediate ungated access.

# How to use the hardware notes

Hardware reference: your RTX 5060 Ti with 16GB VRAM, approximately 16GB
system RAM, Windows and llama-server. Fit labels are estimates from
model size and pipeline requirements, not measurements on your machine.

Good small-model fit: a compact language checkpoint should leave useful
headroom. For 7B through 14B models, quantization and a moderate context
are usually the sensible starting point.

Conditional fit: memory, context length, quantization, offloading and
runtime support must be checked together. Do not read this label as a
guarantee that the model runs comfortably.

Poor default fit: useful for the creator map, but not a practical next
download on your present machine. Video and image models also need
encoders, decoders and working memory.

MoE active parameters describe the work per token, not the full set of
weights that must be stored. A 230B model with 10B active parameters is
not a 10B-memory model.

# GGUF and llama server

GGUF availability and executable support are separate questions. A
community conversion is not proof that your installed llama-server
binary supports its architecture, chat template, vision projector, audio
interface or tool parser.

Use the official model source first. Then check its linked quantizations
and the exact runtime version. This edition does not certify every
checkpoint as llama.cpp compatible. Specialized generation and speech
entries normally need a separate runtime.

Runtime project: [<u>llama.cpp official
repository</u>](https://github.com/ggml-org/llama.cpp)

# Useful additions to your testing pool

For additional compact language lineages, investigate SmolLM, Granite,
Liquid LFM, EXAONE, Arcee AFM and Rnj 1. OLMo, Pythia and AMD OLMo are
particularly useful when training provenance and controlled experiments
matter.

Record base versus instruct versus reasoning variants, native reasoning
mode, quantization, context, runtime version, token budget and
wall-clock time. A distinct lab is not automatically a distinct
architecture or an independent training-data distribution.

# Creator entries

## 1 Alibaba Qwen

**Geography** China

**Model examples** Qwen3 0.6B; broad language, vision and coding
families

**Architecture** Dense and MoE

**License example** Apache 2.0 for cited Qwen3

**Your hardware** Good small-model fit

Own pretraining and post-training pipeline. Particularly useful for
comparing model sizes within one family; avoid assuming identical
reasoning behavior across generations.

[<u>Official source and model
access</u>](https://huggingface.co/Qwen/Qwen3-0.6B)

## 2 Google DeepMind

**Geography** United States and United Kingdom

**Model examples** Gemma 3 1B; 4B, 12B and 27B in the cited generation

**Architecture** Dense transformer

**License example** Gemma terms

**Your hardware** Good small-model fit

Original Gemma pretraining is documented. The 1B example is text only;
larger Gemma 3 variants add vision. Your existing Gemma results should
remain separate from this older generation.

[<u>Official source and model
access</u>](https://huggingface.co/google/gemma-3-1b-it)

# Creator entries

## 3 Meta AI

**Geography** United States

**Model examples** Llama 3.2 1B and 3B; Llama 3.1 8B reference

**Architecture** Dense transformer

**License example** Llama community license

**Your hardware** Good small-model fit

Meta qualifies through its original Llama pretraining. Small Llama 3.2
models use pruning and distillation within Meta's own lineage; they are
not independent from-scratch baselines.

[<u>Official source and model
access</u>](https://huggingface.co/meta-llama/Llama-3.2-1B)

## 4 Mistral AI

**Geography** France

**Model examples** Ministral 8B; Mistral language and coding families

**Architecture** Dense and MoE across families

**License example** Mistral Research License for cited release

**Your hardware** Good quantized fit

Original model developer. The cited Ministral release permits research
under its own terms; do not transfer the Apache license of other Mistral
releases to it.

[<u>Official source and model
access</u>](https://huggingface.co/mistralai/Ministral-8B-Instruct-2410)

# Creator entries

## 5 Microsoft Research

**Geography** United States

**Model examples** Phi 4 14B; Phi small-model family

**Architecture** Dense transformer

**License example** MIT for cited Phi 4

**Your hardware** Good quantized fit at moderate context

Original Phi pretraining uses curated and synthetic data. Synthetic
teacher-generated data does not itself mean a model was initialized from
someone else's weights.

[<u>Official source and model
access</u>](https://huggingface.co/microsoft/phi-4)

## 6 IBM Research

**Geography** United States

**Model examples** Granite 3.3 2B Instruct

**Architecture** Dense transformer for example

**License example** Apache 2.0

**Your hardware** Good small-model fit

IBM's own Granite base underlies the instruction model. Relevant to
tools, retrieval, structured output and reasoning-mode comparisons.

[<u>Official source and model
access</u>](https://huggingface.co/ibm-granite/granite-3.3-2b-instruct)

# Creator entries

## 7 NVIDIA Research

**Geography** United States

**Model examples** Nemotron H 8B Base; SANA and Cosmos specialized
families

**Architecture** Hybrid Mamba and attention; other architectures by
family

**License example** NVIDIA model terms vary by release

**Your hardware** Good size fit; runtime check needed

Nemotron H supplies original pretraining evidence. Some other
Nemotron-branded models adapt external bases, so the NVIDIA name alone
is not proof of an independent lineage.

[<u>Official source and model
access</u>](https://huggingface.co/nvidia/Nemotron-H-8B-Base-8K)

## 8 OpenAI

**Geography** United States

**Model examples** gpt oss 20B; 120B larger reference

**Architecture** MoE with MXFP4 expert weights

**License example** Apache 2.0

**Your hardware** Conditional 16GB fit

The model card describes 20B deployment within 16GB memory. Reserve room
for context and runtime buffers; use the required Harmony format. The
120B release exceeds your practical budget.

[<u>Official source and model
access</u>](https://huggingface.co/openai/gpt-oss-20b)

# Creator entries

## 9 Ai2 Allen Institute for AI

**Geography** United States

**Model examples** OLMo 7B; Olmo 3 7B and 32B

**Architecture** Dense transformer for these examples

**License example** Apache 2.0

**Your hardware** Good quantized 7B fit

Original pretraining, data and training details are released. Especially
valuable for reproducible research rather than only leaderboard
comparisons.

[<u>Official source and model
access</u>](https://huggingface.co/allenai/Olmo-3-1025-7B)

## 10 AMD

**Geography** United States

**Model examples** AMD OLMo 1B; approximately 1.2B actual parameters

**Architecture** OLMo transformer architecture

**License example** Apache 2.0

**Your hardware** Good small-model fit

AMD explicitly trained this model from scratch on MI250 GPUs. Reusing
Ai2's architecture and training code does not make the weights a
fine-tune of Ai2's model.

[<u>Official source and model
access</u>](https://huggingface.co/amd/AMD-OLMo-1B)

# Creator entries

## 11 Hugging Face SmolLM team

**Geography** France and United States

**Model examples** SmolLM2 135M, 360M and 1.7B; SmolLM3 3B

**Architecture** Dense transformer

**License example** Apache 2.0 for SmolLM2

**Your hardware** Good small-model fit

Hugging Face is both a hosting platform and an original model developer.
Count the SmolLM team, not every publisher hosted on the Hub.

[<u>Official source and model
access</u>](https://huggingface.co/HuggingFaceTB/SmolLM2-135M)

## 12 EleutherAI

**Geography** United States and distributed community

**Model examples** Pythia 70M through 12B

**Architecture** GPT NeoX transformer

**License example** Apache 2.0

**Your hardware** Good small-model fit

Pythia provides original training and intermediate checkpoints. Older
base models suit controlled experiments; they are not modern instruction
assistants out of the box.

[<u>Official source and model
access</u>](https://huggingface.co/EleutherAI/pythia-1b)

# Creator entries

## 13 BigScience collaboration

**Geography** International with French compute infrastructure

**Model examples** BLOOM 560M; larger multilingual family

**Architecture** Dense transformer

**License example** BLOOM RAIL terms

**Your hardware** Good small-model fit

An original collaborative pretraining project rather than a conventional
company. Treat it as a historical research lineage, not proof of a
currently staffed commercial lab.

[<u>Official source and model
access</u>](https://huggingface.co/bigscience/bloom-560m)

## 14 Cerebras

**Geography** United States

**Model examples** Cerebras GPT 111M through 13B

**Architecture** GPT transformer

**License example** Apache 2.0

**Your hardware** Good small-model fit

Original compute-efficient pretraining family with public weights and
recipes. Older checkpoints are useful experimental baselines.

[<u>Official source and model
access</u>](https://www.cerebras.ai/blog/cerebras-gpt-a-family-of-open-compute-efficient-large-language-models)

# Creator entries

## 15 Databricks MosaicML

**Geography** United States

**Model examples** MPT 7B; DBRX larger family

**Architecture** Dense MPT; MoE DBRX

**License example** Apache 2.0 for MPT 7B base; variants differ

**Your hardware** Good quantized MPT fit

MPT 7B was trained from scratch on one trillion tokens. MosaicML is
grouped with its owner rather than counted as an additional independent
company.

[<u>Official source and model
access</u>](https://www.databricks.com/blog/mpt-7b)

## 16 Salesforce Research

**Geography** United States

**Model examples** CodeGen 350M, 2B, 6B and 16B

**Architecture** Dense autoregressive transformer

**License example** BSD 3 clause for CodeGen

**Your hardware** Good small-model fit

Original code-model lineage. Mono continues from Salesforce's own Multi
model; use the NL origin when proving independence. Useful for code
completion rather than general agent chat.

[<u>Official source and model
access</u>](https://huggingface.co/Salesforce/codegen-350M-mono)

# Creator entries

## 17 Liquid AI

**Geography** United States

**Model examples** LFM2 350M, 700M, 1.2B and 2.6B; newer LFM2.5 variants

**Architecture** Hybrid gated convolution and attention

**License example** Liquid model license; version-specific

**Your hardware** Good small-model fit

Original architecture and training program aimed at local deployment.
Cited model card includes llama.cpp instructions. Compare speed and
successful task completion together.

[<u>Official source and model
access</u>](https://huggingface.co/LiquidAI/LFM2-1.2B)

## 18 Zyphra

**Geography** United States

**Model examples** Zamba2 1.2B

**Architecture** Hybrid state-space and attention

**License example** Apache 2.0 for cited release

**Your hardware** Good size fit; separate runtime may help

Original pretrained Zamba family. The cited checkpoint is a base model
and is not instruction-tuned, which matters when comparing it with chat
models.

[<u>Official source and model
access</u>](https://huggingface.co/Zyphra/Zamba2-1.2B)

# Creator entries

## 19 RWKV project

**Geography** Distributed with Chinese origin

**Model examples** RWKV 6 Finch 1.6B; larger 7B and 14B references

**Architecture** Recurrent RWKV architecture

**License example** Apache 2.0 for cited checkpoint

**Your hardware** Good size fit; architecture-specific runtime

Independent recurrent language-model lineage. Track architecture and
recurrent state separately from transformer context and KV-cache
behavior.

[<u>Official source and model
access</u>](https://huggingface.co/RWKV/v6-Finch-1B6-HF)

## 20 Mamba research collaboration

**Geography** United States academic collaboration

**Model examples** Mamba 130M and larger research checkpoints

**Architecture** Selective state-space model

**License example** Apache 2.0 for cited checkpoint

**Your hardware** Good size fit; runtime check needed

Original language-model pretraining research. This is a project/team
entry, not an additional commercial lab. The cited card has a copied
size description, so use configuration files for exact tensor counts.

[<u>Official source and model
access</u>](https://huggingface.co/state-spaces/mamba-130m-hf)

# Creator entries

## 21 Arcee AI

**Geography** United States

**Model examples** AFM 4.5B Base

**Architecture** Dense transformer with ReLU squared

**License example** Apache 2.0

**Your hardware** Good quantized fit

AFM documents Arcee's own eight-trillion-token training. Earlier Arcee
merges and adaptations do not establish this qualification; AFM does.

[<u>Official source and model
access</u>](https://huggingface.co/arcee-ai/AFM-4.5B-Base)

## 22 Essential AI

**Geography** United States

**Model examples** Rnj 1 8B class

**Architecture** Dense transformer

**License example** Apache 2.0

**Your hardware** Good quantized fit

Explicitly trained from scratch. Focuses on code, STEM and tool calling,
making it relevant to specialist-agent testing.

[<u>Official source and model
access</u>](https://huggingface.co/EssentialAI/rnj-1)

# Creator entries

## 23 JetBrains

**Geography** Czech origin with international operations

**Model examples** Mellum 4B Base

**Architecture** Dense transformer

**License example** Apache 2.0

**Your hardware** Good quantized fit

Original code-model training on about 4.2 trillion tokens. Base
completion and Python SFT variants should be treated as different
evaluation conditions.

[<u>Official source and model
access</u>](https://huggingface.co/JetBrains/Mellum-4b-base)

## 24 Cohere and Cohere Labs

**Geography** Canada

**Model examples** Command R7B December 2024; Aya language families

**Architecture** Dense transformer for example

**License example** CC BY NC 4.0 for cited release

**Your hardware** Good quantized fit

Original Command-family developer. Relevant to retrieval and multi-step
tools. Downloadable research weights do not imply unrestricted
commercial rights.

[<u>Official source and model
access</u>](https://huggingface.co/CohereLabs/c4ai-command-r7b-12-2024)

# Creator entries

## 25 Reka AI

**Geography** United States

**Model examples** Reka Flash 3 21B

**Architecture** Dense transformer

**License example** Apache 2.0

**Your hardware** Conditional quantized fit

The official card explicitly states training from scratch. A 21B model
may fit at four bits with limited context, but is a tighter choice than
a 7B or 9B model.

[<u>Official source and model
access</u>](https://huggingface.co/RekaAI/reka-flash-3)

## 26 Aleph Alpha

**Geography** Germany

**Model examples** Pharia 1 LLM 7B control and aligned variants

**Architecture** Dense transformer

**License example** Open Aleph License

**Your hardware** Good size fit; runtime check needed

Original Pharia foundation-model family. Public research and educational
access is distinct from commercial permission.

[<u>Official source and model
access</u>](https://aleph-alpha.com/en/blog/introducing-pharia-1-llm-transparent-and-compliant/)

# Creator entries

## 27 DeepSeek

**Geography** China

**Model examples** DeepSeek LLM 7B and 67B; coding and reasoning
families

**Architecture** Dense and MoE across generations

**License example** DeepSeek model license for cited LLM

**Your hardware** Good quantized 7B fit

Cited LLM explicitly trained from scratch. R1 Distill Qwen and R1
Distill Llama checkpoints inherit external bases; do not label those
independent DeepSeek base models.

[<u>Official source and model
access</u>](https://huggingface.co/deepseek-ai/deepseek-llm-7b-base)

## 28 01 AI

**Geography** China

**Model examples** Yi 6B; Yi larger bilingual family

**Architecture** Dense transformer

**License example** Apache 2.0 for cited release

**Your hardware** Good quantized fit

Official card describes Yi as trained from scratch. An older but
distinct model lineage for family-diversity experiments.

[<u>Official source and model
access</u>](https://huggingface.co/01-ai/Yi-6B)

# Creator entries

## 29 Shanghai AI Laboratory InternLM team

**Geography** China

**Model examples** InternLM 2.5 7B

**Architecture** Dense transformer

**License example** Model-specific InternLM terms

**Your hardware** Good quantized fit

Original InternLM language-model family. InternVL uses multiple
components, so multimodal lineage must be recorded component by
component.

[<u>Official source and model
access</u>](https://huggingface.co/internlm/internlm2_5-7b)

## 30 Zhipu Z ai with THUDM collaboration

**Geography** China

**Model examples** GLM 4 9B; CogVideo and other specialized families

**Architecture** Dense and MoE by generation

**License example** GLM model license for cited release

**Your hardware** Good quantized 9B fit

Original GLM pretraining lineage with university collaboration. Group
the connected commercial and THUDM release lineage to avoid double
counting the same model.

[<u>Official source and model
access</u>](https://huggingface.co/zai-org/glm-4-9b)

# Creator entries

## 31 Tencent Hunyuan

**Geography** China

**Model examples** Hunyuan 0.5B Pretrain; HunyuanVideo

**Architecture** Dense and MoE language; video diffusion

**License example** Tencent model-specific terms

**Your hardware** Good small-language-model fit

Own language and video training pipelines. Video inference is a separate
workload from llama-server and may need substantial offloading.

[<u>Official source and model
access</u>](https://huggingface.co/tencent/Hunyuan-0.5B-Pretrain)

## 32 Baidu

**Geography** China

**Model examples** ERNIE 4.5 0.3B PT

**Architecture** Dense small model; MoE elsewhere

**License example** Apache 2.0 for cited release

**Your hardware** Good small-model fit

Original ERNIE pretraining family with small downloadable checkpoints. A
PT model is a base checkpoint, not an instruction assistant.

[<u>Official source and model
access</u>](https://huggingface.co/baidu/ERNIE-4.5-0.3B-PT)

# Creator entries

## 33 Xiaomi MiMo

**Geography** China

**Model examples** MiMo 7B Base, SFT and RL variants

**Architecture** Dense transformer for example

**License example** MIT for cited release

**Your hardware** Good quantized fit

MiMo 7B explicitly trained from scratch on about 25 trillion tokens.
Keep native-base, SFT and RL variants distinct in reasoning experiments.

[<u>Official source and model
access</u>](https://huggingface.co/XiaomiMiMo/MiMo-7B-Base)

## 34 ByteDance Seed

**Geography** China

**Model examples** Seed Coder 8B Base, Instruct and Reasoning

**Architecture** Dense transformer for example

**License example** MIT for cited release

**Your hardware** Good quantized fit

Own code-model pretraining on six trillion tokens. ByteDance's other
research teams and video releases belong under the same parent
organization.

[<u>Official source and model
access</u>](https://huggingface.co/ByteDance-Seed/Seed-Coder-8B-Base)

# Creator entries

## 35 OpenCoder Infly collaboration

**Geography** China with academic collaborators

**Model examples** OpenCoder 1.5B and 8B

**Architecture** Dense transformer

**License example** Apache 2.0

**Your hardware** Good small-model fit

Explicit original pretraining on 2.5 trillion tokens with code-heavy
data. A collaboration entry, not a count of every participating
institution.

[<u>Official source and model
access</u>](https://huggingface.co/infly/OpenCoder-1.5B-Instruct)

## 36 LG AI Research

**Geography** South Korea

**Model examples** EXAONE 3.5 2.4B, 7.8B and 32B

**Architecture** Dense transformer for examples

**License example** EXAONE research license for cited generation

**Your hardware** Good small-model fit

Original bilingual model family. License terms change by release; do not
assume a newer permissive license applies backward to EXAONE 3.5.

[<u>Official source and model
access</u>](https://huggingface.co/LGAI-EXAONE/EXAONE-3.5-2.4B-Instruct)

# Creator entries

## 37 NAVER HyperCLOVA X

**Geography** South Korea

**Model examples** HyperCLOVAX SEED Text Instruct 0.5B

**Architecture** Dense transformer

**License example** Check SEED license for exact release

**Your hardware** Good small-model fit

Own model training and training cost are documented. Korean-oriented
capability makes this useful as a language specialist, not automatically
an English reasoning replacement.

[<u>Official source and model
access</u>](https://huggingface.co/naver-hyperclovax/HyperCLOVAX-SEED-Text-Instruct-0.5B)

## 38 National Institute of Informatics LLM jp

**Geography** Japan

**Model examples** LLM jp 3 1.8B, 3.7B and 13B; larger beta

**Architecture** Dense transformer

**License example** Apache 2.0 for cited model

**Your hardware** Good small-model fit

Original Japanese and English pretraining with datasets and tokenizer
details. Base and instruction versions are both listed.

[<u>Official source and model
access</u>](https://huggingface.co/llm-jp/llm-jp-3-1.8b)

# Creator entries

## 39 rinna

**Geography** Japan

**Model examples** Japanese GPT NeoX 3.6B; bilingual 4B

**Architecture** GPT NeoX transformer

**License example** Check checkpoint license

**Your hardware** Good small-model fit

Research paper establishes original Japanese pretraining. Other rinna
releases adapt Gemma or Llama; the company qualifies through its
independent GPT NeoX lineage.

[<u>Official source and model
access</u>](https://arxiv.org/html/2404.01657v1)

## 40 SB Intuitions

**Geography** Japan

**Model examples** Sarashina 2.2 3B

**Architecture** Dense transformer

**License example** MIT for cited model

**Your hardware** Good small-model fit

Own multistage training begins with ten trillion Japanese, English and
code tokens. Useful for Japanese-specialist comparisons.

[<u>Official source and model
access</u>](https://huggingface.co/sbintuitions/sarashina2.2-3b)

# Creator entries

## 41 Technology Innovation Institute

**Geography** United Arab Emirates

**Model examples** Falcon3 1B; Falcon original 7B and 40B lineage

**Architecture** Dense transformer and later architecture variants

**License example** Falcon license varies by generation

**Your hardware** Good small-model fit

TII qualifies through original Falcon pretraining. Falcon3 1B was pruned
and distilled from its own 3B model, so it is not an independent
from-scratch 1B control.

[<u>Official source and model
access</u>](https://huggingface.co/tiiuae/Falcon3-1B-Base)

## 42 Inception MBZUAI and Cerebras Jais collaboration

**Geography** United Arab Emirates and United States

**Model examples** Jais 2 8B and 70B

**Architecture** Dense transformer

**License example** Check cited Jais model license

**Your hardware** Good quantized 8B fit

Jais 2 is explicitly pretrained from scratch on Arabic, English and
code. Cerebras appears elsewhere as a creator too; shared projects are
not independent extra companies.

[<u>Official source and model
access</u>](https://www.cerebras.ai/blog/jais2)

# Creator entries

## 43 Swiss AI Initiative ETH EPFL CSCS

**Geography** Switzerland

**Model examples** Apertus 8B and 70B

**Architecture** Dense transformer with xIELU

**License example** Apache 2.0

**Your hardware** Good quantized 8B fit

Explicit original pretraining on 15 trillion tokens with open training
details. Check exact llama.cpp architecture support; community GGUF
releases exist.

[<u>Official source and model
access</u>](https://huggingface.co/swiss-ai/Apertus-8B-2509)

## 44 OpenLLM France collaboration

**Geography** France

**Model examples** Lucie 7B

**Architecture** Dense transformer

**License example** Apache 2.0

**Your hardware** Good quantized fit

Original multilingual pretraining with public data and checkpoints.
LINAGORA, research institutions and compute partners are represented as
one collaboration.

[<u>Official source and model
access</u>](https://huggingface.co/OpenLLM-France/Lucie-7B)

# Creator entries

## 45 Polygl0t research initiative

**Geography** Germany with international collaborators

**Model examples** Tucano2 0.6B; LilMoo Hindi and LilTii Bengali

**Architecture** Dense transformer

**License example** Check each checkpoint license

**Your hardware** Good small-model fit

Tucano2 0.6B is natively pretrained with open data and recipes. Other
Tucano2 variants continue from Qwen, so only the independent branch
proves admission.

[<u>Official source and model
access</u>](https://huggingface.co/Polygl0t/Tucano2-0.6B-Base)

## 46 Finnish NLP research team

**Geography** Finland

**Model examples** Ahma 3B

**Architecture** Llama-style transformer architecture

**License example** Check checkpoint license

**Your hardware** Good small-model fit

The card explicitly states pretraining from scratch in Finnish. Reusing
Llama's architecture is different from reusing Llama's trained weights.

[<u>Official source and model
access</u>](https://huggingface.co/Finnish-NLP/Ahma-3B)

# Creator entries

## 47 Black Forest Labs

**Geography** Germany

**Model examples** FLUX 1 schnell 12B; broader FLUX visual lineage

**Architecture** Flow-based diffusion transformer

**License example** Apache 2.0 for schnell

**Your hardware** Conditional quantized and offloaded fit

Original image-model developer. A pipeline also needs text encoders and
a VAE; the 12B denoiser count is not total pipeline memory.

[<u>Official source and model
access</u>](https://huggingface.co/black-forest-labs/FLUX.1-schnell)

## 48 Stability AI

**Geography** United Kingdom with international collaborators

**Model examples** SDXL; Stable Diffusion image and video families

**Architecture** Latent diffusion

**License example** Open RAIL or Stability terms by model

**Your hardware** Good SDXL size fit with suitable software

Original generative-model research includes substantial university
collaboration. Treat model code, weights and inherited components as
separate licensing objects.

[<u>Official source and model
access</u>](https://github.com/Stability-AI/generative-models)

# Creator entries

## 49 Lightricks

**Geography** Israel

**Model examples** LTX Video 2B and 13B; LTX 2 audio-video

**Architecture** Diffusion transformer

**License example** LTX weight license; code license differs

**Your hardware** Good older 2B fit; larger releases conditional

Original visual-generation research. The official repository points to
newer LTX 2; the 2B example remains a smaller entry point, not the
latest flagship.

[<u>Official source and model
access</u>](https://github.com/Lightricks/LTX-Video)

## 50 Genmo

**Geography** United States

**Model examples** Mochi 1 10B

**Architecture** Asymmetric diffusion transformer

**License example** Apache 2.0

**Your hardware** Poor default fit; heavy offloading needed

Original video foundation model with pretrained weights. Keep this entry
for landscape coverage; it is not a comfortable default on 16GB RAM.

[<u>Official source and model
access</u>](https://github.com/genmoai/mochi)

# Creator entries

## 51 HiDream ai

**Geography** China

**Model examples** HiDream I1 17B

**Architecture** Image diffusion transformer

**License example** MIT for transformer; component licenses differ

**Your hardware** Poor default fit; pipeline is large

Original image-generation backbone uses external FLUX VAE and T5 and
Llama text encoders. Original backbone training can qualify a lab
without making every component original.

[<u>Official source and model
access</u>](https://huggingface.co/HiDream-ai/HiDream-I1-Full)

## 52 fal AuraFlow team

**Geography** United States with international developers

**Model examples** AuraFlow 0.3 approximately 6.8B

**Architecture** Flow-based image transformer

**License example** Apache 2.0

**Your hardware** Conditional quantized or offloaded fit

Original AuraFlow visual-model project. Small company research can
coexist with a hosted-inference business; service providers are not
automatically derivative-only labs.

[<u>Official source and model
access</u>](https://huggingface.co/fal/AuraFlow-v0.3)

# Creator entries

## 53 Kyutai

**Geography** France

**Model examples** Moshi 7B; smaller streaming speech models

**Architecture** Multi-stream speech and text transformer

**License example** Checkpoint-specific; Moshi weights CC BY 4.0

**Your hardware** Smaller speech models good; Moshi conditional

Original Moshi training was developed from scratch. Speech and audio
components require their own runtime and memory measurements.

[<u>Official source and model
access</u>](https://github.com/kyutai-labs/moshi)

## 54 Nari Labs

**Geography** South Korea and international team

**Model examples** Dia 1.6B dialogue speech model

**Architecture** Audio-generating transformer

**License example** Apache 2.0

**Your hardware** Good size fit with audio runtime

Original dialogue speech model with public pretrained checkpoints. It
supports transcript-conditioned dialogue and nonverbal sounds; it is not
a general text reasoning model.

[<u>Official source and model
access</u>](https://github.com/nari-labs/dia)

# Creator entries

## 55 Suno

**Geography** United States

**Model examples** Bark small and standard checkpoints

**Architecture** Three-stage audio transformer pipeline

**License example** MIT

**Your hardware** Good smaller-pipeline fit

Suno released an original text-to-audio lineage. Bark's availability
does not imply that Suno's current commercial music-model weights are
downloadable.

[<u>Official source and model
access</u>](https://github.com/suno-ai/bark)

## 56 Nomic AI

**Geography** United States

**Model examples** Nomic Embed Text v1 approximately 137M

**Architecture** Long-context BERT encoder

**License example** Apache 2.0

**Your hardware** Good small-model fit

Own encoder pretraining and embedding pipeline with released data and
training code. Useful for retrieval and memory; not a chat or reasoning
model.

[<u>Official source and model
access</u>](https://huggingface.co/nomic-ai/nomic-embed-text-v1)

# Creator entries

## 57 Jina AI

**Geography** Germany with international operations

**Model examples** Jina Embeddings v2 small 33M and base 137M

**Architecture** Jina BERT encoder with ALiBi

**License example** Apache 2.0 for cited v2 model

**Your hardware** Good small-model fit; access conditions apply

Original Jina BERT pretraining underlies the v2 embeddings. Later
embedding releases may use different external bases and licenses; do not
extrapolate v2 provenance to all releases.

[<u>Official source and model
access</u>](https://huggingface.co/jinaai/jina-embeddings-v2-base-en)

## 58 Octo robotics collaboration

**Geography** United States academic and industry collaboration

**Model examples** Octo Small 27M and Base 93M

**Architecture** Transformer diffusion action policy

**License example** MIT; check inherited components

**Your hardware** Good model-size fit; robotics runtime needed

Original generalist action policy pretrained on 800000 robot episodes.
Reuses a language encoder. Local inference is possible without making it
a ready-made robot; deployment needs compatible observations and action
spaces.

[<u>Official source and model
access</u>](https://octo-models.github.io/)

# Creator entries

## 59 EvolutionaryScale ESM team

**Geography** United States

**Model examples** ESM3 Open 1.4B protein model

**Architecture** Multimodal protein transformer

**License example** Current weight terms must be checked

**Your hardware** Good size fit; scientific runtime needed

Original sequence, structure and function modeling. Official release
prose and current license pages differ, so do not assume MIT applies to
the downloaded weights. A scientific foundation model, not an assistant.

[<u>Official source and model
access</u>](https://www.evolutionaryscale.ai/blog/esm3-release)

# Large models and additional candidates

These entries prevent useful names from disappearing from the map. They
are not included in the main-entry count or certified as practical
downloads for your machine.

## Sarvam AI India

Original Sarvam 30B and 105B MoE models are explicitly trained from
scratch. The 30B has 2.4B non-embedding active parameters but still
needs storage for the full model. Four-bit deployment may be possible
with careful memory planning; verify support before downloading.

[<u>Official source and model
access</u>](https://www.sarvam.ai/blogs/sarvam-30b-105b)

## Moonshot AI China

Kimi K2 proves independent pretraining but its 1T total parameters are
far beyond your PC. Kimi Audio 7B is a smaller specialist release worth
investigating; it needs a separate audio runtime and pipeline-memory
check.

[<u>Official source and model
access</u>](https://huggingface.co/moonshotai/Kimi-K2-Base)

## MiniMax China

MiniMax develops its own large MoE lineage. M2 has approximately 230B
total parameters despite only about 10B being active. It is not a
comfortable local option for your current hardware.

[<u>Official source and model
access</u>](https://huggingface.co/MiniMaxAI/MiniMax-M2)

# Additional candidates continued

## AI21 Labs Israel

Jamba is an original hybrid transformer and Mamba MoE family. The cited
52B total-parameter release is beyond a comfortable default fit on your
PC.

[<u>Official source and model
access</u>](https://huggingface.co/ai21labs/Jamba-v0.1)

## LumiOpen and Silo AI Finland

Poro 34B is an original multilingual model with open parameters and
recipes. Later Llama Poro models adapt Llama; distinguish them from the
original Poro lineage. The 34B model is a tight fit.

[<u>Official source and model
access</u>](https://arxiv.org/html/2404.01856v3)

## AI Sweden Sweden

GPT SW3 documents original pretraining. The inspected 1.3B repository
restricts access to eligible European academic and research users. Small
enough does not mean obtainable by every individual.

[<u>Official source and model
access</u>](https://huggingface.co/AI-Sweden-Models/gpt-sw3-1.3b)

# Additional candidates continued

## StepFun China

Step Audio TTS 3B is a potential smaller local release. Verify the
precise base lineage and complete speech-pipeline memory before
admitting it as an independently pretrained small model.

[<u>Official source and model
access</u>](https://github.com/stepfun-ai/Step-Audio)

## Resemble AI

Chatterbox offers compact downloadable speech models. The public
repository establishes the developer and release, but this edition has
not fully established initialization provenance for every component.

[<u>Official source and model
access</u>](https://github.com/resemble-ai/chatterbox)

## Sesame AI Labs

CSM provides downloadable conversational-speech weights and uses a Llama
backbone plus Mimi codes. Architecture naming alone does not establish
whether language weights were inherited; keep this provenance question
open.

[<u>Official source and model
access</u>](https://github.com/SesameAILabs/csm)

# Additional candidates continued

## PixArt and Lumina academic teams

Original image-backbone research with released weights and training
code. They span overlapping institutional collaborations, including
Shanghai AI Laboratory, so do not automatically count them as separate
companies.

[<u>Official source and model
access</u>](https://github.com/Alpha-VLLM/Lumina-Image-2.0)

## China Telecom TeleAI

TeleChat technical report explicitly describes from-scratch pretraining.
Resolve the current official downloadable checkpoint and license before
adding a definitive small-model entry.

[<u>Official source and model
access</u>](https://arxiv.org/pdf/2401.03804)

## LLM360 collaboration

A relevant open-pretraining research initiative. Its official pages did
not load reliably during this pass; original release ownership, current
download access and suitable checkpoint remain to be checked.

[<u>Official source and model
access</u>](https://github.com/LLM360/LLM360)

# Maintaining the catalog

This file is editable. It does not update itself. Recheck a lab when it
announces a new lineage, changes a license, moves repositories or
releases a smaller model.

# Fields for the next verified release

**•** Lab and parent organization or collaboration

**•** Official model identifier and release date

**•** Evidence of original pretraining and any inherited components

**•** Total parameters and active parameters for MoE

**•** Weight license and access conditions

**•** Official or community GGUF location

**•** Exact runtime and version tested

**•** Measured VRAM, system RAM, context and generation speed

**•** Task success rate, reasoning mode and token budget

**•** Source URL and date checked

# Coverage limits

The count is a count of entries, not a defensible worldwide count of
independent AI corporations. It mixes companies, nonprofits and
collaborations because those all create useful original models. Parent
organizations are grouped where practical, and shared institutional
involvement is noted.

This edition emphasizes language, coding, image, video and speech
models, with initial embedding, robotics and scientific entries.
Dedicated vision encoders and wider robotics and science coverage need a
further provenance pass. Robotics systems that initialize from an
existing language or vision backbone should not be labeled entirely from
scratch simply because a new action head was trained.

Anthropic and other closed-only creators do not qualify merely because
they train original models. Fine-tune and quantization publishers can be
useful suppliers without being original model labs. Their work should be
listed beside the source model, not counted as another base-model
creator.

Source links are attached directly to entries. They establish the cited
release; successful authenticated downloads, commercial license
eligibility and execution on your PC have not been tested here.
