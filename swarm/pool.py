"""Model pool: starts/stops one llama-server per model inside a VRAM budget.

- `async with pool.use(model_id, ctx_per_slot, parallel) as base_url:` gives an
  OpenAI-compatible URL and keeps that model from being evicted while in use.
- When a new model does not fit, idle unpinned models are evicted (least
  recently used first). If everything is busy, the load waits.
- Every load records measured VRAM and load time in runtime/measurements, and
  later estimates use those measurements. This is the start of the capability cards.
- Remote models (gpu.remote_models) run on another machine on the home network, e.g. a laptop
  serving the checker: they are never started, stopped or counted against the VRAM budget here;
  `use()` just checks they answer and hands out their address.
"""
from __future__ import annotations

import asyncio
import contextlib
import json
import socket
import time
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable

import httpx

from swarm import llm, procs
from swarm.paths import LOGS, RUNTIME, repo_path
from swarm.registry import ModelCard, record_measurement

Emit = Callable[[dict], Awaitable[None]]


class ModelLoadError(RuntimeError):
    pass


class _RemoteProc:
    """Stands in for a llama-server process that runs on another machine."""
    pid = 0

    def poll(self):
        return None


@dataclass
class Running:
    card: ModelCard
    proc: Any
    port: int
    ctx_per_slot: int
    parallel: int
    est_mb: int
    pinned: bool = False
    offload: bool = False   # too big for the card: split between GPU and system RAM, runs alone
    on_cpu: bool = False    # runs entirely on the CPU (gpu.cpu_models): uses no VRAM, never evicted for it
    busy: int = 0
    last_used: float = field(default_factory=time.time)
    load_seconds: float = 0.0
    measured_mb: int | None = None
    url: str = ""           # remote model: its address on the network (nothing runs here)
    checked: float = 0.0    # remote model: when it last answered /health

    @property
    def base_url(self) -> str:
        return self.url or f"http://127.0.0.1:{self.port}"

    @property
    def remote(self) -> bool:
        return bool(self.url)

    @property
    def vram_mb(self) -> int:
        if self.on_cpu or self.url:
            return 0
        if self.offload:
            return self.est_mb  # the whole budget: nothing else loads next to it
        return self.measured_mb or self.est_mb

    def alive(self) -> bool:
        return self.proc.poll() is None


# extra llama-server arguments for particular models (model-name prefix -> args)
MODEL_ARGS = {
    # Apriel's template makes llama.cpp exit ("Unable to generate parser for this template")
    "Apriel": ["--chat-template-file", "config/templates/apriel.jinja"],
    # ERNIE's own template gives a strict reply parser that rejects many of its answers (HTTP 500
    # "does not match the expected peg-native format")
    "ERNIE": ["--chat-template-file", "config/templates/ernie.jinja"],
    # OLMo 3's function-calling template: same "Unable to generate parser" as Apriel
    "Olmo-3": ["--chat-template-file", "config/templates/olmo3.jinja"],
    # Command R7B's template: llama-server rejects its plain replies ("does not match the expected
    # peg-native format"), found by the preflight 2026-10-02
    "Command-R": ["--chat-template-file", "config/templates/command-r7b.jinja"],
}

# models whose template forces a thinking block before every answer: a JSON grammar cannot be
# used with them (llama.cpp b10152: "Unexpected empty grammar stack after accepting piece"), so
# their JSON is parsed from the reply instead and they get room to think first (see llm.chat)
FORCED_THINKERS = ("ERNIE",)
# models that ignore enable_thinking=false and need "/no_think" in the system message instead
NO_THINK_SWITCH = ("NVIDIA-Nemotron",)
# models that write their end-of-turn marker as text instead of stopping on it
STOP_WORDS = {"Command-R": ["<|END_OF_TURN_TOKEN|>", "<|END_RESPONSE|>"]}


