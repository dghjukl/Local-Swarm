"""Local web UI: FastAPI + one WebSocket per browser tab."""
from __future__ import annotations

import asyncio
import contextlib
import os
import json
import logging
from pathlib import Path

from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse, Response

from swarm.config import load_config
from swarm.orchestrator import Swarm
from swarm.pool import ModelPool
from swarm.registry import scan_models
from swarm.speech import Speech, SpeechError
from swarm.tools import DirectResearch, ResearchMCP, research_mcp_available

STATIC = Path(__file__).parent / "static"
log = logging.getLogger("swarm")


class State:
    def __init__(self):
        self.cfg: dict = {}
        self.cards: dict = {}
        self.pool: ModelPool | None = None
        self.research: ResearchMCP | None = None
        self.swarm: Swarm | None = None
        self.speech: Speech | None = None
        self.sockets: set[WebSocket] = set()
        self.run_task: asyncio.Task | None = None
        self.notices: list[str] = []

    async def broadcast(self, ev: dict) -> None:
        dead = []
        for ws in list(self.sockets):
            try:
                await ws.send_text(json.dumps(ev, default=str))
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.sockets.discard(ws)


def create_app(cfg: dict | None = None, *, cards: dict | None = None, research: ResearchMCP | None = None,
               start_research: bool = True, warm: bool = True) -> FastAPI:
    st = State()

    @contextlib.asynccontextmanager
    async def lifespan(app: FastAPI):
        st.cfg = cfg or load_config()
        st.cards = cards if cards is not None else scan_models()
        st.pool = ModelPool(st.cfg, st.cards, emit=st.broadcast)
        st.research = research
        if st.research is None and start_research and research_mcp_available(st.cfg):
            rm = ResearchMCP(st.cfg["research"].get("fetch_workers", 3))
            try:
                await rm.start()
                st.research = rm
                log.info("research-mcp started (%d copies)", rm.copies)
            except Exception as e:
                log.exception("research-mcp failed to start")
                st.research = DirectResearch()
                st.notices.append(f"research-mcp did not start ({e}); using the built-in web search instead. "
                                  "Details: runtime/logs/research-mcp.log and swarm.log")
        if st.research is None and start_research and os.environ.get("SWARM_NO_WEB") != "1":
            st.research = DirectResearch()  # built-in backend: web + news search, article extraction
        st.swarm = Swarm(st.cfg, st.pool, st.cards, st.research)
        st.speech = Speech(st.cfg, st.pool)
        st.notices.extend(st.swarm.check_roster())
        warm_task = None
        if warm and not st.swarm.check_roster():
            c = st.cfg["coordinator"]

            async def warmup():
                with contextlib.suppress(Exception):
                    await st.pool.ensure(c["model"], c["ctx_per_slot"], c["parallel"], pin=True)
            warm_task = asyncio.create_task(warmup())
        yield
        if warm_task:
            warm_task.cancel()
        if st.run_task and not st.run_task.done():
            st.run_task.cancel()
        with contextlib.suppress(Exception):
            await st.speech.stop()
        if st.research and st.research is not research:
            with contextlib.suppress(Exception):
                await st.research.close()
        await st.pool.shutdown()

    app = FastAPI(title="Local Swarm", lifespan=lifespan)
    app.state.swarm_state = st

    @app.get("/")
    async def index():
        return FileResponse(STATIC / "index.html", headers={"Cache-Control": "no-store"})

    @app.get("/api/status")
    async def status():
        sw = st.swarm
        return {
            "pool": st.pool.status(),
            "roles": {
                "coordinator": st.cfg["coordinator"]["model"],
                "verifier": st.cfg["verifier"]["model"],
                "team": sw.team() if sw else [],
            },
            "cards": {k: {"lab": v.lab, "lineage": v.lineage, "kind": v.kind, "size_mb": v.size_mb}
                      for k, v in st.cards.items()},
            "web_search": st.research is not None,
            "web_search_backend": getattr(st.research, "name", None),
            "speech": st.speech.available() if st.speech else {},
            "notices": st.notices,
            "busy": bool(st.run_task and not st.run_task.done()),
        }

    @app.post("/api/stt")
    async def stt(request: Request):
        audio = await request.body()
        if len(audio) < 1000:
            return JSONResponse({"error": "no audio received"}, status_code=400)
        try:
            text = await st.speech.transcribe(audio)
        except SpeechError as e:
            return JSONResponse({"error": str(e)}, status_code=500)
        return {"text": text}

    @app.post("/api/tts")
    async def tts(request: Request):
        body = await request.json()
        try:
            wav = await st.speech.speak(body.get("text", ""))
        except SpeechError as e:
            return JSONResponse({"error": str(e)}, status_code=500)
        return Response(wav, media_type="audio/wav")

    @app.post("/api/unload")
    async def unload():
        if st.run_task and not st.run_task.done():
            return JSONResponse({"error": "a question is running"}, status_code=409)
        await st.pool.unload_all()
        await st.speech.stop()
        return st.pool.status()

    @app.websocket("/ws")
    async def ws_endpoint(ws: WebSocket):
        await ws.accept()
        st.sockets.add(ws)
        await ws.send_text(json.dumps({"type": "pool", **st.pool.status()}))
        for n in st.notices:
            await ws.send_text(json.dumps({"type": "warning", "message": n}))
        try:
            while True:
                msg = json.loads(await ws.receive_text())
                if msg.get("type") == "ask":
                    q = (msg.get("question") or "").strip()
                    if not q:
                        continue
                    if st.run_task and not st.run_task.done():
                        await ws.send_text(json.dumps({"type": "error", "message": "The swarm is busy with another question."}))
                        continue

                    async def run(q=q, force=bool(msg.get("force_research"))):
                        try:
                            await st.swarm.run(q, st.broadcast, force_research=force)
                        finally:
                            st.pool.emit = st.broadcast

                    st.run_task = asyncio.create_task(run())
                elif msg.get("type") == "cancel":
                    if st.run_task and not st.run_task.done():
                        st.run_task.cancel()
                        await st.broadcast({"type": "cancelled"})
        except WebSocketDisconnect:
            pass
        finally:
            st.sockets.discard(ws)

    return app
