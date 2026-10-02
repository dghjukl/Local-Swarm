"""Model registry: one card per folder in Models/.

A card starts with facts we can read from disk (file, size, lab, lineage, kind).
Measured facts (VRAM, load time, speed, test scores) are added over time by the
pool and by the qualification tests, and live in runtime/measurements/.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

from swarm.paths import MEASURE, MODELS

# folder-name prefix -> (lab that published the checkpoint, lineage of the base weights)
# Lineage matters for diversity: a DeepSeek distill of Qwen shares Qwen's mistakes.
LABS: list[tuple[str, str, str]] = [
    ("DeepSeek-R1", "DeepSeek", "Qwen"),
    ("Qwen2.5-1.5B-Python-Coder", "Community", "Qwen"),
    ("Bonsai", "Prism ML", "Qwen"),          # ternary-compressed Qwen3.8-27B
    ("Qwen", "Alibaba Qwen", "Qwen"),
    ("MiniCPM", "OpenBMB", "MiniCPM"),
    ("LFM", "Liquid AI", "LFM"),
    ("Ministral", "Mistral", "Mistral"),
    ("Granite", "IBM", "Granite"),
    ("FunctionGemma", "Google", "Gemma"),
    ("Gemma", "Google", "Gemma"),
    ("Phi", "Microsoft", "Phi"),
    ("BitNet", "Microsoft", "BitNet"),
    ("NVIDIA-Nemotron", "NVIDIA", "Nemotron"),
    ("OLMo", "Ai2", "OLMo"),
    ("SmolLM", "Hugging Face", "SmolLM"),
    ("SmolVLM", "Hugging Face", "SmolLM"),
    ("Falcon", "TII", "Falcon"),
    ("Hunyuan", "Tencent", "Hunyuan"),
    ("gpt-oss", "OpenAI", "gpt-oss"),
    # added 2026-09-29 (round 2: second-tier labs that do a lot of open, local work)
    ("MiMo", "Xiaomi", "Qwen"),                 # MiMo-V2.6-Distill-Qwen-9B: fine-tune of Qwen3.5-9B
    ("Kanana", "Kakao", "Kanana"),
    ("Jamba", "AI21", "Jamba"),
    ("Apertus", "Swiss AI", "Apertus"),
    ("rnj", "Essential AI", "rnj"),
    ("HyperCLOVAX", "NAVER", "HyperCLOVA"),
    ("Apriel", "ServiceNow", "Apriel"),
    ("ERNIE", "Baidu", "ERNIE"),
    # added 2026-10-01 (round 3: lineages from Codex's lab catalog, docs/AI_Model_Labs_Catalog.md)
    ("Llama", "Meta", "Llama"),
    ("Command-R", "Cohere", "Command"),
    ("AFM", "Arcee AI", "AFM"),
    ("EXAONE", "LG AI Research", "EXAONE"),
    ("GLM", "Zhipu / Z.ai", "GLM"),
]

# Name keywords that mark a model as NOT a general chat model.
SPECIAL_KINDS = [
    ("Embedding", "embedding"),
    ("Reranker", "reranker"),
    ("Guard", "guard"),
    ("ASR", "asr"),
    ("Audio", "audio"),
    ("VL-", "vision"),
    ("VLM", "vision"),
]

AUX_PREFIXES = ("mmproj", "tokenizer-", "vocoder-")


@dataclass
class ModelCard:
    id: str                      # folder name, used everywhere as the model id
    path: str                    # main gguf
    size_mb: int
    lab: str
    lineage: str
    kind: str = "chat"           # chat | embedding | reranker | guard | asr | audio | vision
    mmproj: str | None = None
    quant: str = ""
    measured: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)


def _lab_for(name: str) -> tuple[str, str]:
    for prefix, lab, lineage in LABS:
        if name.lower().startswith(prefix.lower()):
            return lab, lineage
    return "Unknown", name.split("-")[0]


def _kind_for(name: str) -> str:
    for key, kind in SPECIAL_KINDS:
        if key.lower() in name.lower():
            return kind
    return "chat"


def _quant_rank(fname: str) -> int:
    """Prefer Q5_K_M (good quality, modest VRAM), then Q8, then others."""
    f = fname.upper()
    for i, q in enumerate(["Q5_K_M", "Q8_0", "Q6_K", "Q4_K_M", "BF16", "F16"]):
        if q in f:
            return i
    return 99


def scan_models(models_dir: Path = MODELS) -> dict[str, ModelCard]:
    cards: dict[str, ModelCard] = {}
    if not models_dir.exists():
        return cards
    measured = load_measurements()
    for d in sorted(p for p in models_dir.iterdir() if p.is_dir()):
        ggufs = [f for f in d.glob("*.gguf")]
        main = [f for f in ggufs if not f.name.lower().startswith(AUX_PREFIXES) and "mmproj" not in f.name.lower()]
        if not main:
            continue
        main.sort(key=lambda f: (_quant_rank(f.name), f.name))
        m = main[0]
        mm = [f for f in ggufs if "mmproj" in f.name.lower()]
        lab, lineage = _lab_for(d.name)
        quant = next((q for q in ["Q5_K_M", "Q8_0", "Q6_K", "Q4_K_M", "I2_S", "BF16"] if q in m.name.upper()), "")
        cards[d.name] = ModelCard(
            id=d.name,
            path=str(m),
            size_mb=int(m.stat().st_size / 2**20),
            lab=lab,
            lineage=lineage,
            kind=_kind_for(d.name),
            mmproj=str(mm[0]) if mm else None,
            quant=quant,
            measured=measured.get(d.name, {}),
        )
    return cards


# ---------------------------------------------------------------- measurements

def _measure_file() -> Path:
    return MEASURE / "models.json"


def load_measurements() -> dict:
    f = _measure_file()
    if f.exists():
        try:
            return json.loads(f.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def record_measurement(model_id: str, key: str, value) -> None:
    """Store one observed fact about a model, e.g. key='vram_mb@16384x1'.

    Best effort: on Windows another program (antivirus, indexer) can briefly lock the
    file. Retry a few times, then give up quietly; a lost measurement must never stop a run.
    """
    import time
    for attempt in range(5):
        try:
            MEASURE.mkdir(parents=True, exist_ok=True)
            data = load_measurements()
            data.setdefault(model_id, {})[key] = value
            tmp = _measure_file().with_suffix(".tmp")
            tmp.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")
            tmp.replace(_measure_file())
            return
        except OSError:
            time.sleep(0.2 * (attempt + 1))
