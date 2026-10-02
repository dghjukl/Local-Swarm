"""Research tools used by the swarm.

- Web search: DuckDuckGo web results AND DuckDuckGo News (news finds recent discoveries far
  better than plain web search).
- Page reading: the article text is extracted with trafilatura (a readability-style extractor,
  like MCP/web-fetch-mcp uses), which drops menus, "related stories" rails and footers;
  html2text is the fallback.
- Wikipedia via its public API; scholarly records via swarm/scholar.py.
- MCP/research-mcp can still be used as the search/fetch backend (research.backend: research-mcp).
"""
from __future__ import annotations

import asyncio
import contextlib
import html
import json
import os
import re
import sys
from dataclasses import dataclass

import httpx

from swarm.paths import LOGS, MCP

WIKI_API = "https://en.wikipedia.org/w/api.php"
# ddgs logs a WARNING whenever one of its engines (e.g. Yahoo News) returns a page it cannot
# parse; the search falls back to its other engines, so these are noise in the console
import logging as _logging
_logging.getLogger("ddgs").setLevel(_logging.ERROR)

UA = "LocalSwarm/0.1 (https://github.com/dghjukl/Local-Swarm; personal local research assistant)"


@dataclass
class Doc:
    url: str
    title: str
    text: str
    source: str          # "web" | "wikipedia"
    error: str = ""


class ResearchMCP:
    """A small pool of research-mcp stdio sessions."""

    name = "research-mcp"

    def __init__(self, copies: int = 3):
        self.copies = max(1, copies)
        self._stack: contextlib.AsyncExitStack | None = None
        self._free: asyncio.Queue | None = None
        self.error: str = ""

    async def start(self) -> None:
        from mcp import ClientSession, StdioServerParameters
        from mcp.client.stdio import get_default_environment, stdio_client

        server_dir = MCP / "research-mcp"
        env = get_default_environment()
        env.update({
            "PYTHONIOENCODING": "utf-8",
            "PYTHONNOUSERSITE": "1",
            "RESEARCH_MCP_FETCH_TIMEOUT": "12",
            "RESEARCH_MCP_LOG_LEVEL": "WARNING",
        })
        params = StdioServerParameters(command=sys.executable, args=["server.py"],
                                       cwd=str(server_dir), env=env)
        self._stack = contextlib.AsyncExitStack()
        self._free = asyncio.Queue()
        LOGS.mkdir(parents=True, exist_ok=True)
        # the server's own error output goes here, so start-up problems can be diagnosed
        errlog = self._stack.enter_context(open(LOGS / "research-mcp.log", "w", encoding="utf-8", errors="replace"))
        try:
            for _ in range(self.copies):
                read, write = await self._stack.enter_async_context(stdio_client(params, errlog=errlog))
                session = await self._stack.enter_async_context(ClientSession(read, write))
                await asyncio.wait_for(session.initialize(), 60)
                self._free.put_nowait(session)
        except BaseException as e:
            self.error = f"research-mcp failed to start: {type(e).__name__}: {e}"
            with contextlib.suppress(BaseException):
                await self._stack.aclose()
            self._stack = None
            raise RuntimeError(self.error) from e

    async def close(self) -> None:
        if self._stack:
            with contextlib.suppress(Exception):
                await self._stack.aclose()
            self._stack = None

    async def call(self, tool: str, args: dict, timeout: float = 40) -> dict:
        if self._free is None:
            raise RuntimeError("research-mcp not started")
        session = await self._free.get()
        try:
            result = await asyncio.wait_for(session.call_tool(tool, args), timeout)
        finally:
            self._free.put_nowait(session)
        sc = getattr(result, "structuredContent", None)
        if isinstance(sc, dict):
            return sc.get("result", sc) if set(sc) == {"result"} else sc
        for part in result.content or []:
            txt = getattr(part, "text", None)
            if txt:
                try:
                    return json.loads(txt)
                except json.JSONDecodeError:
                    return {"error": txt[:300]}
        return {"error": "empty tool result"}

    async def news(self, query: str, n: int = 4) -> list[dict]:
        return await news_search(query, n)

    async def search(self, query: str, n: int = 5) -> list[dict]:
        res = await self.call("research_search", {"query": query, "max_results": n})
        if "error" in res:
            raise RuntimeError(res["error"])
        return [{**r, "title": html.unescape(r.get("title", ""))} for r in res.get("results", []) if r.get("url")]

    async def fetch(self, url: str) -> Doc:
        try:
            res = await self.call("research_fetch", {"url": url, "max_words": 6000})
        except Exception as e:
            return Doc(url, "", "", "web", error=str(e))
        if "error" in res:
            return Doc(url, "", "", "web", error=str(res["error"]))
        return Doc(url, html.unescape(res.get("title") or url), res.get("content", ""), "web")


