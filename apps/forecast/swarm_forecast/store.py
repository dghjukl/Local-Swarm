"""Append-only JSONL records with fsync, tolerant of a torn last line (power loss), for resumable cycles."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path


class RecordLog:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.torn = 0

    def read(self) -> list[dict]:
        if not self.path.exists():
            return []
        out = []
        for line in self.path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                v = json.loads(line)
                if isinstance(v, dict):
                    out.append(v)
            except json.JSONDecodeError:
                self.torn += 1
        return out

    def append(self, rec: dict) -> None:
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False, separators=(",", ":")) + "\n")
            f.flush()
            os.fsync(f.fileno())

    def keyed(self, key: str = "market_id") -> dict[str, dict]:
        """Latest record per key."""
        return {str(r[key]): r for r in self.read() if key in r}


def write_json_atomic(path: str | Path, obj) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=1)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


def read_json(path: str | Path):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return None


def config_hash(obj) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True, default=str).encode()).hexdigest()[:16]
