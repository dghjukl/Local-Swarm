"""
server.py — FastMCP server for research-mcp.

6 tools providing structured web research primitives.

Rebuilt from local-deep-research (archived 2026-05-29).
What was kept: iterative search strategy patterns, structured result formats.
What was stripped: LangGraph, LiteLLM, internal LLM calls, own vector database.

Design principle: The MCP runtime model does synthesis. research-mcp provides
the structured fetch-and-combine primitives the model uses to gather information.
No autonomous research loops — the model drives the process step by step.

Search backend: Brave Search API (RESEARCH_MCP_BRAVE_API_KEY) with automatic
               DuckDuckGo fallback when no key is configured.

Stateless — no session state, no database.

Port: 8137 (SSE) / stdio (default)
"""

from __future__ import annotations

import ipaddress
import logging
import re
import socket
from typing import Optional
from urllib.parse import urljoin, urlparse

import httpx
from mcp.server.fastmcp import FastMCP

from config import settings

# ── Optional deps ─────────────────────────────────────────────────────────────

try:
    import html2text as _html2text
    _HTML2TEXT_AVAILABLE = True
except ImportError:
    _html2text = None
    _HTML2TEXT_AVAILABLE = False

try:
    from ddgs import DDGS  # current package name
    _DDG_AVAILABLE = True
except ImportError:
    try:
        from duckduckgo_search import DDGS  # legacy package name
        _DDG_AVAILABLE = True
    except ImportError:
        DDGS = None
        _DDG_AVAILABLE = False

# ── Bootstrap ─────────────────────────────────────────────────────────────────

logging.basicConfig(level=settings.numeric_log_level)
logger = logging.getLogger(__name__)

mcp = FastMCP(
    "research-mcp",
    instructions=(
        "Research MCP for MCP runtime. Provides web search and URL fetch primitives "
        "for structured iterative research. The model synthesizes; this MCP gathers. "
        "Search: Brave API (preferred) or DuckDuckGo (fallback). "
        "Fetch: httpx with HTML-to-markdown conversion."
    ),
)

# ── SSRF protection ───────────────────────────────────────────────────────────

_PRIVATE_NETS = [
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("169.254.0.0/16"),
    ipaddress.ip_network("::1/128"),
    ipaddress.ip_network("fc00::/7"),
]


def _is_private_host(host: str) -> bool:
    """Return True if host resolves to a private/loopback IP."""
    if not settings.block_private_ips:
        return False
    try:
        addr = socket.getaddrinfo(host, None, proto=socket.IPPROTO_TCP)
        for (_, _, _, _, sockaddr) in addr:
            ip = ipaddress.ip_address(sockaddr[0])
            if any(ip in net for net in _PRIVATE_NETS):
                return True
    except Exception:
        pass
    return False


def _validate_url(url: str) -> Optional[str]:
    """Return error message if URL is unsafe, else None."""
    try:
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https"):
            return f"Only http/https URLs are supported, got: {parsed.scheme!r}"
        if not parsed.netloc:
            return "URL must include a hostname"
        if _is_private_host(parsed.hostname or ""):
            return f"Fetch to private/loopback address blocked: {url}"
    except Exception as exc:
        return f"Invalid URL: {exc}"
    return None


# ── HTML → text conversion ────────────────────────────────────────────────────

def _html_to_text(html: str, base_url: str = "") -> str:
    """Convert HTML to clean plain text / markdown."""
    if _HTML2TEXT_AVAILABLE:
        h = _html2text.HTML2Text()
        h.ignore_links = False
        h.ignore_images = True
        h.ignore_emphasis = False
        h.body_width = 0  # no line-wrap
        h.baseurl = base_url
        return h.handle(html)
    # Fallback: strip tags
    text = re.sub(r"<[^>]+>", " ", html)
    text = re.sub(r"\s{2,}", " ", text)
    return text.strip()


def _extract_title(html: str) -> str:
    """Extract page title from HTML."""
    m = re.search(r"<title[^>]*>([^<]*)</title>", html, re.IGNORECASE)
    if m:
        return m.group(1).strip()
    m = re.search(r"<h1[^>]*>([^<]*)</h1>", html, re.IGNORECASE)
    if m:
        return re.sub(r"<[^>]+>", "", m.group(1)).strip()
    return ""


# ── Research planning helpers ─────────────────────────────────────────────────

