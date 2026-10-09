"""Plan-ahead scheduling with the real measured model sizes and a 14.5 GB budget."""
import pytest

from swarm.orchestrator import Swarm
from test_integration import FakeResearch

SIZES = {"Qwen3.5-4B": 4150, "Ministral-3-3B-Instruct": 3360, "LFM2.5-2.6B": 2130,
         "Phi-4-mini-instruct": 3890, "Granite-4.1-3B": 3450}


async def _run_questions(cfg, cards, pool_cls, prefetch: bool, n: int = 3):
    cfg = {**cfg, "gpu": {**cfg["gpu"], "vram_budget_mb": 14500, "prefetch": prefetch}}
    events = []

    async def emit(e):
        events.append(e)

    pool = pool_cls(cfg, cards, emit=emit)
    pool.estimate_mb = lambda card, c, p: SIZES.get(card.id, 1000)
    sw = Swarm(cfg, pool, cards, FakeResearch())
    prep = None
    loads_per_q = []
    try:
        for i in range(n):
            before = sum(1 for e in events if e.get("type") == "model" and e.get("event") == "ready")
            if prep is None:
                prep = await sw.prepare("Tell me about the Eiffel Tower")
            trace = await sw.run("Tell me about the Eiffel Tower", emit, prepared=prep)
            assert trace.get("error") is None, trace.get("error")
            import asyncio
            await asyncio.sleep(3)  # let background loads for the next question finish
            after = sum(1 for e in events if e.get("type") == "model" and e.get("event") == "ready")
            loads_per_q.append(after - before)
            assert pool.used_mb() <= 14500
    finally:
        await pool.shutdown()
    return loads_per_q


async def test_plan_ahead_keeps_loads_low(cfg, cards, mock_pool_cls):
    loads = await _run_questions(cfg, cards, mock_pool_cls, prefetch=True)
    print("loads per question with plan-ahead:", loads)
    # first question loads all 5 models; after that only the verifier and one worker swap
    assert loads[0] == 5
    assert all(x <= 2 for x in loads[1:]), loads


def test_victim_choice_prefers_one_eviction(cfg, cards, mock_pool_cls):
    from swarm.pool import Running
    pool = mock_pool_cls(cfg, cards)
    pool.plan_ahead(["Granite-4.1-3B", "Qwen3.5-4B", "Ministral-3-3B-Instruct", "LFM2.5-2.6B", "Phi-4-mini-instruct"])
    rs = [Running(card=cards[m], proc=None, port=0, ctx_per_slot=4096, parallel=2, est_mb=SIZES[m])
          for m in ("Ministral-3-3B-Instruct", "LFM2.5-2.6B", "Phi-4-mini-instruct")]
    # all three workers are needed later than Granite; LFM (2.1 GB) alone isn't enough for a 2.5 GB
    # shortfall, so it must pick a single model that is: Ministral (3.4) rather than Phi (3.9)
    # ... but only among the models needed LAST, which here is Phi
    assert pool._pick_victim(rs, 2500).card.id == "Phi-4-mini-instruct"


async def test_waits_instead_of_piecemeal_eviction(cfg, cards, mock_pool_cls):
    """While a big worker is still busy, don't unload a small idle one that can't free enough anyway."""
    import asyncio
    cfg = {**cfg, "gpu": {**cfg["gpu"], "vram_budget_mb": 14500, "prefetch": False}}
    events = []

    async def emit(e):
        events.append(e)

    pool = mock_pool_cls(cfg, cards, emit=emit)
    pool.estimate_mb = lambda card, c, p: SIZES.get(card.id, 1000)
    try:
        await pool.ensure("Qwen3.5-4B", 4096, pin=True)
        for m in ("Ministral-3-3B-Instruct", "LFM2.5-2.6B", "Phi-4-mini-instruct"):
            await pool.ensure(m, 4096)
        pool.plan_ahead(["Granite-4.1-3B", "Qwen3.5-4B", "Ministral-3-3B-Instruct", "LFM2.5-2.6B", "Phi-4-mini-instruct"])

        async def ministral_busy():
            async with pool.use("Ministral-3-3B-Instruct", 4096):
                await asyncio.sleep(2)

        async def phi_busy():
            async with pool.use("Phi-4-mini-instruct", 4096):
                await asyncio.sleep(4)

        async def need_granite():
            await asyncio.sleep(0.2)  # LFM is idle, Ministral and Phi are busy
            async with pool.use("Granite-4.1-3B", 4096):
                pass

        await asyncio.gather(ministral_busy(), phi_busy(), need_granite())
        evicted = [e["model"] for e in events if e.get("event") == "unloaded"]
        assert evicted == ["Ministral-3-3B-Instruct"], evicted  # one eviction, not LFM + another
    finally:
        await pool.shutdown()


