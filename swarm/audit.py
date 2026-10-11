"""SQLite hash-chain audit log ordered by sequence, never by wall-clock time."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path


class Audit:
    def __init__(self, path: Path | str = Path("runtime/audit.db")):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._db() as db:
            db.execute("""CREATE TABLE IF NOT EXISTS audit (
                seq INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT NOT NULL, kind TEXT NOT NULL,
                payload TEXT NOT NULL, prev_hash TEXT, record_hash TEXT NOT NULL)""")

    def _db(self):
        db = sqlite3.connect(self.path, timeout=30, isolation_level=None)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA journal_mode=WAL")
        db.execute("PRAGMA synchronous=FULL")
        return db

    @staticmethod
    def _canonical(seq, ts, kind, payload, prev_hash):
        return json.dumps({"seq": seq, "ts": ts, "kind": kind, "payload": payload,
                           "prev_hash": prev_hash}, sort_keys=True, separators=(",", ":"), ensure_ascii=False)

    def record(self, kind: str, payload: dict) -> int:
        ts = datetime.now(timezone.utc).isoformat()
        with self._db() as db:
            db.execute("BEGIN IMMEDIATE")
            prev = db.execute("SELECT record_hash FROM audit ORDER BY seq DESC LIMIT 1").fetchone()
            prev_hash = prev[0] if prev else None
            # SQLite allocates the sequence at INSERT; compute it from the current max while locked.
            seq = (db.execute("SELECT COALESCE(MAX(seq),0)+1 FROM audit").fetchone()[0])
            digest = hashlib.sha256(self._canonical(seq, ts, kind, payload, prev_hash).encode()).hexdigest()
            db.execute("INSERT INTO audit(seq,ts,kind,payload,prev_hash,record_hash) VALUES(?,?,?,?,?,?)",
                       (seq, ts, kind, json.dumps(payload, sort_keys=True, separators=(",", ":")), prev_hash, digest))
            db.commit()
            return int(seq)

    def verify(self) -> dict:
        with self._db() as db:
            rows = db.execute("SELECT * FROM audit ORDER BY seq").fetchall()
        prev = None
        expected = 1
        breach = None
        for row in rows:
            try:
                payload = json.loads(row["payload"])
                expected_hash = hashlib.sha256(self._canonical(row["seq"], row["ts"], row["kind"], payload, row["prev_hash"]).encode()).hexdigest()
                good = row["seq"] == expected and row["prev_hash"] == prev and row["record_hash"] == expected_hash
            except (ValueError, TypeError, json.JSONDecodeError):
                good = False
            if not good and breach is None:
                breach = row["seq"]
            prev = row["record_hash"]
            expected = row["seq"] + 1
        return {"intact": breach is None and len(rows) == expected - 1, "records": len(rows), "first_breach": breach}

    def query(self, kind: str | None = None, limit: int = 100) -> list[dict]:
        with self._db() as db:
            if kind is None:
                rows = db.execute("SELECT * FROM audit ORDER BY seq LIMIT ?", (limit,)).fetchall()
            else:
                rows = db.execute("SELECT * FROM audit WHERE kind=? ORDER BY seq LIMIT ?", (kind, limit)).fetchall()
        result = []
        for row in rows:
            d = dict(row)
            d["payload"] = json.loads(d["payload"])
            result.append(d)
        return result