def _decompose_query(query: str) -> list[str]:
    """Heuristic decomposition of a research query into sub-questions."""
    q = query.strip().rstrip("?")
    sub_questions = [
        f"What is {q}?",
        f"What are the key aspects or components of {q}?",
        f"What is the current state or recent developments in {q}?",
        f"What are the main challenges or controversies around {q}?",
        f"What do experts say about {q}?",
    ]
    # For shorter/simpler queries, return fewer
    if len(query.split()) <= 4:
        return sub_questions[:3]
    return sub_questions


def _extract_search_terms(query: str) -> list[str]:
    """Extract search term variants from a query."""
    base = query.strip()
    terms = [base]
    # Add quoted variant for exact phrase
    if " " in base and '"' not in base:
        terms.append(f'"{base}"')
    # Add site-specific variants if it looks like a technical topic
    lower = base.lower()
    if any(w in lower for w in ["how", "why", "what is", "explain"]):
        terms.append(f"{base} explained")
        terms.append(f"{base} overview")
    else:
        terms.append(f"{base} research")
        terms.append(f"{base} analysis")
    return terms[:4]


def _depth_settings(depth: str) -> dict:
    """Return iteration guidance for the given depth."""
    return {
        "quick": {"iterations": 2, "sources_per_iter": 3, "note": "2 search rounds, 3 sources each. Good for well-known topics."},
        "standard": {"iterations": 3, "sources_per_iter": 5, "note": "3 search rounds, 5 sources each. Default for most research."},
        "deep": {"iterations": 5, "sources_per_iter": 8, "note": "5 search rounds, up to 8 sources each. For complex or niche topics."},
    }.get(depth, {"iterations": 3, "sources_per_iter": 5, "note": "Standard depth."})


# ── Tools ─────────────────────────────────────────────────────────────────────

@mcp.tool()
def research_status() -> dict:
    """Return operational status for research-mcp."""
    return {
        "status": "ok",
        "mcp": "research-mcp",
        "port": settings.port,
        "transport": settings.transport,
        "search_backend": "brave" if settings.brave_configured else "duckduckgo",
        "brave_configured": settings.brave_configured,
        "ddg_available": _DDG_AVAILABLE,
        "html2text_available": _HTML2TEXT_AVAILABLE,
        "fetch_timeout": settings.fetch_timeout,
        "stateless": True,
        "design_note": (
            "The MCP runtime model synthesizes; research-mcp gathers. "
            "No autonomous research loops — model drives step by step."
        ),
    }


@mcp.tool()
def research_search(
    query: str,
    max_results: int = 10,
    region: Optional[str] = None,
) -> dict:
    """
    Search the web and return structured results.

    Uses Brave Search API when RESEARCH_MCP_BRAVE_API_KEY is configured.
    Falls back to DuckDuckGo (free, no key required) otherwise.

    Args:
        query: Search query.
        max_results: Number of results to return (1–20). Default: 10.
        region: Region code for Brave Search (e.g. "us", "gb"). Ignored for DDG.

    Returns:
        List of results with title, url, snippet, and source.
    """
    if not query.strip():
        return {"error": "query cannot be empty"}
    max_results = max(1, min(20, max_results))

    # ── Brave Search ──────────────────────────────────────────────────────────
    if settings.brave_configured:
        try:
            params: dict = {"q": query, "count": max_results}
            if region:
                params["country"] = region
            resp = httpx.get(
                "https://api.search.brave.com/res/v1/web/search",
                headers={
                    "Accept": "application/json",
                    "Accept-Encoding": "gzip",
                    "X-Subscription-Token": settings.brave_api_key,
                },
                params=params,
                timeout=10.0,
            )
            resp.raise_for_status()
            data = resp.json()
            results = []
            for item in data.get("web", {}).get("results", [])[:max_results]:
                results.append({
                    "title": item.get("title", ""),
                    "url": item.get("url", ""),
                    "snippet": item.get("description", ""),
                    "published_date": item.get("page_age", ""),
                    "source": "brave",
                })
            return {
                "query": query,
                "results": results,
                "count": len(results),
                "backend": "brave",
            }
        except Exception as exc:
            logger.warning("Brave search failed (%s), falling back to DDG", exc)

    # ── DuckDuckGo fallback ───────────────────────────────────────────────────
    if _DDG_AVAILABLE:
        try:
            results = []
            with DDGS() as ddgs:
                for item in ddgs.text(query, max_results=max_results):
                    results.append({
                        "title": item.get("title", ""),
                        "url": item.get("href", ""),
                        "snippet": item.get("body", ""),
                        "published_date": "",
                        "source": "duckduckgo",
                    })
            return {
                "query": query,
                "results": results,
                "count": len(results),
                "backend": "duckduckgo",
            }
        except Exception as exc:
            return {"error": f"DuckDuckGo search failed: {exc}", "query": query}

    return {
        "error": (
            "No search backend available. Set RESEARCH_MCP_BRAVE_API_KEY "
            "or install duckduckgo_search (pip install duckduckgo_search)."
        ),
        "query": query,
    }


