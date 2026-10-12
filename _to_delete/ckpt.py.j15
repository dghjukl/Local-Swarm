"""Per-question checkpointing for the manager loop (opt-in: cfg["workspace"] = {"root": ...}).

A question run owns one Workspace (swarm/workspace.py). The run state is saved at the top of
every manager turn and when an attempt finishes; started again with the same run tag, the same
question picks up where it stopped. Context variables keep concurrent questions apart.
"""
from __future__ import annotations

import contextvars
import hashlib
import time
from pathlib import Path

from swarm.audit import Audit
from swarm.workspace import Workspace

_current: contextvars.ContextVar = contextvars.ContextVar("swarm_ckpt", default=None)
_tag: contextvars.ContextVar = contextvars.ContextVar("swarm_ckpt_tag", default="")
_BOOT = time.strftime("%Y%m%d-%H%M%S")


def set_tag(tag: str) -> None:
    """Names the run (e.g. an eval's folder plus the config) so a restart finds its workspaces."""
    _tag.set(tag)


class Ckpt:
    def __init__(self, ws: Workspace, audit: Audit | None = None):
        self.ws, self.audit = ws, audit

    def save(self, key: str, obj) -> None:
        self.ws.save_json(f"{key}.json", obj)

    def load(self, key: str):
        return self.ws.load_json(f"{key}.json")

    def tool_call(self, rec: dict) -> None:
        self.ws.append_record("tool_calls", rec)
        if self.audit:
            self.audit.record("tool_call", {"run": self.ws.run_id, "tool": rec.get("tool"),
                                            "ok": rec.get("ok"), "args": rec.get("args")})

    def event(self, kind: str, **kw) -> None:
        self.ws.append_event({"kind": kind, **kw})
        if self.audit:
            self.audit.record(kind, {"run": self.ws.run_id, **kw})


def open_for(cfg: dict, question: str) -> Ckpt | None:
    _current.set(None)
    wc = cfg.get("workspace")
    if not wc:
        return None
    root = Path(wc.get("root", "runtime/workspaces"))
    tag = wc.get("run") or _tag.get() or _BOOT
    rid = f"{tag}-{hashlib.sha1(question.encode('utf-8')).hexdigest()[:10]}"
    ws = Workspace(root, rid)
    audit = Audit(Path(wc.get("audit", root / "audit.db"))) if wc.get("audit_log", True) else None
    ck = Ckpt(ws, audit)
    _current.set(ck)
    return ck


def current() -> Ckpt | None:
    return _current.get()


def clear() -> None:
    _current.set(None)
