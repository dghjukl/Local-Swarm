"""Child-process helpers.

On Windows every child we start is put in a Job Object that is closed when this
Python process exits, so llama-server / whisper-server never outlive the swarm
(even if the console window is closed or Python crashes).
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

IS_WIN = sys.platform == "win32"
_job = None


def _get_job():
    global _job
    if _job is not None or not IS_WIN:
        return _job
    try:
        import ctypes
        from ctypes import wintypes

        k32 = ctypes.WinDLL("kernel32", use_last_error=True)

        class IO_COUNTERS(ctypes.Structure):
            _fields_ = [(n, ctypes.c_ulonglong) for n in (
                "ReadOperationCount", "WriteOperationCount", "OtherOperationCount",
                "ReadTransferCount", "WriteTransferCount", "OtherTransferCount")]

        class BASIC(ctypes.Structure):
            _fields_ = [
                ("PerProcessUserTimeLimit", ctypes.c_int64),
                ("PerJobUserTimeLimit", ctypes.c_int64),
                ("LimitFlags", wintypes.DWORD),
                ("MinimumWorkingSetSize", ctypes.c_size_t),
                ("MaximumWorkingSetSize", ctypes.c_size_t),
                ("ActiveProcessLimit", wintypes.DWORD),
                ("Affinity", ctypes.c_size_t),
                ("PriorityClass", wintypes.DWORD),
                ("SchedulingClass", wintypes.DWORD),
            ]

        class EXTENDED(ctypes.Structure):
            _fields_ = [
                ("BasicLimitInformation", BASIC),
                ("IoInfo", IO_COUNTERS),
                ("ProcessMemoryLimit", ctypes.c_size_t),
                ("JobMemoryLimit", ctypes.c_size_t),
                ("PeakProcessMemoryUsed", ctypes.c_size_t),
                ("PeakJobMemoryUsed", ctypes.c_size_t),
            ]

        k32.CreateJobObjectW.restype = wintypes.HANDLE
        job = k32.CreateJobObjectW(None, None)
        info = EXTENDED()
        info.BasicLimitInformation.LimitFlags = 0x2000  # KILL_ON_JOB_CLOSE
        ok = k32.SetInformationJobObject(job, 9, ctypes.byref(info), ctypes.sizeof(info))
        if not ok:
            return None
        _job = (k32, job)
    except Exception:
        _job = None
    return _job


def start(cmd: list[str], log_path: Path, cwd: Path | None = None, env: dict | None = None) -> subprocess.Popen:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log = open(log_path, "w", encoding="utf-8", errors="replace")
    flags = 0
    if IS_WIN:
        flags = subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP
    proc = subprocess.Popen(
        cmd, stdout=log, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
        cwd=str(cwd) if cwd else None, env=env, creationflags=flags,
    )
    proc._swarm_log = log  # type: ignore[attr-defined]
    job = _get_job()
    if job:
        try:
            import ctypes
            k32, h = job
            PROCESS_ALL_ACCESS = 0x1F0FFF
            ph = k32.OpenProcess(PROCESS_ALL_ACCESS, False, proc.pid)
            k32.AssignProcessToJobObject(h, ph)
            k32.CloseHandle(ph)
        except Exception:
            pass
    return proc


def stop(proc: subprocess.Popen, timeout: float = 8.0) -> None:
    if proc.poll() is None:
        proc.terminate()
        try:
            proc.wait(timeout)
        except subprocess.TimeoutExpired:
            proc.kill()
            try:
                proc.wait(5)
            except subprocess.TimeoutExpired:
                pass
    log = getattr(proc, "_swarm_log", None)
    if log:
        try:
            log.close()
        except Exception:
            pass


def gpu_memory_mb() -> tuple[int, int] | None:
    """(used, total) MiB from nvidia-smi, or None if unavailable."""
    exe = "nvidia-smi"
    if IS_WIN and os.path.exists(r"C:\Windows\System32\nvidia-smi.exe"):
        exe = r"C:\Windows\System32\nvidia-smi.exe"
    try:
        out = subprocess.run(
            [exe, "--query-gpu=memory.used,memory.total", "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=5,
            creationflags=subprocess.CREATE_NO_WINDOW if IS_WIN else 0,
        ).stdout.strip().splitlines()[0]
        used, total = (int(x.strip()) for x in out.split(","))
        return used, total
    except Exception:
        return None


def system_ram_mb() -> tuple[int, int] | None:
    """(available, total) MiB of system RAM, or None if unknown."""
    try:
        if IS_WIN:
            import ctypes

            class MEMORYSTATUSEX(ctypes.Structure):
                _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong),
                            ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
                            ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
                            ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong),
                            ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]
            st = MEMORYSTATUSEX()
            st.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
            if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(st)):
                return None
            return int(st.ullAvailPhys // 2**20), int(st.ullTotalPhys // 2**20)
        info = {}
        with open("/proc/meminfo") as f:
            for line in f:
                k, v = line.split(":", 1)
                info[k] = int(v.split()[0]) // 1024
        return info.get("MemAvailable", 0), info.get("MemTotal", 0)
    except Exception:
        return None


def kill_stale(pids: list[int], exe_name: str = "llama-server") -> int:
    """Kill leftover model servers from an earlier run that did not shut down cleanly
    (e.g. the PC lost power mid-run is fine - nothing survives that - but a hard-killed
    console can leave them). Only processes whose image name matches are touched."""
    killed = 0
    for pid in pids:
        try:
            if IS_WIN:
                out = subprocess.run(["tasklist", "/FI", f"PID eq {int(pid)}", "/FO", "CSV", "/NH"],
                                     capture_output=True, text=True, timeout=10,
                                     creationflags=subprocess.CREATE_NO_WINDOW).stdout
                if exe_name.lower() not in out.lower():
                    continue
                subprocess.run(["taskkill", "/F", "/PID", str(int(pid))], capture_output=True, timeout=10,
                               creationflags=subprocess.CREATE_NO_WINDOW)
            else:
                with open(f"/proc/{int(pid)}/cmdline", "rb") as f:
                    if exe_name.encode() not in f.read():
                        continue
                os.kill(int(pid), 9)
            killed += 1
        except Exception:
            continue
    return killed
