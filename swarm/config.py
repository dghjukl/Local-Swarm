"""Load config/swarm.yaml into a plain nested dict with defaults filled in."""
from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

import yaml

from swarm.paths import CONFIG

DEFAULTS: dict[str, Any] = {
    "server": {"host": "127.0.0.1", "port": 8700, "open_browser": True},
    "gpu": {
        "vram_budget_mb": 14000,
        "llama_server": "Bin/llama-cuda/llama-server.exe",
        "port_range": [8200, 8299],
    },
    "coordinator": {"model": "Qwen3.5-4B", "ctx_per_slot": 16384, "parallel": 1},
    "workers": {"team_size": 3, "ctx_per_slot": 8192, "parallel": 2, "pool": []},
    "verifier": {"model": "Granite-4.1-3B", "ctx_per_slot": 8192, "parallel": 2},
    "research": {
        "max_search_queries": 4,
        "results_per_query": 5,
        "wikipedia_results": 2,
        "max_pages": 8,
        "passages_per_subquestion": 6,
        "passage_chars": 900,
        "fetch_workers": 3,
    },
    "speech": {},
}


def _merge(base: dict, over: dict) -> dict:
    out = copy.deepcopy(base)
    for k, v in (over or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _merge(out[k], v)
        else:
            out[k] = v
    return out


def load_config(path: Path | None = None) -> dict[str, Any]:
    path = path or (CONFIG / "swarm.yaml")
    data = {}
    if path.exists():
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return _merge(DEFAULTS, data)
