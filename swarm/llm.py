"""Minimal async client for llama-server's OpenAI-compatible chat endpoint."""
from __future__ import annotations

import contextvars
import json
import re
import time
from dataclasses import dataclass, field
from typing import Awaitable, Callable

import httpx


@dataclass
class ChatResult:
    text: str
    reasoning: str = ""
    seconds: float = 0.0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    tokens_per_second: float = 0.0
    data: dict | list | None = None     # parsed JSON when a schema was requested
    raw: dict = field(default_factory=dict)


# Compute accounting: every chat() call inside a run adds its token counts here (the dict is shared
# with every task the run starts), so a whole swarm run and a single model can be compared by the
# total amount of text read (prompt) and written (completion).
_usage: contextvars.ContextVar[dict | None] = contextvars.ContextVar("swarm_usage", default=None)


def start_usage() -> dict:
    u = {"calls": 0, "prompt_tokens": 0, "completion_tokens": 0}
    _usage.set(u)
    return u


def usage_snapshot() -> dict | None:
    u = _usage.get()
    if u is None:
        return None
    return dict(u)


def _count(base_url: str, prompt: int, completion: int) -> None:
    u = _usage.get()
    if u is None:
        return
    u["calls"] += 1
    u["prompt_tokens"] += prompt
    u["completion_tokens"] += completion


class LLMError(RuntimeError):
    pass


class NoJSON(ValueError):
    """The reply had no parseable JSON; .text is the reply."""
    def __init__(self, msg: str, text: str = ""):
        super().__init__(msg)
        self.text = text


class BudgetExhausted(LLMError):
    """The run's token or time budget has no room left for this (non-final) call."""


# Normalized-budget runs: a hard ceiling on the tokens a whole run may WRITE and on its wall time,
# so different architectures can be compared on the same compute. Every call except the final
# answer is capped to what is left minus a reserve that is kept for the final answer; calls that
# start in parallel reserve their share up front, so together they can never overshoot.
_budget: contextvars.ContextVar[dict | None] = contextvars.ContextVar("swarm_budget", default=None)


def start_budget(max_output_tokens: int | None = None, max_seconds: float | None = None,
                 reserve_tokens: int = 900, reserve_seconds: float = 45.0) -> dict | None:
    if not max_output_tokens and not max_seconds:
        _budget.set(None)
        return None
    b = {"max_output_tokens": int(max_output_tokens) if max_output_tokens else None,
         "max_seconds": float(max_seconds) if max_seconds else None,
         "reserve_tokens": int(reserve_tokens), "reserve_seconds": float(reserve_seconds),
         "t0": time.time(), "used": 0, "committed": 0, "skipped_calls": 0, "capped_calls": 0}
    _budget.set(b)
    return b


def budget_snapshot() -> dict | None:
    b = _budget.get()
    if b is None:
        return None
    return {k: b[k] for k in ("max_output_tokens", "max_seconds", "used", "skipped_calls", "capped_calls")} | {
        "seconds": round(time.time() - b["t0"], 1)}


def _budget_take(max_tokens: int, timeout: float, final: bool) -> tuple[int, float, int]:
    """(max_tokens, timeout, tokens reserved) for a call under the current budget, or raise."""
    b = _budget.get()
    if b is None:
        return max_tokens, timeout, 0
    tok, tmo = max_tokens, timeout
    if b["max_output_tokens"]:
        left = b["max_output_tokens"] - b["used"] - b["committed"] - (0 if final else b["reserve_tokens"])
        if not final and left < 64:
            b["skipped_calls"] += 1
            raise BudgetExhausted(f"token budget used up ({b['used']}/{b['max_output_tokens']})")
        tok = max(1, min(max_tokens, left)) if not final else max(64, min(max_tokens, left))
    if b["max_seconds"]:
        left_s = b["max_seconds"] - (time.time() - b["t0"]) - (0 if final else b["reserve_seconds"])
        if not final and left_s < 5:
            b["skipped_calls"] += 1
            raise BudgetExhausted(f"time budget used up ({time.time() - b['t0']:.0f}/{b['max_seconds']:.0f}s)")
        tmo = min(timeout, max(left_s, 20.0 if final else 5.0))
    if tok < max_tokens:
        b["capped_calls"] += 1
    b["committed"] += tok
    return tok, tmo, tok


def _budget_release(reserved: int, completion_tokens: int) -> None:
    b = _budget.get()
    if b is not None:
        b["committed"] -= reserved
        b["used"] += completion_tokens


# servers (base URLs) running a model whose chat template always opens a thinking block
FORCED_THINKING: set[str] = set()
# servers running a model whose template ignores enable_thinking and is switched off by writing
# "/no_think" in the system message instead (NVIDIA Nemotron Nano v2)
NO_THINK_SWITCH: set[str] = set()
# extra stop strings per server, for models whose end-of-turn token is not marked as one in the
# GGUF (Command R7B writes <|END_OF_TURN_TOKEN|> as text, which the server's parser rejects)
STOP_WORDS: dict[str, list[str]] = {}


