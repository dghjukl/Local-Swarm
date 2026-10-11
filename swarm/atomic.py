"""Small, crash-safe file-writing helpers used by durable state code."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path


def _fsync_directory(path: Path) -> None:
    if os.name == "nt":
        return
    try:
        fd = os.open(path, os.O_RDONLY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)
    except OSError:
        pass


def write_text_atomic(path: Path, text: str) -> None:
    """Write UTF-8 text by replacing the destination only after a full flush."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    tmp = Path(name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, path)
        _fsync_directory(path.parent)
    finally:
        try:
            tmp.unlink()
        except FileNotFoundError:
            pass


def write_json_atomic(path: Path, obj) -> None:
    write_text_atomic(Path(path), json.dumps(obj, indent=2, ensure_ascii=False) + "\n")