async def test_low_system_ram_evicts_an_idle_model(cfg, cards, mock_pool_cls, monkeypatch):
    """Free RAM below the reserve: loading another model first unloads an idle one."""
    from swarm import procs
    pool = mock_pool_cls(cfg, cards)
    pool.estimate_mb = lambda card, c, p: 1000
    ram = {"free": 8000}
    monkeypatch.setattr(procs, "system_ram_mb", lambda: (ram["free"], 16000))
    try:
        async with pool.use("LFM2.5-2.6B", 4096, 1):
            pass
        assert "LFM2.5-2.6B" in pool.running
        ram["free"] = 1500  # below min_free_ram_mb + ram_per_server_mb
        # once LFM is gone the (fake) RAM is fine again
        orig_stop = pool._stop

        async def stop(mid, reason):
            ram["free"] = 8000
            await orig_stop(mid, reason)
        pool._stop = stop
        async with pool.use("Phi-4-mini-instruct", 4096, 1):
            pass
        assert "LFM2.5-2.6B" not in pool.running and "Phi-4-mini-instruct" in pool.running
    finally:
        await pool.shutdown()


def test_model_servers_use_no_mmap_and_few_threads(cfg, cards, mock_pool_cls):
    pool = mock_pool_cls(cfg, cards)
    cmd = pool.build_cmd(cards["LFM2.5-2.6B"], 8200, 4096, 2) if hasattr(pool, "build_cmd") else []
    from swarm.pool import ModelPool
    cmd = ModelPool.build_cmd(pool, cards["LFM2.5-2.6B"], 8200, 4096, 2)
    assert "--no-mmap" in cmd and cmd[cmd.index("-t") + 1] == "2"


def test_system_ram_reading():
    from swarm import procs
    r = procs.system_ram_mb()
    assert r is None or (0 < r[0] <= r[1])


def test_big_models_run_alone_split_between_gpu_and_ram(cfg, cards, mock_pool_cls):
    import dataclasses
    from swarm.pool import ModelPool
    pool = mock_pool_cls({**cfg, "gpu": {**cfg["gpu"], "vram_budget_mb": 14500}}, cards)
    small = cards["LFM2.5-2.6B"]
    big = dataclasses.replace(small, id="Qwen3.6-35B-A3B", size_mb=25230)
    assert not pool.needs_offload(dataclasses.replace(small, size_mb=2000), 4096, 2)
    assert pool.needs_offload(big, 12288, 1)
    cmd = ModelPool.build_cmd(pool, big, 8200, 12288, 1, offload=True)
    assert "--fit" in cmd and "-ngl" not in cmd and "--no-mmap" not in cmd
    # listed in gpu.offload_no_mmap: the split model holds only its CPU part in RAM (J5, 2026-10-09)
    pool2 = mock_pool_cls({**cfg, "gpu": {**cfg["gpu"], "vram_budget_mb": 14500, "offload_no_mmap": ["Qwen3.6"]}}, cards)
    assert "--no-mmap" in ModelPool.build_cmd(pool2, big, 8200, 12288, 1, offload=True)


async def test_offload_model_unloads_everything_else(cfg, cards, mock_pool_cls):
    pool = mock_pool_cls({**cfg, "gpu": {**cfg["gpu"], "vram_budget_mb": 14500}}, cards)
    pool.estimate_mb = lambda card, c, p: 2000
    try:
        async with pool.use("LFM2.5-2.6B", 4096, 1):
            pass
        async with pool.use("Phi-4-mini-instruct", 4096, 1):
            pass
        pool.needs_offload = lambda card, c, p: card.id == "Qwen3.5-9B"
        async with pool.use("Qwen3.5-9B", 12288, 1, pin=True):
            assert list(pool.running) == ["Qwen3.5-9B"]
            assert not pool.running["Qwen3.5-9B"].pinned, "a big model is never pinned"
        async with pool.use("LFM2.5-2.6B", 4096, 1):
            assert "Qwen3.5-9B" not in pool.running
    finally:
        await pool.shutdown()


