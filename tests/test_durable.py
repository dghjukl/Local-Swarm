import json
import sqlite3
import threading
import time

from swarm.audit import Audit
from swarm.atomic import write_text_atomic
from swarm.jobs import JobQueue
from swarm.workspace import Workspace


def test_workspace_round_trip_and_torn_records(tmp_path):
    ws = Workspace(tmp_path, "run-1")
    ws.append_event({"type": "start"})
    ws.save_state({"cycle": 2})
    ws.save_state({"cycle": 3})
    assert ws.load_state()["cycle"] == 3
    assert ws.resume_info()["seq"] == 2
    ws.append_record("notes", {"n": 1})
    (ws.path / "notes.jsonl").open("a", encoding="utf-8").write('{"torn":')
    assert ws.read_records("notes") == [{"n": 1}]
    assert ws.torn == 1
    ws.save_json("plan.json", {"x": [1, 2]})
    assert ws.load_json("plan.json") == {"x": [1, 2]}
    ws.put_page("https://example.test", "page text")
    assert ws.get_page("https://example.test") == "page text"
    ws.mark_done({"ok": True})
    assert ws.is_done()
    assert Workspace.list_runs(tmp_path)[0]["done"]


def test_workspace_state_falls_back_and_atomic_replace_preserves_old(tmp_path, monkeypatch):
    ws = Workspace(tmp_path, "run-2")
    ws.save_state({"cycle": 1})
    ws.save_state({"cycle": 2})
    (ws.path / "state.json").write_text("{", encoding="utf-8")
    assert ws.load_state()["cycle"] == 1

    original = ws.load_state()
    import swarm.atomic as atomic
    real_replace = atomic.os.replace
    def fail_replace(*args):
        raise OSError("simulated crash")
    monkeypatch.setattr(atomic.os, "replace", fail_replace)
    try:
        try:
            write_text_atomic(ws.path / "state.json", json.dumps({"cycle": 9}))
        except OSError:
            pass
    finally:
        monkeypatch.setattr(atomic.os, "replace", real_replace)
    assert ws.load_state() == original


def test_workspace_concurrent_writers(tmp_path):
    ws = Workspace(tmp_path, "run-3")
    def writer(n):
        for i in range(20):
            ws.append_event({"writer": n, "i": i})
    threads = [threading.Thread(target=writer, args=(n,)) for n in range(4)]
    for t in threads: t.start()
    for t in threads: t.join()
    lines = (ws.path / "events.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(lines) == 80 and all(json.loads(line)["writer"] in range(4) for line in lines)


def test_jobs_claim_is_exclusive_and_recovery(tmp_path):
    q = JobQueue(tmp_path / "jobs.db", max_attempts=2, initial_backoff=0.001, max_backoff=0.01)
    job = q.enqueue("work", {"x": 1}, priority=5)
    claimed = []
    lock = threading.Lock()
    def claim():
        got = q.claim(threading.current_thread().name, lease_s=60)
        if got:
            with lock: claimed.append(got)
    threads = [threading.Thread(target=claim, name=f"w{i}") for i in range(8)]
    for t in threads: t.start()
    for t in threads: t.join()
    assert len(claimed) == 1 and claimed[0]["id"] == job
    assert q.heartbeat(job, claimed[0]["worker_id"], lease_s=60)
    assert q.complete(job, {"ok": True})
    assert q.stats()["counts"]["done"] == 1

    stale = q.enqueue("stale", {})
    got = q.claim("old", lease_s=0.001)
    assert got and got["id"] == stale
    time.sleep(0.01)
    assert q.reconcile_on_startup() == 1
    assert q.get(stale)["state"] == "queued"


def test_jobs_retry_backoff_then_dead(tmp_path):
    q = JobQueue(tmp_path / "jobs.db", max_attempts=2, initial_backoff=0.001, max_backoff=0.01)
    job = q.enqueue("retry", {})
    first = q.claim("w")
    assert q.fail(job, "bad")
    assert q.get(job)["state"] == "queued"
    time.sleep(0.01)
    second = q.claim("w")
    assert second and second["attempts"] == 2
    assert q.fail(job, "still bad")
    assert q.get(job)["state"] == "dead"


def test_audit_chain_detects_tamper_and_deletion(tmp_path):
    audit = Audit(tmp_path / "audit.db")
    for i in range(200):
        audit.record("tool", {"i": i})
    assert audit.verify() == {"intact": True, "records": 200, "first_breach": None}
    with sqlite3.connect(tmp_path / "audit.db") as db:
        db.execute("UPDATE audit SET payload=? WHERE seq=?", ('{"i":999}', 40))
        db.commit()
    result = audit.verify()
    assert not result["intact"] and result["first_breach"] == 40
    with sqlite3.connect(tmp_path / "audit.db") as db:
        db.execute("DELETE FROM audit WHERE seq=?", (40,))
        db.commit()
    result = audit.verify()
    assert not result["intact"] and result["first_breach"] == 41
    assert audit.query("tool", 2)[0]["seq"] == 1
