from pathlib import Path
import subprocess


def test_notify_writes_completion_record_without_display():
    root = Path(__file__).resolve().parents[1]
    log_dir = root / "runtime" / "logs"
    before = set(log_dir.glob("DONE-TEST-*.txt")) if log_dir.exists() else set()
    result = subprocess.run(
        [
            "powershell",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(root / "scripts" / "notify.ps1"),
            "-Job",
            "TEST",
            "-Code",
            "0",
            "-Summary",
            "test completion",
            "-NoDisplay",
        ],
        cwd=root,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stderr
    after = set(log_dir.glob("DONE-TEST-*.txt"))
    created = after - before
    assert created, "notify.ps1 did not write a DONE record"
    assert "Exit code: 0" in next(iter(created)).read_text(encoding="utf-8-sig")
