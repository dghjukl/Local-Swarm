import json
import subprocess
import time
from pathlib import Path
from swarm_forecast.adapter import forecast
from swarm_forecast.gpu_lock import acquire, release, status
from swarm_forecast.versioning import assert_pinned_commit, swarm_stamp

def test_blind_adapter_rejects_market_fields():
    try: forecast({"question": "q", "prices": [0.5]}, "blind", {})
    except ValueError: pass
    else: assert False

def test_gpu_lock_owner_and_release(tmp_path):
    path = tmp_path / "lock.json"
    first = acquire("one", "test", path=path)
    assert first and status(path)["owner"] == "one"
    assert acquire("two", "test", path=path) is None
    assert not release("two", path)
    assert release("one", path) and status(path) is None

def test_gpu_lock_recovers_stale_lease(tmp_path):
    path = tmp_path / "stale.json"
    path.write_text(json.dumps({"owner": "dead", "pid": 99999999, "created_at": time.time() - 100}), encoding="utf-8")
    assert acquire("new", "test", path=path, stale_after=10)["owner"] == "new"
    assert release("new", path)

def test_versioning_records_git_commit(tmp_path):
    import subprocess
    subprocess.run(["git", "init", str(tmp_path)], check=True, capture_output=True)
    (tmp_path / "x.txt").write_text("x", encoding="utf-8")
    subprocess.run(["git", "-C", str(tmp_path), "add", "x.txt"], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(tmp_path), "-c", "user.email=test@example.com", "-c", "user.name=test", "commit", "-m", "init"], check=True, capture_output=True)
    stamp = swarm_stamp(tmp_path, config_path=tmp_path / "x.txt")
    assert stamp["swarm_commit"] and stamp["config_sha256"]

def test_versioning_rejects_wrong_pinned_commit(tmp_path):
    import pytest
    subprocess.run(["git", "init", str(tmp_path)], check=True, capture_output=True)
    (tmp_path / "x.txt").write_text("x", encoding="utf-8")
    subprocess.run(["git", "-C", str(tmp_path), "add", "x.txt"], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(tmp_path), "-c", "user.email=test@example.com", "-c", "user.name=test", "commit", "-m", "init"], check=True, capture_output=True)
    with pytest.raises(RuntimeError, match="pinned swarm mismatch"):
        assert_pinned_commit(tmp_path, "wrong")
