"""A small SQLite-backed durable job queue."""

from __future__ import annotations

import argparse
import json
import sqlite3
import time
from pathlib import Path


class JobQueue:
    def __init__(self, db_path: Path | str = Path("runtime/jobs/jobs.db"), *, root=None,
                 max_attempts: int = 3, initial_backoff: float = 1.0, max_backoff: float = 60.0):
        if root is not None:
            db_path = Path(root) / "jobs.db"
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.max_attempts = max_attempts
        self.initial_backoff = initial_backoff
        self.max_backoff = max_backoff
        self._init()

    def _db(self):
        conn = sqlite3.connect(self.db_path, timeout=30, isolation_level=None)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=FULL")
        return conn

    def _init(self):
        with self._db() as db:
            db.execute("""CREATE TABLE IF NOT EXISTS jobs (
                id INTEGER PRIMARY KEY AUTOINCREMENT, kind TEXT NOT NULL, payload TEXT NOT NULL,
                priority INTEGER NOT NULL DEFAULT 0, run_after REAL NOT NULL DEFAULT 0,
                state TEXT NOT NULL, worker_id TEXT, lease_until REAL, attempts INTEGER NOT NULL DEFAULT 0,
                max_attempts INTEGER NOT NULL, result TEXT, error TEXT,
                created_at REAL NOT NULL, updated_at REAL NOT NULL)""")
            db.execute("CREATE INDEX IF NOT EXISTS jobs_ready ON jobs(state, run_after, priority, id)")

    @staticmethod
    def _row(row):
        if row is None:
            return None
        d = dict(row)
        for k in ("payload", "result"):
            if d.get(k) is not None:
                d[k] = json.loads(d[k])
        return d

    def enqueue(self, kind: str, payload: dict, priority: int = 0, run_after: float = 0) -> int:
        now = time.time()
        with self._db() as db:
            cur = db.execute("INSERT INTO jobs(kind,payload,priority,run_after,state,max_attempts,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?)",
                             (kind, json.dumps(payload), priority, run_after, "queued", self.max_attempts, now, now))
            return int(cur.lastrowid)

    def claim(self, worker_id: str, lease_s: float = 300):
        now = time.time()
        with self._db() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT id FROM jobs WHERE state='queued' AND run_after<=? ORDER BY priority DESC, id LIMIT 1", (now,)).fetchone()
            if row is None:
                db.commit()
                return None
            db.execute("UPDATE jobs SET state='running',worker_id=?,lease_until=?,attempts=attempts+1,updated_at=? WHERE id=? AND state='queued'",
                       (worker_id, now + lease_s, now, row["id"]))
            claimed = db.execute("SELECT * FROM jobs WHERE id=?", (row["id"],)).fetchone()
            db.commit()
            return self._row(claimed)

    def heartbeat(self, job_id: int, worker_id: str, lease_s: float = 300) -> bool:
        now = time.time()
        with self._db() as db:
            cur = db.execute("UPDATE jobs SET lease_until=?,updated_at=? WHERE id=? AND state='running' AND worker_id=?",
                             (now + lease_s, now, job_id, worker_id))
            return cur.rowcount == 1

    def complete(self, job_id: int, result: dict | None = None) -> bool:
        with self._db() as db:
            cur = db.execute("UPDATE jobs SET state='done',result=?,lease_until=NULL,worker_id=NULL,updated_at=? WHERE id=? AND state='running'",
                             (json.dumps(result) if result is not None else None, time.time(), job_id))
            return cur.rowcount == 1

    def fail(self, job_id: int, error: str, retry: bool = True) -> bool:
        now = time.time()
        with self._db() as db:
            row = db.execute("SELECT attempts,max_attempts FROM jobs WHERE id=?", (job_id,)).fetchone()
            if row is None:
                return False
            dead = not retry or row["attempts"] >= row["max_attempts"]
            delay = min(self.max_backoff, self.initial_backoff * (2 ** max(0, row["attempts"] - 1)))
            state, run_after = ("dead", now) if dead else ("queued", now + delay)
            cur = db.execute("UPDATE jobs SET state=?,run_after=?,error=?,lease_until=NULL,worker_id=NULL,updated_at=? WHERE id=? AND state='running'",
                             (state, run_after, error, now, job_id))
            return cur.rowcount == 1

    def reconcile_on_startup(self) -> int:
        now = time.time()
        with self._db() as db:
            cur = db.execute("UPDATE jobs SET state='queued',worker_id=NULL,lease_until=NULL,run_after=?,updated_at=?,error=? WHERE state='running' AND lease_until IS NOT NULL AND lease_until<?",
                             (now, now, "expired lease recovered", now))
            return cur.rowcount

    def stats(self) -> dict:
        with self._db() as db:
            rows = db.execute("SELECT state,COUNT(*) AS n FROM jobs GROUP BY state").fetchall()
            counts = {r["state"]: r["n"] for r in rows}
            return {"total": sum(counts.values()), "counts": counts, "counts_by_status": counts}

    def get(self, job_id: int):
        with self._db() as db:
            return self._row(db.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone())


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python -m swarm.jobs")
    ap.add_argument("command", choices=("enqueue", "list", "reconcile"))
    ap.add_argument("kind", nargs="?")
    ap.add_argument("payload", nargs="?", default="{}")
    args = ap.parse_args(argv)
    q = JobQueue()
    if args.command == "enqueue":
        print(q.enqueue(args.kind or "job", json.loads(args.payload)))
    elif args.command == "reconcile":
        print(q.reconcile_on_startup())
    else:
        print(json.dumps(q.stats(), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