def _no_think(messages: list[dict]) -> list[dict]:
    out = [dict(m) for m in messages]
    if out and out[0].get("role") == "system" and isinstance(out[0].get("content"), str):
        out[0]["content"] = out[0]["content"].rstrip() + " /no_think"
    else:
        out.insert(0, {"role": "system", "content": "/no_think"})
    return out

_THINK_RE = re.compile(r"<think>.*?</think>", re.S | re.I)


def strip_think(text: str) -> str:
    text = _THINK_RE.sub("", text or "")
    if "</think>" in text:           # opening tag was in the prompt
        text = text.split("</think>", 1)[1]
    if "[BEGIN FINAL RESPONSE]" in text:  # Apriel: reasoning steps, then the answer between markers
        text = text.split("[BEGIN FINAL RESPONSE]", 1)[1]
    text = text.replace("[END FINAL RESPONSE]", "").replace("<|end|>", "")
    text = text.replace("<|START_RESPONSE|>", "").replace("<|END_RESPONSE|>", "")  # Cohere Command
    m = re.search(r"<response>\s*(.*?)\s*(?:</response>|$)", text, re.S)  # ERNIE wraps its answer
    if m:
        text = m.group(1)
    return text.strip()


def extract_json(text: str):
    """Best-effort JSON extraction for when a model wraps output in prose/fences."""
    text = strip_think(text)
    fence = re.search(r"```(?:json)?\s*(.*?)```", text, re.S)
    if fence:
        text = fence.group(1)
    for opener, closer in (("{", "}"), ("[", "]")):
        a, b = text.find(opener), text.rfind(closer)
        if a != -1 and b > a:
            try:
                return json.loads(text[a:b + 1])
            except json.JSONDecodeError:
                continue
    raise ValueError("no JSON found")


async def chat(
    base_url: str,
    messages: list[dict],
    *,
    max_tokens: int = 800,
    temperature: float = 0.3,
    schema: dict | None = None,
    think: bool = False,
    grammar: bool = True,
    on_delta: Callable[[str], Awaitable[None]] | None = None,
    timeout: float = 300,
    final: bool = False,
    gbnf: str | None = None,
) -> ChatResult:
    """final=True marks the call that writes the answer the user gets: under a budget it may use
    the reserve that other calls must leave free."""
    if not think and base_url.rstrip("/") in NO_THINK_SWITCH:
        messages = _no_think(messages)
    if base_url.rstrip("/") in FORCED_THINKING:  # always thinks first: no grammar, room to think
        grammar = False
        max_tokens = max(max_tokens, min(6000, max_tokens * 4))
        if schema is not None:  # without a grammar the format has to be asked for in words
            messages = json_request(messages, schema)
    max_tokens, timeout, reserved = _budget_take(max_tokens, timeout, final)
    try:
        res = await _chat(base_url, messages, max_tokens=max_tokens, temperature=temperature, schema=schema,
                          think=think, grammar=grammar and not gbnf, on_delta=on_delta, timeout=timeout,
                          gbnf=gbnf)
    except BaseException:
        _budget_release(reserved, 0)
        raise
    _budget_release(reserved, res.completion_tokens)
    if schema is not None:
        try:
            res.data = json.loads(res.text)
        except json.JSONDecodeError:
            try:
                res.data = extract_json(res.text)
            except ValueError:
                try:  # some templates route everything into reasoning_content
                    res.data = extract_json(res.reasoning)
                except ValueError:
                    finish = ""
                    if res.raw.get("choices"):
                        finish = res.raw["choices"][0].get("finish_reason") or ""
                    raise NoJSON(
                        f"no JSON in reply (finish={finish or '?'}, {res.completion_tokens} tokens, "
                        f"{len(res.reasoning)} chars of reasoning): text={res.text[:120]!r} "
                        f"reasoning={res.reasoning[:160]!r}", res.text)
    if schema is not None and schema.get("type") == "object" and not isinstance(res.data, dict):
        # e.g. a model that wrote a JSON list of the fields: unwrap a single object, else retry
        if isinstance(res.data, list) and len(res.data) == 1 and isinstance(res.data[0], dict):
            res.data = res.data[0]
        else:
            raise NoJSON(f"reply was JSON but not an object: {res.text[:120]!r}", res.text)
    return res