# Hard limits so one slow site can never stall a run (a FRAMES run sat for 6+ minutes on one question):
# every page download has an overall deadline and a size cap, and every search a deadline.
FETCH_DEADLINE = 20.0
EXTRACT_DEADLINE = 20.0
SEARCH_DEADLINE = 25.0
MAX_PAGE_BYTES = 3_000_000


async def _download(url: str) -> tuple[str, str]:
    """(content-type, text) of a page, reading at most MAX_PAGE_BYTES."""
    async with httpx.AsyncClient(timeout=12, follow_redirects=True, headers={"User-Agent": UA}) as c:
        async with c.stream("GET", url) as r:
            r.raise_for_status()
            ctype = r.headers.get("content-type", "")
            if "html" not in ctype and "text" not in ctype:
                return ctype, ""  # PDFs, images, video, archives: not read
            buf = bytearray()
            async for chunk in r.aiter_bytes():
                buf.extend(chunk)
                if len(buf) >= MAX_PAGE_BYTES:
                    break
            enc = r.encoding or "utf-8"
    return ctype, bytes(buf).decode(enc, errors="replace")[:500_000]


# Text extraction (trafilatura / lxml, native code) runs in a separate worker process: a page that
# crashes the parser then kills only that worker, not the whole overnight run (a FRAMES run died
# silently with no Python error, the signature of a native crash). The pool is rebuilt after a crash.
_extract_pool = None


def _pool():
    global _extract_pool
    if _extract_pool is None:
        from concurrent.futures import ProcessPoolExecutor
        _extract_pool = ProcessPoolExecutor(max_workers=2)
    return _extract_pool


async def extract_isolated(raw: str, url: str) -> str:
    global _extract_pool
    if os.environ.get("SWARM_EXTRACT_INPROCESS") == "1":  # tests
        return await asyncio.wait_for(asyncio.to_thread(extract_text, raw, url), EXTRACT_DEADLINE)
    loop = asyncio.get_running_loop()
    try:
        return await asyncio.wait_for(loop.run_in_executor(_pool(), extract_text, raw, url), EXTRACT_DEADLINE)
    except Exception as e:
        from concurrent.futures.process import BrokenProcessPool
        if isinstance(e, BrokenProcessPool) or isinstance(e, asyncio.TimeoutError):
            # the worker crashed or is stuck on this page: throw the pool away and start fresh
            old, _extract_pool = _extract_pool, None
            if old is not None:
                old.shutdown(wait=False, cancel_futures=True)
                for p in list(getattr(old, "_processes", {}).values()):
                    with contextlib.suppress(Exception):
                        p.kill()
        raise


async def _in_thread(fn, deadline: float = SEARCH_DEADLINE):
    return await asyncio.wait_for(asyncio.to_thread(fn), deadline)


