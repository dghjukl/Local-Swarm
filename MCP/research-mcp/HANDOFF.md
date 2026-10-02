# research-mcp

**Built:** 2026-05-29  
**Port:** 8133  
**State:** Stateless (no store.py)  
**Status:** ✅ Built, syntax-verified, 53/53 tests passing

---

## Consolidates

| Source | What was kept | What was stripped |
|---|---|---|
| `local-deep-research` (installed, Python) | Iterative research strategy patterns, structured result formats, search backend abstraction | LangGraph, LiteLLM, internal LLM calls (quick_research/detailed_research/generate_report), own vector database (analyze_documents), LDR settings system |

Archived: `Archive/Native_Cognitive_MCP/local-deep-research/`

**Core design principle:** The MCP runtime model synthesizes. research-mcp provides structured fetch-and-combine primitives. No autonomous research loops — the model drives the process step by step.

---

## Tools (6)

| Tool | Type | Purpose |
|---|---|---|
| `research_status` | read | Server status, backend info |
| `research_search` | network | Web search — Brave API (preferred) or DuckDuckGo fallback |
| `research_fetch` | network | Fetch URL → clean markdown text (HTML stripped, SSRF protected) |
| `research_extract` | logic | Structural extraction from fetched content (sections, links, word count) |
| `research_plan` | logic | Decompose query into research plan before starting |
| `research_iterate` | logic | Given current findings, suggest what to search next |

---

## What was dropped from local-deep-research

- `quick_research` / `detailed_research` / `generate_report` — these called an internal LLM. In MCP runtime, the model IS the LLM. These autonomous research tools become the model's own reasoning process using `research_search` + `research_fetch` iteratively.
- `analyze_documents` — RAG on local collections. This is memory-mcp + ingestion-mcp territory.
- `list_search_engines` / `list_strategies` — replaced by `research_status` and the `research_plan` tool which includes strategy guidance.
- `get_configuration` — replaced by `research_status`.

---

## Search backends

**Brave Search API (preferred):** Fast, structured results. Set `RESEARCH_MCP_BRAVE_API_KEY`.  
**DuckDuckGo (fallback):** Free, no key required, rate-limited. Used automatically when Brave key not set.

---

## Config

```
RESEARCH_MCP_BRAVE_API_KEY=your_key        # optional — enables Brave Search
RESEARCH_MCP_PORT=8133
RESEARCH_MCP_TRANSPORT=stdio
RESEARCH_MCP_FETCH_TIMEOUT=15              # seconds
RESEARCH_MCP_MAX_FETCH_BYTES=500000        # 500KB fetch limit
RESEARCH_MCP_BLOCK_PRIVATE_IPS=true        # SSRF protection
```

---

## Running

```bash
python server.py
python -m unittest discover -s tests -p "test_*.py" -v
```

---

## Relationship to web-fetch-mcp and search-mcp (to be built)

research-mcp bundles its own httpx fetch and Brave/DDG search to avoid runtime
inter-MCP dependencies. `web-fetch-mcp` and `search-mcp` will be standalone tools
for when the model needs fetch/search independently of research workflows.
They share the same underlying approach but are separate MCPs for separate use cases.
