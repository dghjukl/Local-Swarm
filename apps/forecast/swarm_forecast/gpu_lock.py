"""Small cross-project GPU lease using atomic exclusive file creation."""

from __future__ import annotations
import json, os, time
from pathlib import Path

DEFAULT_LOCK = Path(r"C:\Users\Chris\Documents\GitHub\.gpu_lock\lock.json")

def _read(path):
    try: return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError): return None

def _stale(data, stale_after):
    if not data: return True
    if time.time() - float(data.get("created_at", 0)) > stale_after: return True
    pid = int(data.get("pid", 0))
    if pid == os.getpid(): return False
    try:
        os.kill(pid, 0)
    except (OSError, ProcessLookupError): return True
    return False

def acquire(owner, purpose, timeout=0, path=DEFAULT_LOCK, stale_after=21600):
    path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    deadline = time.time() + timeout
    while True:
        payload = {"owner": owner, "purpose": purpose, "pid": os.getpid(), "created_at": time.time()}
        try:
            fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            with os.fdopen(fd, "w", encoding="utf-8") as f: json.dump(payload, f)
            return payload
        except FileExistsError:
            current = _read(path)
            if _stale(current, stale_after):
                try: path.unlink()
                except FileNotFoundError: pass
                continue
            if time.time() >= deadline: return None
            time.sleep(min(0.25, max(0, deadline - time.time())))

def release(owner, path=DEFAULT_LOCK):
    path = Path(path); current = _read(path)
    if not current or current.get("owner") != owner: return False
    try: path.unlink()
    except FileNotFoundError: return False
    return True

def status(path=DEFAULT_LOCK):
    current = _read(Path(path))
    return None if _stale(current, 21600) else current