@mcp.tool()
def research_fetch(
    url: str,
    max_words: Optional[int] = None,
) -> dict:
    """
    Fetch a URL and return its content as clean text.

    HTML is converted to markdown-style plain text using html2text.
    Non-HTML responses (JSON, plain text) are returned as-is.
    Private/loopback addresses are blocked.

    Args:
        url: The URL to fetch. Must be http or https.
        max_words: Truncate output to this many words. Default: no limit.

    Returns:
        Cleaned text content, title, word count, and content type.
    """
    url_err = _validate_url(url)
    if url_err:
        return {"error": url_err, "url": url}

    try:
        resp = httpx.get(
            url,
            headers={"User-Agent": settings.user_agent},
            timeout=settings.fetch_timeout,
            follow_redirects=True,
        )
        resp.raise_for_status()
    except httpx.TimeoutException:
        return {"error": f"Request timed out after {settings.fetch_timeout}s", "url": url}
    except httpx.HTTPStatusError as exc:
        return {"error": f"HTTP {exc.response.status_code}: {exc.response.reason_phrase}", "url": url}
    except Exception as exc:
        return {"error": str(exc), "url": url}

    content_type = resp.headers.get("content-type", "").split(";")[0].strip().lower()
    raw = resp.content[:settings.max_fetch_bytes]

    if "html" in content_type:
        html_str = raw.decode("utf-8", errors="replace")
        title = _extract_title(html_str)
        text = _html_to_text(html_str, base_url=url)
    elif "json" in content_type:
        text = raw.decode("utf-8", errors="replace")
        title = ""
    else:
        text = raw.decode("utf-8", errors="replace")
        title = ""

    # Word count and optional truncation
    words = text.split()
    word_count = len(words)
    truncated = False
    if max_words and word_count > max_words:
        text = " ".join(words[:max_words]) + "\n\n[... truncated]"
        truncated = True

    return {
        "url": url,
        "title": title,
        "content_type": content_type,
        "word_count": word_count,
        "truncated": truncated,
        "content": text,
    }


@mcp.tool()
def research_extract(
    content: str,
    url: str = "",
) -> dict:
    """
    Extract structural information from fetched content.

    Identifies sections (by headings), links mentioned in the content,
    and key statistics (word count, section count). Does NOT interpret
    the content — the model does that. This tool structures the raw data.

    Args:
        content: Text content returned by research_fetch.
        url: Source URL (used to resolve relative links). Optional.

    Returns:
        Sections, links found, word count, and a summary preview.
    """
    if not content.strip():
        return {"error": "content cannot be empty"}

    lines = content.splitlines()

    # Extract markdown-style headings
    sections = []
    current_heading = "(introduction)"
    current_body: list[str] = []
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("#"):
            if current_body:
                sections.append({
                    "heading": current_heading,
                    "word_count": len(" ".join(current_body).split()),
                    "preview": " ".join(current_body)[:200].strip(),
                })
            current_heading = stripped.lstrip("#").strip()
            current_body = []
        elif stripped:
            current_body.append(stripped)
    if current_body:
        sections.append({
            "heading": current_heading,
            "word_count": len(" ".join(current_body).split()),
            "preview": " ".join(current_body)[:200].strip(),
        })

    # Extract URLs from content
    url_pattern = re.compile(r"https?://[^\s\)\]\,\"\']+")
    found_urls = list(dict.fromkeys(url_pattern.findall(content)))[:20]

    # Summary preview (first ~300 words)
    all_words = content.split()
    word_count = len(all_words)
    preview = " ".join(all_words[:300]) + ("..." if word_count > 300 else "")

    return {
        "source_url": url,
        "word_count": word_count,
        "section_count": len(sections),
        "sections": sections,
        "links_found": found_urls,
        "link_count": len(found_urls),
        "preview": preview,
    }