async def test_offload_model_never_gets_pinned_on_reuse(cfg, cards, mock_pool_cls):
    pool = mock_pool_cls({**cfg, "gpu": {**cfg["gpu"], "vram_budget_mb": 14500}}, cards)
    pool.estimate_mb = lambda card, c, p: 2000
    pool.needs_offload = lambda card, c, p: card.id == "Qwen3.5-9B"
    try:
        async with pool.use("Qwen3.5-9B", 12288, 1, pin=True):   # plan
            pass
        async with pool.use("Qwen3.5-9B", 12288, 1, pin=True):   # synthesis reuses the running server
            pass
        assert not pool.running["Qwen3.5-9B"].pinned
        async with pool.use("LFM2.5-2.6B", 4096, 1):
            assert "Qwen3.5-9B" not in pool.running
    finally:
        await pool.shutdown()


async def test_idle_pinned_coordinator_is_evicted_instead_of_waiting(cfg, cards, mock_pool_cls):
    """A big pinned coordinator that is idle must make room for a worker (bake-off 2: a worker waited
    15 minutes behind an 11 GB pinned Phi-4 coordinator and the question timed out)."""
    import time
    c = {**cfg, "gpu": {**cfg["gpu"], "vram_budget_mb": 14500, "prefetch": False, "pinned_evict_after_s": 2}}
    pool = mock_pool_cls(c, cards)
    sizes = {"Ministral-3-14B-Instruct": 11500, "LFM2.5-2.6B": 2130, "Ministral-3-3B-Instruct": 3400}
    pool.estimate_mb = lambda card, ctx, par: sizes.get(card.id, 1000)
    try:
        await pool.ensure("Ministral-3-14B-Instruct", 4096, 1, pin=True)   # coordinator, pinned, idle
        async with pool.use("LFM2.5-2.6B", 4096, 1):                       # a busy worker
            t0 = time.time()
            async with pool.use("Ministral-3-3B-Instruct", 4096, 1):       # needs room
                assert time.time() - t0 < 60
                assert "Ministral-3-14B-Instruct" not in pool.running
                assert pool.used_mb() <= 14500
    finally:
        await pool.shutdown()


def test_apriel_gets_plain_chat_template(cfg, cards, mock_pool_cls, tmp_path):
    from swarm import llm
    from swarm.registry import ModelCard
    card = ModelCard(id="Apriel-1.6-15B-Thinker", path="x.gguf", size_mb=8000, lab="ServiceNow", lineage="Apriel")
    args = mock_pool_cls(cfg, cards)._extra_for(card)
    i = args.index("--chat-template-file")
    assert args[i + 1].replace("\\", "/").endswith("config/templates/apriel.jinja")
    assert llm.strip_think("Here are my reasoning steps:\n1. x\n[BEGIN FINAL RESPONSE]\nParis.\n[END FINAL RESPONSE]<|end|>") == "Paris."


def test_ernie_gets_plain_chat_template(cfg, cards, mock_pool_cls, tmp_path):
    from swarm.registry import ModelCard
    pool = mock_pool_cls(cfg, cards)
    card = ModelCard(id="ERNIE-4.5-21B-A3B-Thinking", path="x.gguf", size_mb=12000, lab="Baidu", lineage="ERNIE")
    args = pool._extra_for(card)
    i = args.index("--chat-template-file")
    assert args[i + 1].replace("\\", "/").endswith("config/templates/ernie.jinja")


def test_preflight_catches_a_model_that_cannot_load(cfg, cards, mock_pool_cls, monkeypatch):
    import asyncio
    from swarm import preflight
    monkeypatch.setenv("MOCK_LLAMA_FAIL", "Phi-4-mini")
    said = []

    async def go():
        pool = mock_pool_cls(cfg, cards)
        try:
            bad = await preflight.preflight(["Qwen3.5-4B", "Phi-4-mini-instruct"], pool, cards, [], say=said.append)
            again = await preflight.preflight(["Qwen3.5-4B"], pool, cards, [], say=said.append)
            return bad, again
        finally:
            await pool.shutdown()
    bad, again = asyncio.run(go())
    assert list(bad) == ["Phi-4-mini-instruct"] and not again
    assert any("passed before" in s for s in said)          # a model that passed is not tested twice
    variant = cfg | {"workers": {**cfg["workers"], "team": ["Phi-4-mini-instruct", "LFM2.5-2.6B"]}}
    assert "Phi-4-mini-instruct" in preflight.models_for(variant, cards)


