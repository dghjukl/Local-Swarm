import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from swarm import orchestrator, pool, preflight, procs, registry  # noqa: E402
from swarm.config import load_config  # noqa: E402

MOCK = Path(__file__).parent / "mock_llama.py"

MODELS = ["Qwen3.5-4B", "Granite-4.1-3B", "Ministral-3-3B-Instruct", "LFM2.5-2.6B",
          "Phi-4-mini-instruct", "Gemma-4-E2B-it", "Qwen3-Embedding-0.6B",
          "Qwen3.5-9B", "Ministral-3-14B-Instruct", "gpt-oss-20b", "Bonsai-2-27B",
          "Qwen3-Reranker-4B", "Broken-Reranker", "Granite-Guardian-4.1-8B"]


@pytest.fixture(autouse=True)
def extract_in_process(monkeypatch):
    monkeypatch.setenv("SWARM_EXTRACT_INPROCESS", "1")  # no worker processes in tests (one test covers them)


@pytest.fixture(autouse=True)
def no_real_hardware(request, monkeypatch):
    """Tests must not depend on the machine they run on. On the swarm PC, nvidia-smi reports the real
    GPU (other programs' VRAM changes became 'measured' model sizes) and the real free RAM can trigger
    the low-RAM eviction rule, so scheduling tests behaved differently there than in CI (2026-10-03).
    Tests that need these readings set them explicitly."""
    if "system_ram_reading" not in request.node.name:
        monkeypatch.setattr(procs, "gpu_memory_mb", lambda: None)
        monkeypatch.setattr(procs, "system_ram_mb", lambda: None)


@pytest.fixture(autouse=True)
def isolate_runtime(tmp_path, monkeypatch):
    rt = tmp_path / "runtime"
    monkeypatch.setattr(pool, "LOGS", rt / "logs")
    monkeypatch.setattr(pool, "RUNTIME", rt)
    monkeypatch.setattr(registry, "MEASURE", rt / "measurements")
    monkeypatch.setattr(orchestrator, "RUNS", rt / "runs")
    monkeypatch.setattr(preflight, "CACHE", rt / "preflight.json")
    return rt


@pytest.fixture
def models_dir(tmp_path):
    d = tmp_path / "Models"
    for m in MODELS:
        (d / m).mkdir(parents=True)
        (d / m / f"{m}-Q5_K_M.gguf").write_bytes(b"\0" * 1024)
    (d / "Qwen3.5-4B" / "mmproj-Qwen3.5-4B-bf16.gguf").write_bytes(b"\0")
    (d / "Qwen3.5-4B" / f"Qwen3.5-4B-Q8_0.gguf").write_bytes(b"\0" * 2048)
    return d


@pytest.fixture
def cards(models_dir):
    return registry.scan_models(models_dir)


class MockPool(pool.ModelPool):
    def build_cmd(self, card, port, ctx_per_slot, parallel, offload=False):
        return [sys.executable, str(MOCK), "-m", card.path, "--port", str(port), "-c", str(ctx_per_slot * parallel)]


@pytest.fixture
def cfg(tmp_path):
    c = load_config(ROOT / "config" / "swarm.yaml")
    c["gpu"]["llama_server"] = sys.executable  # must exist
    c["gpu"]["vram_budget_mb"] = 100000
    return c


@pytest.fixture
def mock_pool_cls():
    return MockPool


@pytest.fixture(autouse=True)
def no_scholarly_network(monkeypatch):
    """Tests never call the real scholarly APIs; a test can replace this stub with its own."""
    async def none(query, n=2, sources=None, since=""):
        return {}
    monkeypatch.setattr("swarm.scholar.search_all", none)
