"""Speed check for a model server on another machine (or this one).

    python -m swarm.nodecheck http://192.168.68.70:8090

Sends fact-check-sized prompts (about 500, 2,000 and 4,000 tokens) and reports, from llama-server's
own timings, how fast the server reads the prompt and writes the reply. Use it to judge whether a
network node is quick enough for its job before the swarm relies on it.
"""
from __future__ import annotations

import argparse
import sys
import time

import httpx

from swarm.paths import REPO

FILLER_FILES = ["README.md", "docs/Project-Brief.md", "docs/Model-Research-2026-10.md"]


def _filler() -> str:
    parts = []
    for f in FILLER_FILES:
        try:
            parts.append((REPO / f).read_text(encoding="utf-8", errors="replace"))
        except OSError:
            pass
    text = "\n".join(parts) or ("The swarm reads passages and checks claims against them. " * 400)
    return " ".join(text.split())


def build_prompt(tokens: int) -> list[dict]:
    """A verifier-style prompt: numbered passages, then claims to check (about 4 characters per token)."""
    text = _filler()
    want = tokens * 4
    while len(text) < want:
        text += " " + text
    body = text[:want]
    passages = "\n\n".join(f"[E{i + 1}] {body[j:j + 900]}" for i, j in enumerate(range(0, len(body), 900)))
    claims = ("1. The swarm checks claims against cited passages.  (cites E1)\n"
              "2. The project runs entirely on a cloud server.  (cites E2)")
    return [{"role": "system", "content": "You are a strict fact checker. For each numbered claim, say whether "
                                          "the cited passages support it, in one line each."},
            {"role": "user", "content": f"Passages:\n{passages}\n\nClaims to check:\n{claims}"}]


def run(url: str, sizes: list[int], max_tokens: int = 120) -> int:
    url = url.rstrip("/")
    try:
        h = httpx.get(url + "/health", timeout=8)
        print(f"{url}/health -> {h.status_code} {h.text.strip()[:60]}")
    except httpx.HTTPError as e:
        print(f"Can't reach {url}: {type(e).__name__}. Is the machine on and the server running?")
        return 1
    try:
        props = httpx.get(url + "/props", timeout=8).json()
        n_ctx = (props.get("default_generation_settings") or {}).get("n_ctx")
        model = str(props.get("model_path", "")).replace("\\", "/").split("/")[-1]
        print(f"model: {model or '?'}   context per request: {n_ctx or '?'}")
    except Exception:
        n_ctx = None
    print(f"\n{'prompt':>8} {'read tok/s':>11} {'write tok/s':>12} {'total s':>8}")
    worst = 0
    for size in sizes:
        if n_ctx and size + max_tokens > n_ctx:
            print(f"{size:>8}  skipped (bigger than the server's {n_ctx}-token context)")
            continue
        body = {"messages": build_prompt(size), "max_tokens": max_tokens, "temperature": 0.0,
                "cache_prompt": False}
        t0 = time.time()
        try:
            r = httpx.post(url + "/v1/chat/completions", json=body, timeout=600)
            r.raise_for_status()
            data = r.json()
        except Exception as e:
            print(f"{size:>8}  failed: {type(e).__name__}: {str(e)[:120]}")
            worst = 1
            continue
        secs = time.time() - t0
        t = data.get("timings") or {}
        n_prompt = t.get("prompt_n") or (data.get("usage") or {}).get("prompt_tokens") or size
        print(f"{n_prompt:>8} {t.get('prompt_per_second', 0):>11.0f} {t.get('predicted_per_second', 0):>12.1f} "
              f"{secs:>8.1f}")
    print("\nA typical fact-check reads about 1,500-3,500 tokens and writes about 100-300.")
    return worst


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m swarm.nodecheck")
    ap.add_argument("url", nargs="?", default="http://192.168.68.70:8090")
    ap.add_argument("--sizes", default="500,2000,4000", help="prompt sizes in tokens")
    a = ap.parse_args(argv)
    return run(a.url, [int(x) for x in a.sizes.split(",") if x.strip()])


if __name__ == "__main__":
    sys.exit(main())