def test_command_r7b_gets_plain_chat_template(cfg, cards, mock_pool_cls):
    from swarm import llm
    from swarm.registry import ModelCard
    card = ModelCard(id="Command-R7B", path="x.gguf", size_mb=5800, lab="Cohere", lineage="Command")
    args = mock_pool_cls(cfg, cards)._extra_for(card)
    assert args[args.index("--chat-template-file") + 1].replace("\\", "/").endswith("config/templates/command-r7b.jinja")
    assert llm.strip_think("Paris.<|END_RESPONSE|>") == "Paris."


def test_cpu_models_take_no_vram_and_stay_loaded(cfg, cards, mock_pool_cls):
    from swarm import pool as poolmod
    c = dict(cfg)
    c["gpu"] = dict(cfg["gpu"], cpu_models=["LFM2.5"])
    p = mock_pool_cls(c, cards)
    lfm, phi = cards["LFM2.5-2.6B"], cards["Phi-4-mini-instruct"]
    assert p.on_cpu(lfm) and not p.on_cpu(phi)
    assert p.estimate_mb(lfm, 8192, 1) == 0 and p.estimate_mb(phi, 8192, 1) > 0
    cmd = poolmod.ModelPool.build_cmd(p, lfm, 8300, 8192, 1)
    assert cmd[cmd.index("-ngl") + 1] == "0" and "--no-mmap" not in cmd
    r = poolmod.Running(card=lfm, proc=None, port=1, ctx_per_slot=8192, parallel=1, est_mb=0, on_cpu=True)
    p.running[lfm.id] = r
    assert r.vram_mb == 0 and r not in p._evictable("Phi-4-mini-instruct", False)
    p.running.clear()


def test_cpu_models_are_started_without_the_gpu(cfg, cards, mock_pool_cls, monkeypatch):
    """A CPU-resident model gets CUDA hidden, so it never puts buffers on the card."""
    import asyncio
    from swarm import pool as poolmod
    seen = {}
    real = poolmod.procs.start

    def spy(cmd, log_path, cwd=None, env=None):
        seen[cmd[cmd.index("-m") + 1]] = env
        return real(cmd, log_path, cwd=cwd, env=env)
    monkeypatch.setattr(poolmod.procs, "start", spy)
    c = dict(cfg)
    c["gpu"] = dict(cfg["gpu"], cpu_models=["LFM2.5"])
    p = mock_pool_cls(c, cards)

    async def go():
        try:
            async with p.use("LFM2.5-2.6B", 4096):
                pass
            async with p.use("Phi-4-mini-instruct", 4096):
                pass
        finally:
            await p.shutdown()
    asyncio.run(go())
    assert seen[cards["LFM2.5-2.6B"].path]["CUDA_VISIBLE_DEVICES"] == "-1"
    assert seen[cards["Phi-4-mini-instruct"].path] is None


async def test_remote_model_is_used_by_address_not_started(cfg, cards, mock_pool_cls):
    """gpu.remote_models: a model served by another machine is never started or counted here; the
    pool hands out its address after a health check, and a model that only exists over there gets a
    card of its own. An unreachable machine gives a clear error."""
    from swarm import llm
    from swarm.pool import ModelLoadError
    other = mock_pool_cls(cfg, cards)          # stands in for the laptop: really runs a (mock) server
    here = mock_pool_cls(cfg, dict(cards))
    try:
        async with other.use("Phi-4-mini-instruct", 4096) as laptop_url:
            here.set_remote({"Phi-4-mini-instruct": {"url": laptop_url, "ctx_per_slot": 6144, "parallel": 2},
                             "Laptop-Only-Model": laptop_url})
            async with here.use("Phi-4-mini-instruct", 4096) as url:
                assert url == laptop_url.rstrip("/")
                res = await llm.chat(url, [{"role": "user", "content": "hello"}], max_tokens=20)
                assert res.text
            assert "Phi-4-mini-instruct" not in here.running and here.used_mb() == 0
            st = here.status()
            assert any(m.get("remote") == laptop_url.rstrip("/") for m in st["models"])
            assert "Laptop-Only-Model" in here.cards and here.cards["Laptop-Only-Model"].size_mb == 0
            async with here.use("Laptop-Only-Model", 4096) as url2:
                assert url2 == laptop_url.rstrip("/")
            await here.unload_all()                       # nothing to stop for remote models
            here.set_remote({"Granite-4.1-3B": "http://127.0.0.1:9"})  # nothing listens there
            with pytest.raises(ModelLoadError, match="isn't answering"):
                async with here.use("Granite-4.1-3B", 4096):
                    pass
            assert "Granite-4.1-3B" not in here.running   # it did not fall back to loading it here
    finally:
        await here.shutdown()
        await other.shutdown()