@mcp.tool()
def research_plan(
    query: str,
    depth: str = "standard",
    context: Optional[str] = None,
) -> dict:
    """
    Decompose a research question into a structured research plan.

    Call this before starting iterative research. Returns sub-questions,
    search term variants, and guidance on how many iterations to run.

    Depth options: "quick" (2 rounds), "standard" (3 rounds), "deep" (5 rounds).

    Args:
        query: The research question or topic.
        depth: Research depth — "quick", "standard", or "deep". Default: "standard".
        context: Additional context about what is already known. Optional.

    Returns:
        Sub-questions, search terms, depth guidance, and iteration plan.
    """
    if not query.strip():
        return {"error": "query cannot be empty"}
    if depth not in ("quick", "standard", "deep"):
        return {"error": "depth must be 'quick', 'standard', or 'deep'"}

    sub_questions = _decompose_query(query)
    search_terms = _extract_search_terms(query)
    depth_info = _depth_settings(depth)

    return {
        "query": query,
        "depth": depth,
        "sub_questions": sub_questions,
        "suggested_search_terms": search_terms,
        "iterations_recommended": depth_info["iterations"],
        "sources_per_iteration": depth_info["sources_per_iter"],
        "depth_note": depth_info["note"],
        "research_sequence": [
            "1. Search with primary terms → review results, note key sources",
            "2. Fetch 2-3 most relevant pages → extract key facts",
            "3. Call research_iterate to identify gaps → search those next",
            f"4. Repeat for {depth_info['iterations']} total rounds",
            "5. Synthesize gathered facts into a response",
        ],
        "context_noted": bool(context),
        "search_tips": [
            "Start broad, then narrow: first search the topic generally, then drill into sub-questions.",
            "Prioritize authoritative sources: academic papers, official docs, well-known news sites.",
            "Use research_fetch on the most promising URLs from search results.",
            "Use research_extract to quickly scan large pages without reading every word.",
        ],
    }


@mcp.tool()
def research_iterate(
    query: str,
    findings_summary: str,
    iteration: int,
    max_iterations: int = 3,
) -> dict:
    """
    Given current research findings, suggest what to search next.

    Call this after each research round to decide whether to continue and
    what gaps remain. Provides structured guidance for the next iteration.

    Args:
        query: Original research question.
        findings_summary: Summary of what has been found so far (free text).
        iteration: Which iteration just completed (1-based).
        max_iterations: Maximum iterations planned. Default: 3.

    Returns:
        Coverage assessment, identified gaps, next search suggestions,
        and whether to continue researching.
    """
    if not query.strip():
        return {"error": "query cannot be empty"}
    if not findings_summary.strip():
        return {"error": "findings_summary cannot be empty"}
    if iteration < 1:
        return {"error": "iteration must be >= 1"}

    should_continue = iteration < max_iterations

    # Gap identification — heuristic based on findings summary length and content
    summary_lower = findings_summary.lower()
    gaps = []
    if "unknown" in summary_lower or "unclear" in summary_lower:
        gaps.append("Some aspects remain unclear — target them directly in the next search.")
    if "disagree" in summary_lower or "conflicting" in summary_lower or "controversy" in summary_lower:
        gaps.append("Conflicting information found — search for authoritative sources to resolve.")
    if iteration == 1:
        gaps.append("Initial overview gathered — now search for specific details and sub-topics.")
        gaps.append("Look for expert opinions, recent developments, and primary sources.")
    elif iteration == 2:
        gaps.append("Core information gathered — check for counterarguments or alternative perspectives.")
        gaps.append("Verify key claims against multiple independent sources.")
    if not gaps:
        gaps.append("Coverage appears adequate. Consider verifying the most important claims.")

    # Next search suggestions
    next_searches = _extract_search_terms(query)
    if iteration == 1:
        next_searches = [f"{query} expert opinion", f"{query} research findings", f"{query} examples"]
    elif iteration == 2:
        next_searches = [f"{query} criticism", f"{query} alternatives", f"{query} latest developments"]
    elif iteration >= 3:
        next_searches = [f"{query} primary sources", f"{query} data statistics"]

    return {
        "query": query,
        "iteration_completed": iteration,
        "max_iterations": max_iterations,
        "should_continue": should_continue,
        "progress": f"{iteration}/{max_iterations} iterations complete",
        "coverage_assessment": (
            "Early stage — focus on breadth." if iteration == 1
            else "Mid-stage — deepen on key aspects." if iteration < max_iterations - 1
            else "Near complete — verify and fill remaining gaps."
        ),
        "gaps_identified": gaps,
        "next_search_suggestions": next_searches if should_continue else [],
        "termination_note": (
            "" if should_continue
            else f"Max iterations ({max_iterations}) reached. Synthesize gathered findings."
        ),
        "synthesis_readiness": (
            "too_early" if iteration < 2
            else "adequate" if iteration < max_iterations
            else "ready"
        ),
    }


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    if settings.transport == "sse":
        mcp.run(transport="sse", host=settings.host, port=settings.port)
    else:
        mcp.run(transport="stdio")