class ModelPool:
    def __init__(self, cfg: dict, cards: dict[str, ModelCard], emit: Emit | None = None):
        g = cfg["gpu"]
        self.cfg = cfg
        self.cards = cards
        self.budget_mb = int(g["vram_budget_mb"])
        self.exe = repo_path(g["llama_server"])
        self.port_lo, self.port_hi = g["port_range"]
        self.running: dict[str, Running] = {}
        self.reservations: dict[str, int] = {}
        self._load_lock = asyncio.Lock()
        self._changed = asyncio.Condition()
        self.emit: Emit | None = emit
        # Small models waste their budget on hidden "thinking"; turn it off server-side.
        self.extra_args: list[str] = list(g.get("extra_args", ["--reasoning-budget", "0"]))
        # models whose chat format breaks when reasoning is switched off server-side (gpt-oss loops
        # on empty "analysis" messages); they get reasoning_effort=low from the request instead
        self.keep_reasoning = [m.lower() for m in g.get("keep_reasoning_models", ["gpt-oss"])]
        # Plan-ahead scheduling: the orchestrator says which models it needs next, in order.
        # Eviction removes the model needed furthest in the future (not the least recently used),
        # and prefetch loads the next stage's model in the background as soon as it fits.
        self.upcoming: list[str] = []
        self.prefetch_enabled = bool(g.get("prefetch", True))
        self._prefetch: dict[str, asyncio.Task] = {}
        # System RAM protection. With 16 GB of RAM, several model servers that each keep their
        # model file mapped in RAM filled it to 93% and destabilised the PC. Fully-offloaded
        # models are now loaded with --no-mmap (the weights live only on the GPU), each server
        # gets few CPU threads, and a load waits/evicts while free RAM is below the reserve.
        self.min_free_ram_mb = int(g.get("min_free_ram_mb", 2500))
        self.ram_per_server_mb = int(g.get("ram_per_server_mb", 700))
        self.threads = int(g.get("threads_per_model", 2))
        self.no_mmap = bool(g.get("no_mmap", True))
        self.offload_threads = int(g.get("offload_threads", 8))
        # small models that run on the CPU next to the GPU swarm (model-name prefixes): they take no
        # VRAM, so they stay loaded and never trigger a swap (Chris, 2026-10-03: LFM2.5-1.2B)
        self.cpu_models = [str(m).lower() for m in (g.get("cpu_models") or [])]
        self.cpu_threads = int(g.get("cpu_threads", 6))
        self.fit_margin_mb = int(g.get("fit_margin_mb", 1024))
        # models served by other machines on the network (model id -> url or {url, ctx_per_slot, parallel})
        self.remote_models: dict[str, dict] = {}
        self.remote_running: dict[str, Running] = {}
        self.set_remote(g.get("remote_models") or {})
        self._kill_stale()

    def set_remote(self, mapping: dict) -> None:
        """Which models live on another machine. A model that isn't in Models/ on this PC gets a
        card of its own, so configs can name it like any other model."""
        from swarm.registry import _kind_for, _lab_for
        out: dict[str, dict] = {}
        for mid, v in (mapping or {}).items():
            spec = {"url": v} if isinstance(v, str) else dict(v or {})
            url = str(spec.get("url", "")).rstrip("/")
            if not url:
                continue
            if not url.startswith(("http://", "https://")):
                url = "http://" + url
            out[str(mid)] = {"url": url, "ctx_per_slot": int(spec.get("ctx_per_slot", 0) or 0),
                             "parallel": int(spec.get("parallel", 1) or 1)}
            if mid not in self.cards:
                lab, lineage = _lab_for(str(mid))
                self.cards[str(mid)] = ModelCard(id=str(mid), path=f"remote:{url}", size_mb=0, lab=lab,
                                                 lineage=lineage, kind=_kind_for(str(mid)))
        for mid in [m for m in self.remote_running if m not in out or out[m]["url"] != self.remote_running[m].url]:
            self.remote_running.pop(mid, None)
        self.remote_models = out

    def is_remote(self, model_id: str) -> bool:
        return model_id in self.remote_models

    async def _ensure_remote(self, model_id: str, ctx_per_slot: int, parallel: int) -> Running:
        spec = self.remote_models[model_id]
        r = self.remote_running.get(model_id)
        if r is None:
            r = Running(card=self.cards[model_id], proc=_RemoteProc(), port=0,
                        ctx_per_slot=spec["ctx_per_slot"] or ctx_per_slot, parallel=spec["parallel"],
                        est_mb=0, url=spec["url"])
            self.remote_running[model_id] = r
        if time.time() - r.checked > 60:  # make sure the other machine is up (cheap, on the home network)
            t0 = time.time()
            try:
                async with httpx.AsyncClient(timeout=8) as c:
                    resp = await c.get(r.url + "/health")
                ok = resp.status_code == 200
                why = f"HTTP {resp.status_code}"
            except httpx.HTTPError as e:
                ok, why = False, f"{type(e).__name__}"
            if not ok:
                r.checked = 0.0
                raise ModelLoadError(f"{model_id} runs on another machine ({r.url}) but it isn't answering "
                                     f"({why}). Is that machine on and its model server running?")
            first = r.checked == 0.0 and r.load_seconds == 0.0
            r.checked = time.time()
            if first:
                r.load_seconds = time.time() - t0
                await self._emit({"type": "model", "event": "ready", "model": model_id, "lab": r.card.lab,
                                  "vram_mb": 0, "seconds": round(r.load_seconds, 2), "remote": r.url})
                if spec["ctx_per_slot"] and ctx_per_slot > spec["ctx_per_slot"]:
                    await self._emit({"type": "warning", "message":
                                      f"{model_id} on {r.url} has {spec['ctx_per_slot']} tokens per request; this "
                                      f"configuration asks for {ctx_per_slot}. Longer prompts will fail there."})
        return r

    def _kill_stale(self) -> None:
        try:
            old = json.loads((RUNTIME / "pids.json").read_text())
        except Exception:
            return
        n = procs.kill_stale([int(p) for p in old if isinstance(p, int)])
        _write_pids([])
        if n:
            print(f"Stopped {n} model server(s) left over from an earlier run", flush=True)

    # ------------------------------------------------------------ accounting
    def used_mb(self) -> int:
        return sum(r.vram_mb for r in self.running.values()) + sum(self.reservations.values())

    def on_cpu(self, card: ModelCard) -> bool:
        return any(card.id.lower().startswith(p) for p in self.cpu_models)

    def estimate_mb(self, card: ModelCard, ctx_per_slot: int, parallel: int) -> int:
        if self.on_cpu(card):
            return 0
        key = f"vram_mb@{ctx_per_slot}x{parallel}"
        if key in card.measured:
            return int(card.measured[key])
        ctx_total = ctx_per_slot * parallel
        # weights + compute buffers + KV cache (rough; replaced by measurement after first load)
        kv = int(ctx_total * 0.06)
        return int(card.size_mb * 1.05) + 350 + kv

    def status(self) -> dict:
        return {
            "budget_mb": self.budget_mb,
            "used_mb": self.used_mb(),
            "reservations": dict(self.reservations),
            "upcoming": list(self.upcoming),
            "prefetching": list(self._prefetch),
            "models": [
                {
                    "model": r.card.id, "lab": r.card.lab, "lineage": r.card.lineage,
                    "vram_mb": r.vram_mb, "measured": r.measured_mb is not None,
                    "busy": r.busy, "pinned": r.pinned, "port": r.port,
                    "load_seconds": round(r.load_seconds, 1), "alive": r.alive(),
                }
                for r in self.running.values()
            ] + [
                {"model": r.card.id, "lab": r.card.lab, "lineage": r.card.lineage, "vram_mb": 0,
                 "measured": False, "busy": r.busy, "pinned": False, "port": 0, "remote": r.url,
                 "load_seconds": round(r.load_seconds, 2), "alive": True}
                for r in self.remote_running.values()
            ],
        }

    async def _emit(self, ev: dict) -> None:
        if self.emit:
            try:
                await self.emit(ev)
            except Exception:
                pass

    async def _emit_pool(self) -> None:
        await self._emit({"type": "pool", **self.status()})

    # ------------------------------------------------------------ public API
    @contextlib.asynccontextmanager
    async def use(self, model_id: str, ctx_per_slot: int, parallel: int = 1, pin: bool = False):
        r = await self.ensure(model_id, ctx_per_slot, parallel, pin)
        if any(r.card.id.lower().startswith(p.lower()) for p in FORCED_THINKERS):
            llm.FORCED_THINKING.add(r.base_url.rstrip("/"))
        else:
            llm.FORCED_THINKING.discard(r.base_url.rstrip("/"))
        stops = [w for p, ws in STOP_WORDS.items() if r.card.id.lower().startswith(p.lower()) for w in ws]
        if stops:
            llm.STOP_WORDS[r.base_url.rstrip("/")] = stops
        else:
            llm.STOP_WORDS.pop(r.base_url.rstrip("/"), None)
        if any(r.card.id.lower().startswith(p.lower()) for p in NO_THINK_SWITCH):
            llm.NO_THINK_SWITCH.add(r.base_url.rstrip("/"))
        else:
            llm.NO_THINK_SWITCH.discard(r.base_url.rstrip("/"))
        r.busy += 1
        r.last_used = time.time()
        try:
            yield r.base_url
        finally:
            r.busy -= 1
            r.last_used = time.time()
            async with self._changed:
                self._changed.notify_all()

    async def ensure(self, model_id: str, ctx_per_slot: int, parallel: int = 1, pin: bool = False) -> Running:
        if model_id in self.remote_models:
            return await self._ensure_remote(model_id, ctx_per_slot, parallel)
        if model_id not in self.cards:
            raise ModelLoadError(f"Unknown model '{model_id}'. Folder names in Models/ are the valid ids.")
        async with self._load_lock:
            r = self.running.get(model_id)
            if r and r.alive() and r.ctx_per_slot >= ctx_per_slot and r.parallel >= parallel:
                # a big (offloaded) model must never become pinned: it holds the whole card, and a pin
                # left it unevictable so every other model waited 15 minutes (bigcoord-qwen36 overnight)
                r.pinned = (r.pinned or pin) and not r.offload
                return r
            if r:  # dead, or started with too small a context: restart
                if r.alive():  # big enough for both jobs (e.g. one model as worker AND coordinator), so it
                    ctx_per_slot = max(ctx_per_slot, r.ctx_per_slot)  # doesn't restart back and forth
                    parallel = max(parallel, r.parallel)
                await self._wait_idle(r)
                await self._stop(model_id, reason="restart")
            card = self.cards[model_id]
            need = self.estimate_mb(card, ctx_per_slot, parallel)
            offload = self.needs_offload(card, ctx_per_slot, parallel) and not self.on_cpu(card)
            if offload:
                # a big model gets the whole card (everything else is unloaded) and llama.cpp's
                # --fit puts as many layers / experts on the GPU as fit; the rest runs from RAM.
                # Never pinned, so the next stage can unload it again.
                need, pin = self.budget_mb, False
                await self._emit({"type": "warning", "message":
                    f"{model_id} ({card.size_mb / 1024:.1f} GB) is bigger than the graphics card budget: "
                    f"running it alone, split between the GPU and system RAM (slower)"})
            await self._make_room(need, model_id)
            r = await self._start(card, ctx_per_slot, parallel, need, pin, offload=offload)
            return r

    def needs_offload(self, card: ModelCard, ctx_per_slot: int, parallel: int) -> bool:
        """True when a model cannot sit entirely on the card within the budget."""
        weights = int(card.size_mb * 1.05) + 350
        kv = int(ctx_per_slot * parallel * 0.12)  # generous: bigger models have bigger KV caches
        return weights + kv > self.budget_mb - self.fit_margin_mb

    async def reserve(self, name: str, mb: int) -> None:
        """Hold VRAM for something that is not a llama-server (e.g. Whisper)."""
        async with self._load_lock:
            await self._make_room(mb, name)
            self.reservations[name] = mb
        await self._emit_pool()

    async def unreserve(self, name: str) -> None:
        self.reservations.pop(name, None)
        async with self._changed:
            self._changed.notify_all()
        await self._emit_pool()

    async def unload(self, model_id: str) -> None:
        async with self._load_lock:
            if model_id in self.running:
                await self._stop(model_id, reason="unload")

    # ------------------------------------------------------------ plan-ahead scheduling
    def plan_ahead(self, models: list[str]) -> None:
        """Order in which models will be needed next (soonest first)."""
        self.upcoming = list(dict.fromkeys(m for m in models if m))

    def _next_use(self, model_id: str) -> int:
        try:
            return self.upcoming.index(model_id)
        except ValueError:
            return 10_000  # not needed at all in the known future

    def prefetch(self, model_id: str, ctx_per_slot: int, parallel: int = 1, pin: bool = False) -> None:
        """Load a model in the background when it fits, without disturbing models needed sooner."""
        if not self.prefetch_enabled or model_id not in self.cards or model_id in self.remote_models:
            return
        r = self.running.get(model_id)
        if (r and r.alive()) or model_id in self._prefetch:
            return
        self._prefetch[model_id] = asyncio.create_task(self._prefetch_loop(model_id, ctx_per_slot, parallel, pin))

    def cancel_prefetch(self) -> None:
        for t in self._prefetch.values():
            t.cancel()
        self._prefetch.clear()

    async def _prefetch_loop(self, model_id: str, ctx_per_slot: int, parallel: int, pin: bool) -> None:
        deadline = time.time() + 300
        try:
            while time.time() < deadline and model_id in self.upcoming:
                async with self._load_lock:
                    r = self.running.get(model_id)
                    if r and r.alive():
                        return
                    card = self.cards[model_id]
                    need = self.estimate_mb(card, ctx_per_slot, parallel)
                    if await self._make_room(need, model_id, only_later=True):
                        await self._emit({"type": "model", "event": "prefetch", "model": model_id})
                        await self._start(card, ctx_per_slot, parallel, need, pin)
                        return
                async with self._changed:
                    try:
                        await asyncio.wait_for(self._changed.wait(), timeout=5)
                    except asyncio.TimeoutError:
                        pass
        except asyncio.CancelledError:
            raise
        except Exception as e:  # a failed prefetch is not fatal; the real request will retry and report
            await self._emit({"type": "warning", "message": f"background load of {model_id} failed: {e}"[:300]})
        finally:
            if self._prefetch.get(model_id) is asyncio.current_task():
                self._prefetch.pop(model_id, None)

    async def unload_all(self, keep_pinned: bool = False) -> None:
        self.cancel_prefetch()
        self.upcoming = []
        async with self._load_lock:
            for mid in list(self.running):
                if keep_pinned and self.running[mid].pinned:
                    continue
                await self._stop(mid, reason="unload")

    async def shutdown(self) -> None:
        self.cancel_prefetch()
        for mid in list(self.running):
            r = self.running.pop(mid)
            await asyncio.to_thread(procs.stop, r.proc)
        _write_pids([])

    # ------------------------------------------------------------ internals
    async def _wait_idle(self, r: Running, timeout: float = 600) -> None:
        deadline = time.time() + timeout
        async with self._changed:
            while r.busy > 0 and time.time() < deadline:
                try:
                    await asyncio.wait_for(self._changed.wait(), timeout=5)
                except asyncio.TimeoutError:
                    pass

    def _evictable(self, for_what: str, only_later: bool) -> list[Running]:
        """Idle, unpinned models; with only_later, just those needed after `for_what`."""
        target = self._next_use(for_what)
        return [r for r in self.running.values()
                if r.busy == 0 and not r.pinned and r.card.id != for_what and not r.on_cpu
                and (not only_later or self._next_use(r.card.id) > target)]

    def _pick_victim(self, candidates: list[Running], shortfall: int) -> Running:
        """Prefer ONE eviction that frees enough memory: of the models big enough on their own,
        take the one needed furthest in the future (ties: the smallest). If no single model is
        big enough, take the biggest of those needed furthest in the future."""
        enough = [r for r in candidates if r.vram_mb >= shortfall]
        if enough:
            return max(enough, key=lambda r: (self._next_use(r.card.id), -r.vram_mb))
        latest = max(self._next_use(r.card.id) for r in candidates)
        tier = [r for r in candidates if self._next_use(r.card.id) == latest]
        return max(tier, key=lambda r: r.vram_mb)

    async def _make_room(self, need: int, for_what: str, only_later: bool = False) -> bool:
        """Free VRAM for `need` MB. only_later=True (prefetch): never wait, never load anyway,
        and only evict models needed later than `for_what`; returns False if it can't fit."""
        deadline = time.time() + 900
        warned = False
        while True:
            # drop dead servers from the books
            for mid in [m for m, r in self.running.items() if not r.alive()]:
                await self._stop(mid, reason="crashed")
            gpu = await asyncio.to_thread(procs.gpu_memory_mb)
            short_budget = self.used_mb() + need - self.budget_mb
            short_card = 0 if gpu is None or need <= 0 else (need + 300) - (gpu[1] - gpu[0])
            ram = await asyncio.to_thread(procs.system_ram_mb)
            short_ram = 0 if ram is None else (self.min_free_ram_mb + self.ram_per_server_mb) - ram[0]
            # evicting any one server frees roughly ram_per_server_mb of RAM (and its VRAM)
            shortfall = max(short_budget, short_card, 1 if short_ram > 0 else 0)
            if shortfall <= 0:
                return True
            candidates = self._evictable(for_what, only_later)
            if only_later and sum(r.vram_mb for r in candidates) < shortfall:
                return False  # evicting everything allowed still wouldn't fit: don't evict anything
            others_busy = any(r.busy for r in self.running.values() if r.card.id != for_what)
            if candidates and (sum(r.vram_mb for r in candidates) >= shortfall or not others_busy):
                victim = self._pick_victim(candidates, shortfall)
                await self._stop(victim.card.id, reason=f"make room for {for_what}")
                continue
            # Not enough can be freed yet, but busy models will finish soon: wait instead of
            # unloading a model now and another one later (two reloads instead of one).
            if only_later:
                return False
            # A pinned model that is idle right now (e.g. a big coordinator while the workers run)
            # is unloaded rather than making everyone wait: with an 11 GB coordinator pinned, a worker
            # waited the full 15 minutes and the question timed out (bake-off 2, Phi-4-15B).
            pinned_idle = [r for r in self.running.values()
                           if r.busy == 0 and r.pinned and r.card.id != for_what]
            waited = time.time() - (deadline - 900)
            grace = float(self.cfg["gpu"].get("pinned_evict_after_s", 30))
            if pinned_idle and waited >= grace and sum(r.vram_mb for r in candidates + pinned_idle) >= shortfall:
                victim = (self._pick_victim(candidates, shortfall) if candidates
                          else max(pinned_idle, key=lambda r: r.vram_mb))
                await self._stop(victim.card.id, reason=f"make room for {for_what}")
                continue
            ram_only = short_ram > 0 and short_budget <= 0 and short_card <= 0
            if ram_only and time.time() > deadline - 900 + 60:
                # low RAM that no idle model can free (the other models are busy this moment):
                # waiting the full 15 minutes turned one question into an hour; wait at most a minute
                await self._emit({"type": "warning", "message":
                    f"system RAM is low ({ram[0]} MB free) and busy models can't be unloaded; loading {for_what} anyway"})
                return True
            if not self.running or time.time() > deadline:
                # Nothing we can evict. Load anyway; llama.cpp will fit what it can.
                if short_ram > 0 and short_budget <= 0 and short_card <= 0:
                    await self._emit({"type": "warning", "message":
                        f"system RAM is low ({ram[0]} MB free); loading {for_what} anyway - close other programs"})
                else:
                    await self._emit({"type": "warning", "message":
                        f"{for_what} needs ~{need} MB but only {self.budget_mb - self.used_mb()} MB of the "
                        f"budget is free and nothing can be unloaded. Loading anyway; it may run slowly."})
                return True
            if not warned:
                what = "system RAM" if short_ram > 0 and short_budget <= 0 and short_card <= 0 else "VRAM"
                await self._emit({"type": "waiting", "message": f"waiting for {what} to load {for_what}"})
                warned = True
            async with self._changed:
                try:
                    await asyncio.wait_for(self._changed.wait(), timeout=5)
                except asyncio.TimeoutError:
                    pass

    def _free_port(self) -> int:
        used = {r.port for r in self.running.values()}
        for p in range(self.port_lo, self.port_hi + 1):
            if p in used:
                continue
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                try:
                    s.bind(("127.0.0.1", p))
                    return p
                except OSError:
                    continue
        raise ModelLoadError("No free port in gpu.port_range")

    def _exe_for(self, card: ModelCard):
        """Some models need their own llama.cpp build (e.g. Bonsai's ternary weights need the PrismML
        fork): gpu.model_servers maps a model-name prefix to that llama-server."""
        # built-in defaults live here, not in config/swarm.yaml, so frozen configurations keep their hash
        servers = {"Bonsai": "Bin/llama-prism/llama-server.exe", **(self.cfg["gpu"].get("model_servers") or {})}
        for prefix, path in servers.items():
            if card.id.lower().startswith(str(prefix).lower()):
                return repo_path(path)
        return self.exe

    def _extra_for(self, card: ModelCard) -> list[str]:
        if any(k in card.id.lower() for k in self.keep_reasoning):
            args = [a for i, a in enumerate(self.extra_args)
                    if a != "--reasoning-budget" and (i == 0 or self.extra_args[i - 1] != "--reasoning-budget")]
        else:
            args = list(self.extra_args)
        # models whose own chat template this llama.cpp build cannot parse get a plain one
        for prefix, extra in MODEL_ARGS.items():
            if card.id.lower().startswith(prefix.lower()):
                args += [str(repo_path(a)) if a.startswith("config/") else a for a in extra]
        # llama-server keeps old prompts in SYSTEM RAM to reuse them (up to 8 GiB per server by
        # default). With several servers that filled the 16 GB of RAM a little more every question
        # until Windows restarted (the FRAMES run, 2026-09-29). Our prompts are rarely reused, so
        # switch it off unless the config sets it.
        if "--cache-ram" not in args and "-cram" not in args:
            args += ["--cache-ram", str(self.cfg["gpu"].get("cache_ram_mb", 0))]
        return args

    def build_cmd(self, card: ModelCard, port: int, ctx_per_slot: int, parallel: int,
                  offload: bool = False) -> list[str]:
        if offload:
            # let llama.cpp fit layers/experts to the free VRAM (keeping a margin); keep the file
            # memory-mapped so the CPU part can be paged in from disk instead of filling RAM
            return [
                str(self._exe_for(card)), "-m", card.path,
                "--host", "127.0.0.1", "--port", str(port),
                "--fit", "on", "--fit-target", str(self.fit_margin_mb),
                "-c", str(ctx_per_slot * parallel),
                "-np", str(parallel),
                "--jinja",
                "-t", str(self.offload_threads),
                *self._extra_for(card),
            ]
        if self.on_cpu(card):
            return [
                str(self._exe_for(card)), "-m", card.path,
                "--host", "127.0.0.1", "--port", str(port),
                "-ngl", "0",
                "-c", str(ctx_per_slot * parallel),
                "-np", str(parallel),
                "--jinja",
                "-t", str(self.cpu_threads),
                *self._extra_for(card),
            ]
        return [
            str(self._exe_for(card)), "-m", card.path,
            "--host", "127.0.0.1", "--port", str(port),
            "-ngl", "999",
            "-c", str(ctx_per_slot * parallel),
            "-np", str(parallel),
            "--jinja",
            # a reranker scores (query, passage) pairs through /v1/rerank instead of chatting
            *(["--embedding", "--reranking", "--pooling", "rank"] if card.kind == "reranker" else []),
            # the whole model is on the GPU: don't also keep the file mapped in system RAM,
            # and don't spin up a CPU thread per core in every server
            *(["--no-mmap"] if self.no_mmap else []),
            "-t", str(self.threads),
            *self._extra_for(card),
        ]

    async def _start(self, card: ModelCard, ctx_per_slot: int, parallel: int, est: int, pin: bool,
                     offload: bool = False) -> Running:
        exe = self._exe_for(card)
        if not exe.exists():
            raise ModelLoadError(f"llama-server not found at {exe}")
        port = self._free_port()
        await self._emit({"type": "model", "event": "loading", "model": card.id, "lab": card.lab,
                          "est_mb": est})
        before = await asyncio.to_thread(procs.gpu_memory_mb)
        t0 = time.time()
        log_path = LOGS / "models" / f"{card.id}.log"
        env = None
        if self.on_cpu(card):
            # hide the GPU: a CUDA build with -ngl 0 still puts compute buffers on the card (and
            # uses it for prompt processing), which takes VRAM the budget doesn't count
            import os
            env = {**os.environ, "CUDA_VISIBLE_DEVICES": "-1"}
        proc = procs.start(self.build_cmd(card, port, ctx_per_slot, parallel, offload=offload), log_path, env=env)
        r = Running(card=card, proc=proc, port=port, ctx_per_slot=ctx_per_slot,
                    parallel=parallel, est_mb=est, pinned=pin, offload=offload, on_cpu=self.on_cpu(card))
        self.running[card.id] = r
        _write_pids([x.proc.pid for x in self.running.values()])
        try:
            await self._wait_healthy(r, log_path, timeout=600 if offload else 240)
        except Exception as e:
            self.running.pop(card.id, None)
            await asyncio.to_thread(procs.stop, proc)
            if self.extra_args and ("invalid argument" in str(e) or "unknown argument" in str(e)):
                # this llama-server build doesn't know one of the extra flags: drop them and retry
                await self._emit({"type": "warning", "message": f"llama-server rejected {self.extra_args}; retrying without them"})
                self.extra_args = []
                return await self._start(card, ctx_per_slot, parallel, est, pin, offload=offload)
            await self._emit({"type": "model", "event": "failed", "model": card.id, "error": str(e)[:500]})
            raise
        r.load_seconds = time.time() - t0
        await asyncio.sleep(0.3)
        after = await asyncio.to_thread(procs.gpu_memory_mb)
        if before and after and after[0] > before[0] and not r.on_cpu:
            r.measured_mb = after[0] - before[0]
            record_measurement(card.id, f"vram_mb@{ctx_per_slot}x{parallel}", r.measured_mb)
            card.measured[f"vram_mb@{ctx_per_slot}x{parallel}"] = r.measured_mb
        record_measurement(card.id, "load_seconds", round(r.load_seconds, 2))
        await self._emit({"type": "model", "event": "ready", "model": card.id, "lab": card.lab,
                          "vram_mb": r.vram_mb, "seconds": round(r.load_seconds, 1)})
        await self._emit_pool()
        return r

    async def _wait_healthy(self, r: Running, log_path, timeout: float = 240) -> None:
        deadline = time.time() + timeout
        async with httpx.AsyncClient(timeout=3) as c:
            while time.time() < deadline:
                if not r.alive():
                    raise ModelLoadError(f"{r.card.id} exited while loading:\n{_tail(log_path)}")
                try:
                    resp = await c.get(r.base_url + "/health")
                    if resp.status_code == 200:
                        return
                except httpx.HTTPError:
                    pass
                await asyncio.sleep(0.4)
        raise ModelLoadError(f"{r.card.id} did not become ready in {timeout}s:\n{_tail(log_path)}")

    async def _stop(self, model_id: str, reason: str) -> None:
        r = self.running.pop(model_id, None)
        if not r:
            return
        await asyncio.to_thread(procs.stop, r.proc)
        _write_pids([x.proc.pid for x in self.running.values()])
        await self._emit({"type": "model", "event": "unloaded", "model": model_id, "reason": reason})
        await self._emit_pool()
        async with self._changed:
            self._changed.notify_all()


def _tail(path, n: int = 12) -> str:
    try:
        lines = open(path, encoding="utf-8", errors="replace").read().splitlines()
        return "\n".join(lines[-n:])
    except Exception:
        return ""


def _write_pids(pids: list[int]) -> None:
    try:
        RUNTIME.mkdir(parents=True, exist_ok=True)
        (RUNTIME / "pids.json").write_text(json.dumps(pids))
    except Exception:
        pass