async def _chat(base_url, messages, *, max_tokens, temperature, schema, think, grammar, on_delta, timeout,
                gbnf=None) -> ChatResult:
    payload: dict = {
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": temperature,
        # enable_thinking: Qwen-style templates; reasoning_effort: gpt-oss (harmony) templates
        "chat_template_kwargs": {"enable_thinking": think, "reasoning_effort": "medium" if think else "low"},
        "cache_prompt": True,
    }
    if gbnf:  # a plain grammar instead of the template's (which may allow a thinking block first)
        payload["grammar"] = gbnf
    if STOP_WORDS.get(base_url.rstrip("/")):
        payload["stop"] = list(STOP_WORDS[base_url.rstrip("/")])
    # grammar=False: still parse JSON from the reply, but don't constrain decoding (a grammar can
    # stop a thinking model from writing its thoughts first)
    if schema is not None and grammar:
        payload["response_format"] = {"type": "json_schema", "json_schema": {"name": "output", "schema": schema}}
    t0 = time.time()
    url = base_url.rstrip("/") + "/v1/chat/completions"
    async with httpx.AsyncClient(timeout=httpx.Timeout(timeout, connect=10)) as c:
        if on_delta is None:
            try:
                resp = await c.post(url, json=payload)
            except httpx.HTTPError as e:
                raise LLMError(f"request to {base_url} failed: {e}") from e
            if resp.status_code != 200:
                raise LLMError(f"{resp.status_code}: {resp.text[:400]}")
            data = resp.json()
            msg = data["choices"][0]["message"]
            text = msg.get("content") or ""
            reasoning = msg.get("reasoning_content") or ""
            usage = data.get("usage", {})
            timings = data.get("timings", {})
        else:
            payload["stream"] = True
            text, reasoning, usage, timings, data = "", "", {}, {}, {}
            try:
                async with c.stream("POST", url, json=payload) as resp:
                    if resp.status_code != 200:
                        body = await resp.aread()
                        raise LLMError(f"{resp.status_code}: {body[:400]!r}")
                    async for line in resp.aiter_lines():
                        if not line.startswith("data:"):
                            continue
                        chunk = line[5:].strip()
                        if chunk == "[DONE]":
                            break
                        try:
                            ev = json.loads(chunk)
                        except json.JSONDecodeError:
                            continue
                        if ev.get("timings"):
                            timings = ev["timings"]
                        if ev.get("usage"):
                            usage = ev["usage"]
                        for ch in ev.get("choices", []):
                            d = ch.get("delta", {})
                            if d.get("reasoning_content"):
                                reasoning += d["reasoning_content"]
                            if d.get("content"):
                                text += d["content"]
                                await on_delta(d["content"])
            except httpx.HTTPError as e:
                raise LLMError(f"stream from {base_url} failed: {e}") from e
    res = ChatResult(
        text=strip_think(text),
        reasoning=reasoning,
        seconds=time.time() - t0,
        prompt_tokens=int(usage.get("prompt_tokens", timings.get("prompt_n", 0)) or 0),
        completion_tokens=int(usage.get("completion_tokens", timings.get("predicted_n", 0)) or 0),
        tokens_per_second=float(timings.get("predicted_per_second", 0) or 0),
        raw=data if isinstance(data, dict) else {},
    )
    _count(base_url, res.prompt_tokens, res.completion_tokens)
    return res


def json_request(messages: list[dict], schema: dict) -> list[dict]:
    """The messages with an explicit request for one JSON object appended to the last user turn
    (for models that cannot be held to a schema by a grammar)."""
    note = ("\n\nWhen you have finished thinking, give your final answer as ONE JSON object that follows "
            "this JSON schema, with no markdown, headings or other text around it:\n"
            + json.dumps(schema, separators=(",", ":")))
    out = [dict(m) for m in messages]
    for m in reversed(out):
        if m.get("role") == "user" and isinstance(m.get("content"), str):
            m["content"] += note
            break
    return out


async def chat_json(base_url: str, messages: list[dict], schema: dict, *, retries: int = 1, **kw) -> ChatResult:
    """chat() with a JSON schema; retries once at temperature 0 if parsing fails. A model that
    cannot be held to the schema by a grammar is instead shown its reply and asked to rewrite it
    as the JSON object."""
    last: Exception | None = None
    temperature = kw.pop("temperature", 0.2)
    max_tokens = kw.pop("max_tokens", 800)
    msgs = messages
    for attempt in range(retries + 1):
        try:
            return await chat(base_url, msgs, schema=schema, temperature=temperature,
                              max_tokens=max_tokens, **kw)
        except (ValueError, KeyError) as e:
            last = e
            temperature, max_tokens = 0.0, int(max_tokens * 1.5)  # retry: deterministic, more room
            if isinstance(e, NoJSON) and e.text and base_url.rstrip("/") in FORCED_THINKING:
                msgs = messages + [{"role": "assistant", "content": e.text[:6000]},
                                   {"role": "user", "content": "Rewrite your answer above as the JSON object only."}]
    raise LLMError(f"model did not return valid JSON: {last}")
