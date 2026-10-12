"""Reproducibility stamp for each forecast record."""

from __future__ import annotations
import hashlib, json, subprocess, time
from pathlib import Path

def _sha(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""): h.update(block)
    return h.hexdigest()

def swarm_stamp(swarm_root, config_name="default", config_path=None, model_paths=(), prompt_path=None, app_version="0.1.0"):
    root = Path(swarm_root)
    try: commit = subprocess.check_output(["git", "-C", str(root), "rev-parse", "HEAD"], text=True).strip()
    except (OSError, subprocess.CalledProcessError): commit = None
    try: tag = subprocess.check_output(["git", "-C", str(root), "describe", "--tags", "--exact-match", "HEAD"], text=True, stderr=subprocess.DEVNULL).strip()
    except (OSError, subprocess.CalledProcessError): tag = None
    def files(paths):
        return [{"path": str(p), "size": Path(p).stat().st_size, "sha256": _sha(p)} for p in paths if Path(p).exists()]
    config = Path(config_path) if config_path else None
    return {"swarm_commit": commit, "swarm_tag": tag, "swarm_config": config_name,
            "config_sha256": _sha(config) if config and config.exists() else None,
            "model_files": files(model_paths), "prompt": files([prompt_path] if prompt_path else []),
            "app_version": app_version, "timestamp": time.time()}
