"""SQLite/FTS5 memory store. Stored text is data; it is never executed."""

from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
import time
from datetime import date, datetime, timezone
from pathlib import Path


class MemoryStore:
    def __init__(self, path: Path | str):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.db = None
        for attempt in range(40):
            try:
                self.db = sqlite3.connect(self.path, timeout=60, isolation_level=None, check_same_thread=False)
                self.db.row_factory = sqlite3.Row
                self.db.execute("PRAGMA busy_timeout=60000")
                self.db.execute("PRAGMA journal_mode=WAL")
                self.db.execute("PRAGMA synchronous=FULL")
                break
            except sqlite3.OperationalError:
                if self.db is not None:
                    self.db.close()
                if attempt == 39:
                    raise
                time.sleep(0.05)
        try:
            self.db.execute("CREATE VIRTUAL TABLE IF NOT EXISTS memory_fts USING fts5(kind UNINDEXED, ref_id UNINDEXED, entity, body)")
        except sqlite3.OperationalError as exc:
            self.db.close()
            raise RuntimeError("SQLite FTS5 is required for MemoryStore") from exc
        self._schema()

    def _schema(self):
        self.db.executescript("""
        CREATE TABLE IF NOT EXISTS facts(
          id INTEGER PRIMARY KEY AUTOINCREMENT, entity TEXT NOT NULL, attribute TEXT NOT NULL,
          value_text TEXT NOT NULL, as_of TEXT NOT NULL, created_at TEXT NOT NULL,
          confidence REAL, status TEXT NOT NULL DEFAULT 'unchecked', refresh_after TEXT,
          run_id TEXT, origin TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS fact_sources(
          id INTEGER PRIMARY KEY AUTOINCREMENT, fact_id INTEGER NOT NULL REFERENCES facts(id) ON DELETE CASCADE,
          ref TEXT NOT NULL, quote TEXT, content_hash TEXT, fetched_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS conflicts(
          id INTEGER PRIMARY KEY AUTOINCREMENT, entity TEXT NOT NULL, attribute TEXT NOT NULL,
          fact_id INTEGER NOT NULL REFERENCES facts(id) ON DELETE CASCADE, other_fact_id INTEGER NOT NULL REFERENCES facts(id) ON DELETE CASCADE,
          UNIQUE(fact_id, other_fact_id));
        CREATE TABLE IF NOT EXISTS playbooks(
          id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, body TEXT NOT NULL, version TEXT,
          domain TEXT, last_reviewed TEXT, measured_effect TEXT, origin TEXT NOT NULL DEFAULT 'human');
        CREATE TABLE IF NOT EXISTS track_record(
          id INTEGER PRIMARY KEY AUTOINCREMENT, category TEXT NOT NULL, model_config_id TEXT NOT NULL,
          forecast_id TEXT NOT NULL, probability REAL NOT NULL, outcome INTEGER NOT NULL, scored_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS agenda(
          id INTEGER PRIMARY KEY AUTOINCREMENT, kind TEXT NOT NULL, text TEXT NOT NULL, due_at TEXT NOT NULL,
          status TEXT NOT NULL DEFAULT 'open', created_at TEXT NOT NULL, run_id TEXT);
        CREATE TABLE IF NOT EXISTS memory_events(
          seq INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT NOT NULL, kind TEXT NOT NULL, payload TEXT NOT NULL,
          prev_hash TEXT, record_hash TEXT NOT NULL);
        """)

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()

    @staticmethod
    def _error(message: str, **extra):
        return {"ok": False, "error": message, **extra}

    @staticmethod
    def _ok(**data):
        return {"ok": True, **data}

    def _event(self, kind: str, payload: dict):
        prev = self.db.execute("SELECT record_hash FROM memory_events ORDER BY seq DESC LIMIT 1").fetchone()
        prev_hash = prev[0] if prev else None
        seq = self.db.execute("SELECT COALESCE(MAX(seq),0)+1 FROM memory_events").fetchone()[0]
        ts = self._now()
        canonical = json.dumps({"seq": seq, "ts": ts, "kind": kind, "payload": payload, "prev_hash": prev_hash},
                               sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        digest = hashlib.sha256(canonical.encode()).hexdigest()
        self.db.execute("INSERT INTO memory_events(seq,ts,kind,payload,prev_hash,record_hash) VALUES(?,?,?,?,?,?)",
                        (seq, ts, kind, json.dumps(payload, sort_keys=True, separators=(",", ":")), prev_hash, digest))

    def add_fact(self, entity, attribute, value, as_of, sources=None, origin="model", run_id=None,
                 confidence=None, refresh_after=None):
        try:
            if not entity or not attribute or value is None:
                return self._error("entity, attribute, and value are required")
            if not as_of:
                return self._error("as_of is required")
            sources = sources or []
            if not sources:
                return self._error("at least one source is required")
            if origin == "web" and any(not s.get("quote") for s in sources):
                return self._error("web facts require a quote for every source")
            if confidence is not None and not 0 <= float(confidence) <= 1:
                return self._error("confidence must be between 0 and 1")
            self.db.execute("BEGIN IMMEDIATE")
            now = self._now()
            cur = self.db.execute("INSERT INTO facts(entity,attribute,value_text,as_of,created_at,confidence,status,refresh_after,run_id,origin) VALUES(?,?,?,?,?,?,?,?,?,?)",
                                  (str(entity), str(attribute), str(value), str(as_of), now, confidence, "unchecked", refresh_after, run_id, str(origin)))
            fact_id = int(cur.lastrowid)
            for source in sources:
                ref, quote = str(source.get("ref", "")), source.get("quote")
                if not ref:
                    raise ValueError("source ref is required")
                self.db.execute("INSERT INTO fact_sources(fact_id,ref,quote,content_hash,fetched_at) VALUES(?,?,?,?,?)",
                                (fact_id, ref, quote, source.get("content_hash") or hashlib.sha256(str(quote or "").encode()).hexdigest(), now))
            old = self.db.execute("SELECT id FROM facts WHERE entity=? AND attribute=? AND value_text<>? AND id<>? AND status<>'expired'",
                                  (str(entity), str(attribute), str(value), fact_id)).fetchall()
            for row in old:
                self.db.execute("INSERT OR IGNORE INTO conflicts(entity,attribute,fact_id,other_fact_id) VALUES(?,?,?,?)", (entity, attribute, fact_id, row[0]))
                self.db.execute("INSERT OR IGNORE INTO conflicts(entity,attribute,fact_id,other_fact_id) VALUES(?,?,?,?)", (entity, attribute, row[0], fact_id))
            body = f"{entity} {attribute} {value}"
            self.db.execute("INSERT INTO memory_fts(kind,ref_id,entity,body) VALUES('fact',?,?,?)", (str(fact_id), str(entity), body))
            self._event("fact.added", {"fact_id": fact_id, "entity": entity, "attribute": attribute, "origin": origin})
            self.db.commit()
            return self._ok(fact_id=fact_id, conflict_ids=[r[0] for r in old])
        except (ValueError, TypeError, sqlite3.Error) as exc:
            self.db.rollback()
            return self._error(str(exc))

    def _fact(self, fact_id):
        row = self.db.execute("SELECT * FROM facts WHERE id=?", (fact_id,)).fetchone()
        if not row:
            return None
        d = dict(row)
        d["sources"] = [dict(x) for x in self.db.execute("SELECT ref,quote,content_hash,fetched_at FROM fact_sources WHERE fact_id=?", (fact_id,))]
        d["needs_recheck"] = d["status"] == "unchecked" or bool(d["refresh_after"] and d["refresh_after"] < date.today().isoformat())
        return d

    def search(self, query, limit=20, kinds=None, include_expired=False):
        try:
            if not query:
                return self._ok(results=[], torn=0)
            kinds = set(kinds or ["fact", "playbook", "agenda"])
            terms = [x for x in str(query).replace('"', " ").split() if x]
            match = " AND ".join(f'"{x}"' for x in terms)
            rows = self.db.execute("SELECT kind,ref_id,entity,body FROM memory_fts WHERE memory_fts MATCH ? LIMIT ?", (match, max(1, int(limit) * 3))).fetchall()
            out = []
            for row in rows:
                if row["kind"] not in kinds:
                    continue
                if row["kind"] == "fact":
                    item = self._fact(int(row["ref_id"]))
                    if not item or (item["status"] == "expired" and not include_expired):
                        continue
                elif row["kind"] == "playbook":
                    item = dict(self.db.execute("SELECT * FROM playbooks WHERE id=?", (row["ref_id"],)).fetchone() or {})
                else:
                    item = dict(self.db.execute("SELECT * FROM agenda WHERE id=?", (row["ref_id"],)).fetchone() or {})
                if item:
                    item["kind"] = row["kind"]
                    out.append(item)
                if len(out) >= int(limit):
                    break
            return self._ok(results=out, torn=0)
        except (TypeError, ValueError, sqlite3.Error) as exc:
            return self._error(str(exc), results=[])

    def mark(self, fact_id, status, note=""):
        try:
            if status not in {"verified", "disputed"}:
                return self._error("status must be verified or disputed")
            self.db.execute("BEGIN IMMEDIATE")
            cur = self.db.execute("UPDATE facts SET status=? WHERE id=?", (status, fact_id))
            if not cur.rowcount:
                self.db.rollback(); return self._error("fact not found")
            self._event("fact.marked", {"fact_id": fact_id, "status": status, "note": str(note)})
            self.db.commit(); return self._ok(fact_id=fact_id, status=status)
        except sqlite3.Error as exc:
            self.db.rollback(); return self._error(str(exc))

    def expire_due(self, now=None):
        try:
            now = now or date.today().isoformat()
            self.db.execute("BEGIN IMMEDIATE")
            ids = [r[0] for r in self.db.execute("SELECT id FROM facts WHERE refresh_after IS NOT NULL AND refresh_after<? AND status<>'expired'", (now,))]
            self.db.execute("UPDATE facts SET status='expired' WHERE refresh_after IS NOT NULL AND refresh_after<? AND status<>'expired'", (now,))
            for fact_id in ids: self._event("fact.expired", {"fact_id": fact_id})
            self.db.commit(); return self._ok(expired=ids)
        except sqlite3.Error as exc:
            self.db.rollback(); return self._error(str(exc))

    def add_playbook(self, name, body, version=None, domain=None, last_reviewed=None, measured_effect=None,
                     origin="human", human_approved=False):
        try:
            if origin in {"web", "model"} and not human_approved:
                return self._error("web/model playbooks require human approval")
            if not name or not body:
                return self._error("name and body are required")
            self.db.execute("BEGIN IMMEDIATE")
            cur = self.db.execute("INSERT INTO playbooks(name,body,version,domain,last_reviewed,measured_effect,origin) VALUES(?,?,?,?,?,?,?)",
                                  (name, body, version, domain, last_reviewed, json.dumps(measured_effect) if measured_effect is not None else None, origin))
            ident = int(cur.lastrowid)
            self.db.execute("INSERT INTO memory_fts(kind,ref_id,entity,body) VALUES('playbook',?,?,?)", (str(ident), name, f"{name} {body}"))
            self._event("playbook.added", {"playbook_id": ident, "origin": origin}); self.db.commit()
            return self._ok(playbook_id=ident)
        except (TypeError, sqlite3.Error) as exc:
            self.db.rollback(); return self._error(str(exc))

    def list_playbooks(self, domain=None):
        rows = self.db.execute("SELECT * FROM playbooks" + (" WHERE domain=?" if domain else "") + " ORDER BY id", ((domain,) if domain else ())).fetchall()
        return self._ok(playbooks=[dict(r) for r in rows])

    def record_forecast_outcome(self, category, model_config_id, forecast_id, probability, outcome, scored_at=None):
        try:
            p = float(probability)
            if not 0 <= p <= 1 or outcome not in (0, 1, False, True): return self._error("invalid probability or outcome")
            self.db.execute("INSERT INTO track_record(category,model_config_id,forecast_id,probability,outcome,scored_at) VALUES(?,?,?,?,?,?)",
                            (category, model_config_id, forecast_id, p, int(bool(outcome)), scored_at or self._now()))
            return self._ok(forecast_id=forecast_id)
        except (ValueError, TypeError, sqlite3.Error) as exc: return self._error(str(exc))

    def calibration(self, category=None):
        rows = self.db.execute("SELECT * FROM track_record" + (" WHERE category=?" if category else ""), ((category,) if category else ())).fetchall()
        bins = {}
        brier = 0.0
        for r in rows:
            p, o = r["probability"], r["outcome"]; brier += (p - o) ** 2
            key = min(9, int(p * 10)); bins.setdefault(key, []).append((p, o))
        return self._ok(count=len(rows), brier=(brier / len(rows) if rows else None), bins=[{"bin": k / 10, "count": len(v), "mean_probability": sum(x[0] for x in v) / len(v), "hit_rate": sum(x[1] for x in v) / len(v)} for k, v in sorted(bins.items())])

    def add_agenda(self, kind, text, due_at, run_id=None):
        try:
            if kind not in {"open_loop", "revisit", "task"}: return self._error("invalid agenda kind")
            cur = self.db.execute("INSERT INTO agenda(kind,text,due_at,status,created_at,run_id) VALUES(?,?,?,?,?,?)", (kind, text, due_at, "open", self._now(), run_id))
            ident = int(cur.lastrowid); self.db.execute("INSERT INTO memory_fts(kind,ref_id,entity,body) VALUES('agenda',?,?,?)", (str(ident), kind, text)); self._event("agenda.added", {"agenda_id": ident}); return self._ok(agenda_id=ident)
        except sqlite3.Error as exc: return self._error(str(exc))

    def due_agenda(self, now=None):
        rows = self.db.execute("SELECT * FROM agenda WHERE status='open' AND due_at<=? ORDER BY due_at", (now or self._now(),)).fetchall()
        return self._ok(agenda=[dict(r) for r in rows])

    def close_agenda(self, agenda_id):
        cur = self.db.execute("UPDATE agenda SET status='closed' WHERE id=? AND status='open'", (agenda_id,))
        return self._ok(agenda_id=agenda_id, closed=bool(cur.rowcount))

    def consolidate(self):
        changed = []
        groups = self.db.execute("SELECT entity,attribute,value_text,COUNT(*) n FROM facts GROUP BY entity,attribute,value_text HAVING n>1").fetchall()
        for g in groups:
            facts = self.db.execute("SELECT id FROM facts WHERE entity=? AND attribute=? AND value_text=? ORDER BY id", (g[0], g[1], g[2])).fetchall()
            keep = facts[0][0]
            keep_src = {(r[0], r[1]) for r in self.db.execute("SELECT ref,quote FROM fact_sources WHERE fact_id=?", (keep,))}
            for row in facts[1:]:
                other = row[0]; srcs = self.db.execute("SELECT ref,quote,content_hash,fetched_at FROM fact_sources WHERE fact_id=?", (other,)).fetchall()
                for src in srcs:
                    if (src[0], src[1]) not in keep_src:
                        self.db.execute("INSERT INTO fact_sources(fact_id,ref,quote,content_hash,fetched_at) VALUES(?,?,?,?,?)", (keep, *src)); keep_src.add((src[0], src[1]))
                self.db.execute("DELETE FROM memory_fts WHERE kind='fact' AND ref_id=?", (str(other),)); self.db.execute("DELETE FROM facts WHERE id=?", (other,)); changed.append(other)
            self._event("facts.consolidated", {"kept": keep, "removed": changed})
        return self._ok(removed=changed)

    def export_jsonl(self, path):
        path = Path(path)
        with path.open("w", encoding="utf-8") as f:
            for kind, rows in (("fact", self.db.execute("SELECT * FROM facts")), ("fact_source", self.db.execute("SELECT * FROM fact_sources")), ("playbook", self.db.execute("SELECT * FROM playbooks")), ("track_record", self.db.execute("SELECT * FROM track_record")), ("agenda", self.db.execute("SELECT * FROM agenda"))):
                for row in rows: f.write(json.dumps({"kind": kind, "data": dict(row)}, ensure_ascii=False) + "\n")
        return self._ok(path=str(path))

    def import_jsonl(self, path):
        try:
            items = [json.loads(line) for line in Path(path).open(encoding="utf-8") if line.strip()]
            sources = {}
            for item in items:
                if item["kind"] == "fact_source":
                    sources.setdefault(item["data"]["fact_id"], []).append({"ref": item["data"]["ref"], "quote": item["data"].get("quote"), "content_hash": item["data"].get("content_hash")})
            for item in items:
                kind, data = item["kind"], dict(item["data"])
                if kind == "fact":
                    self.add_fact(data["entity"], data["attribute"], data["value_text"], data["as_of"], sources.get(data["id"], []), data["origin"], data.get("run_id"), data.get("confidence"), data.get("refresh_after"))
                elif kind == "playbook": self.add_playbook(data["name"], data["body"], data.get("version"), data.get("domain"), data.get("last_reviewed"), json.loads(data["measured_effect"]) if data.get("measured_effect") else None, data.get("origin", "human"), True)
                elif kind == "track_record":
                    self.record_forecast_outcome(data["category"], data["model_config_id"], data["forecast_id"], data["probability"], data["outcome"], data.get("scored_at"))
                elif kind == "agenda":
                    self.add_agenda(data["kind"], data["text"], data["due_at"], data.get("run_id"))
            return self._ok()
        except (OSError, KeyError, ValueError, json.JSONDecodeError) as exc: return self._error(str(exc))

    def verify_chain(self):
        rows = self.db.execute("SELECT * FROM memory_events ORDER BY seq").fetchall(); prev = None; expected = 1; breach = None
        for row in rows:
            canonical = json.dumps({"seq": row["seq"], "ts": row["ts"], "kind": row["kind"], "payload": json.loads(row["payload"]), "prev_hash": row["prev_hash"]}, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
            good = row["seq"] == expected and row["prev_hash"] == prev and hashlib.sha256(canonical.encode()).hexdigest() == row["record_hash"]
            if not good and breach is None: breach = row["seq"]
            prev, expected = row["record_hash"], row["seq"] + 1
        return self._ok(intact=breach is None, records=len(rows), first_breach=breach)

    def close(self):
        self.db.close()


def main(argv=None):
    ap = argparse.ArgumentParser(prog="python -m swarm.memory")
    ap.add_argument("command", choices=("show", "search", "due", "verify")); ap.add_argument("path"); ap.add_argument("query", nargs="?")
    a = ap.parse_args(argv); store = MemoryStore(a.path)
    try:
        if a.command == "show": result = {"ok": True, "facts": store.db.execute("SELECT COUNT(*) FROM facts").fetchone()[0]}
        elif a.command == "search": result = store.search(a.query or "")
        elif a.command == "due": result = store.due_agenda()
        else: result = store.verify_chain()
        print(json.dumps(result, indent=2)); return 0
    finally: store.close()


if __name__ == "__main__":
    raise SystemExit(main())
