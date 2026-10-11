"""Thread-safe, append-oriented persistence for one resumable run."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import threading
from datetime import datetime, timezone
from pathlib import Path

from .atomic import write_json_atomic, write_text_atomic


class Workspace:
    def __init__(self, root: Path, run_id: str):
        self.root = Path(root)
        self.run_id = run_id
        self.path = self.root / run_id
        self.path.mkdir(parents=True, exist_ok=True)
        (self.path / "pages").mkdir(exist_ok=True)
        self._lock = threading.RLock()
        self.torn = 0
        state = self._read_state_file("state.json") or self._read_state_file("state.prev.json") or {}
        self._seq = int(state.get("seq", 0))

    def _read_state_file(self, name: str) -> dict | None:
        try:
            value = json.loads((self.path / name).read_text(encoding="utf-8"))
            return value if isinstance(value, dict) else None
        except (FileNotFoundError, OSError, json.JSONDecodeError):
            return None

    def append_event(self, ev: dict) -> None:
        with self._lock:
            with (self.path / "events.jsonl").open("a", encoding="utf-8") as f:
                f.write(json.dumps(ev, ensure_ascii=False, separators=(",", ":")) + "\n")
                f.flush()
                os.fsync(f.fileno())

    def save_state(self, state: dict) -> dict:
        with self._lock:
            current = self._read_state_file("state.json")
            self._seq = max(self._seq, int((current or {}).get("seq", 0))) + 1
            value = dict(state)
            value.update(seq=self._seq, saved_at=datetime.now(timezone.utc).isoformat())
            if current is not None:
                write_json_atomic(self.path / "state.prev.json", current)
            write_json_atomic(self.path / "state.json", value)
            return value

    def load_state(self) -> dict | None:
        with self._lock:
            return self._read_state_file("state.json") or self._read_state_file("state.prev.json")

    def save_json(self, name: str, obj) -> None:
        with self._lock:
            write_json_atomic(self.path / name, obj)

    def load_json(self, name: str):
        with self._lock:
            try:
                return json.loads((self.path / name).read_text(encoding="utf-8"))
            except FileNotFoundError:
                return None

    def append_record(self, kind: str, rec: dict) -> None:
        if kind not in {"tool_calls", "passages", "notes"}:
            raise ValueError(f"unknown record kind: {kind}")
        with self._lock:
            with (self.path / f"{kind}.jsonl").open("a", encoding="utf-8") as f:
                f.write(json.dumps(rec, ensure_ascii=False, separators=(",", ":")) + "\n")
                f.flush()
                os.fsync(f.fileno())

    def read_records(self, kind: str) -> list[dict]:
        if kind not in {"tool_calls", "passages", "notes"}:
            raise ValueError(f"unknown record kind: {kind}")
        with self._lock:
            try:
                lines = (self.path / f"{kind}.jsonl").read_text(encoding="utf-8").splitlines()
            except FileNotFoundError:
                return []
            result = []
            for line in lines:
                if not line.strip():
                    continue
                try:
                    value = json.loads(line)
                    if isinstance(value, dict):
                        result.append(value)
                except json.JSONDecodeError:
                    self.torn += 1
            return result

    def put_page(self, url: str, text: str) -> Path:
        name = hashlib.sha256(url.encode("utf-8")).hexdigest() + ".txt"
        path = self.path / "pages" / name
        with self._lock:
            write_text_atomic(path, text)
        return path

    def get_page(self, url: str) -> str | None:
        name = hashlib.sha256(url.encode("utf-8")).hexdigest() + ".txt"
        try:
            return (self.path / "pages" / name).read_text(encoding="utf-8")
        except FileNotFoundError:
            return None

    def mark_done(self, result: dict) -> None:
        with self._lock:
            write_json_atomic(self.path / "done.json", result)

    def is_done(self) -> bool:
        return (self.path / "done.json").is_file()

    def resume_info(self) -> dict:
        state = self.load_state() or {}
        return {"run_id": self.run_id, "seq": state.get("seq", 0),
                "cycle": state.get("cycle"), "done": self.is_done(), "torn": self.torn}

    @staticmethod
    def list_runs(root: Path) -> list[dict]:
        root = Path(root)
        if not root.exists():
            return []
        dirs = [p for p in root.iterdir() if p.is_dir()]
        dirs.sort(key=lambda p: (p.stat().st_mtime, p.name), reverse=True)
        result = []
        for path in dirs:
            state = None
            for name in ("state.json", "state.prev.json"):
                try:
                    state = json.loads((path / name).read_text(encoding="utf-8"))
                    break
                except (FileNotFoundError, OSError, json.JSONDecodeError):
                    pass
            result.append({"run_id": path.name, "state": state,
                           "done": (path / "done.json").is_file()})
        return result
