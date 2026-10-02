"""Speech in and out, all local.

STT: whisper.cpp's whisper-server (GPU), started on first use and kept running.
TTS: Piper, run once per reply.
"""
from __future__ import annotations

import asyncio
import re
import subprocess
import tempfile
import time
from pathlib import Path

import httpx

from swarm import procs
from swarm.paths import LOGS, repo_path
from swarm.pool import ModelPool


class SpeechError(RuntimeError):
    pass


class Speech:
    def __init__(self, cfg: dict, pool: ModelPool):
        s = cfg.get("speech", {})
        self.pool = pool
        self.whisper_exe = repo_path(s.get("whisper_server", "Bin/Whisper-CUDA/Release/whisper-server.exe"))
        self.whisper_model = repo_path(s.get("whisper_model", "Bin/Whisper/ggml-large-v3-turbo.bin"))
        self.whisper_port = int(s.get("whisper_port", 8180))
        self.whisper_vram = int(s.get("whisper_vram_mb", 1800))
        self.piper = repo_path(s.get("piper", "Bin/Piper/piper.exe"))
        self.voice = repo_path(s.get("piper_voice", "Bin/Piper/en_US-amy-medium.onnx"))
        self._whisper = None
        self._lock = asyncio.Lock()

    def available(self) -> dict:
        return {
            "stt": self.whisper_exe.exists() and self.whisper_model.exists(),
            "tts": self.piper.exists() and self.voice.exists(),
        }

    # ------------------------------------------------------------ STT
    async def _ensure_whisper(self) -> str:
        base = f"http://127.0.0.1:{self.whisper_port}"
        async with self._lock:
            if self._whisper and self._whisper.poll() is None:
                return base
            if not self.available()["stt"]:
                raise SpeechError("whisper-server or its model is missing from Bin/")
            await self.pool.reserve("whisper", self.whisper_vram)
            log = LOGS / "whisper-server.log"
            self._whisper = procs.start(
                [str(self.whisper_exe), "-m", str(self.whisper_model),
                 "--host", "127.0.0.1", "--port", str(self.whisper_port)],
                log, cwd=self.whisper_exe.parent)
            deadline = time.time() + 120
            async with httpx.AsyncClient(timeout=3) as c:
                while time.time() < deadline:
                    if self._whisper.poll() is not None:
                        await self.pool.unreserve("whisper")
                        raise SpeechError("whisper-server exited; see runtime/logs/whisper-server.log")
                    try:
                        r = await c.get(base + "/")
                        if r.status_code < 500:
                            return base
                    except httpx.HTTPError:
                        pass
                    await asyncio.sleep(0.5)
            raise SpeechError("whisper-server did not start in time")

    async def transcribe(self, wav: bytes) -> str:
        base = await self._ensure_whisper()
        async with httpx.AsyncClient(timeout=120) as c:
            r = await c.post(base + "/inference",
                             files={"file": ("speech.wav", wav, "audio/wav")},
                             data={"response_format": "json", "temperature": "0.0"})
        if r.status_code != 200:
            raise SpeechError(f"whisper-server {r.status_code}: {r.text[:200]}")
        text = r.json().get("text", "")
        text = re.sub(r"\[[A-Z _]+\]", "", text)  # [BLANK_AUDIO] etc.
        return text.strip()

    async def stop(self) -> None:
        if self._whisper:
            await asyncio.to_thread(procs.stop, self._whisper)
            self._whisper = None
            await self.pool.unreserve("whisper")

    # ------------------------------------------------------------ TTS
    async def speak(self, text: str) -> bytes:
        if not self.available()["tts"]:
            raise SpeechError("Piper or its voice is missing from Bin/Piper")
        text = speakable(text)
        if not text:
            raise SpeechError("nothing to say")
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "out.wav"

            def run() -> subprocess.CompletedProcess:
                return subprocess.run(
                    [str(self.piper), "--model", str(self.voice), "--output_file", str(out)],
                    input=text.encode("utf-8"), capture_output=True, timeout=120,
                    cwd=str(self.piper.parent),
                    creationflags=subprocess.CREATE_NO_WINDOW if procs.IS_WIN else 0,
                )

            p = await asyncio.to_thread(run)
            if p.returncode != 0 or not out.exists():
                raise SpeechError(f"piper failed: {p.stderr.decode(errors='replace')[-300:]}")
            return out.read_bytes()


def speakable(md: str) -> str:
    """Strip markdown and citations so the voice reads naturally."""
    t = re.sub(r"\s?\[(?:E\d+[,\s]*)+\]", "", md)
    t = re.sub(r"```.*?```", " ", t, flags=re.S)
    t = re.sub(r"[*_`#>]+", "", t)
    t = re.sub(r"^\s*[-•]\s+", "", t, flags=re.M)
    t = re.sub(r"\s+\n", "\n", t)
    t = re.sub(r"[ \t]{2,}", " ", t)
    return t.strip()[:4000]