class DirectResearch:
    """Built-in search + fetch (same interface as ResearchMCP), used when research-mcp can't start."""

    name = "built-in"

    async def search(self, query: str, n: int = 5) -> list[dict]:
        def run():
            from ddgs import DDGS
            return list(DDGS().text(query, max_results=n))
        hits = await _in_thread(run)
        return [{"title": html.unescape(h.get("title", "")), "url": h.get("href", ""), "snippet": h.get("body", "")}
                for h in hits if h.get("href")]

    async def news(self, query: str, n: int = 4) -> list[dict]:
        return await news_search(query, n)

    async def fetch(self, url: str) -> Doc:
        from urllib.parse import urlparse
        host = urlparse(url).hostname or ""
        if not url.startswith(("http://", "https://")) or await asyncio.to_thread(_is_private, host):
            return Doc(url, "", "", "web", error="blocked address")
        try:
            ctype, raw = await asyncio.wait_for(_download(url), FETCH_DEADLINE)
        except asyncio.TimeoutError:
            return Doc(url, "", "", "web", error=f"gave up after {FETCH_DEADLINE:.0f}s")
        except Exception as e:
            return Doc(url, "", "", "web", error=str(e)[:200])
        if "html" not in ctype:
            return Doc(url, url, raw if "text" in ctype else "", "web", error="" if "text" in ctype else "not text")
        m = re.search(r"<title[^>]*>(.*?)</title>", raw, re.S | re.I)
        title = html.unescape(m.group(1).strip() if m else url)[:200]
        try:  # a pathological page can keep the extractor busy for minutes: move on without it
            text = await extract_isolated(raw, url)
        except asyncio.TimeoutError:
            return Doc(url, title, "", "web", error=f"text extraction took over {EXTRACT_DEADLINE:.0f}s")
        except Exception as e:
            return Doc(url, title, "", "web", error=f"text extraction failed: {type(e).__name__}"[:200])
        return Doc(url, title, text, "web")

    async def close(self) -> None:
        pass


def extract_text(raw_html: str, url: str = "") -> str:
    """Main article text. trafilatura finds the article body and drops navigation, teaser rails
    and footers; if it finds nothing usable, fall back to converting the whole page."""
    try:
        import trafilatura
        txt = trafilatura.extract(raw_html, url=url or None, include_comments=False, include_tables=True,
                                  include_links=False, include_images=False, favor_recall=True)
        if txt and len(txt) > 400:
            return txt
    except Exception:
        pass
    import html2text
    h = html2text.HTML2Text()
    h.ignore_images = True
    h.ignore_links = True
    h.body_width = 0
    return h.handle(raw_html)


async def news_search(query: str, n: int = 4) -> list[dict]:
    """DuckDuckGo News: recent articles with dates."""
    def run():
        from ddgs import DDGS
        return list(DDGS().news(query, max_results=n))
    hits = await _in_thread(run)
    return [{"title": html.unescape(h.get("title", "")), "url": h.get("url") or h.get("href", ""),
             "snippet": h.get("body", ""), "date": h.get("date", ""), "publisher": h.get("source", "")}
            for h in hits if h.get("url") or h.get("href")]


def _is_private(host: str) -> bool:
    import ipaddress
    import socket
    if host in ("localhost", ""):
        return True
    try:
        for info in socket.getaddrinfo(host, None):
            ip = ipaddress.ip_address(info[4][0])
            if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved:
                return True
    except Exception:
        return False
    return False


async def wikipedia(query: str, n: int = 2) -> list[Doc]:
    """Search Wikipedia and return plain-text article extracts."""
    async with httpx.AsyncClient(timeout=15, headers={"User-Agent": UA}) as c:
        r = await c.get(WIKI_API, params={"action": "query", "list": "search", "srsearch": query,
                                          "srlimit": n, "format": "json"})
        r.raise_for_status()
        titles = [h["title"] for h in r.json().get("query", {}).get("search", [])]
        if not titles:
            return []
        # Full-text extracts come back one page per request.
        async def one(title: str) -> Doc | None:
            r = await c.get(WIKI_API, params={"action": "query", "prop": "extracts", "explaintext": 1,
                                              "titles": title, "format": "json", "redirects": 1})
            r.raise_for_status()
            for p in r.json().get("query", {}).get("pages", {}).values():
                if p.get("extract"):
                    t = p.get("title", title)
                    return Doc("https://en.wikipedia.org/wiki/" + t.replace(" ", "_"),
                               f"{t} - Wikipedia", p["extract"], "wikipedia")
            return None

        docs = await asyncio.gather(*(one(t) for t in titles), return_exceptions=True)
        return [d for d in docs if isinstance(d, Doc)]


def research_mcp_available(cfg: dict | None = None) -> bool:
    """research-mcp is used only when the config asks for it (research.backend: research-mcp);
    the built-in backend has news search and better article extraction."""
    if cfg is not None and (cfg.get("research") or {}).get("backend", "builtin") != "research-mcp":
        return False
    return (MCP / "research-mcp" / "server.py").exists() and os.environ.get("SWARM_NO_WEB") != "1"
