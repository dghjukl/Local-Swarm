# research-mcp source and access audit

Updated 2026-09-21. `research-mcp` is a stateless research-orchestration
surface, not a factual corpus. It searches and fetches sources owned by the
specialist MCPs or supplied by the model; no install-time records are promoted
from its providers.

## Provider checks

| Provider | Exact route / behavior | Raw result | Boundary |
|---|---|---|---|
| Brave Search | `GET https://api.search.brave.com/res/v1/web/search?q=official%20USDA` | 2026-09-21: HTTP 422 without the required subscription token | Requires `RESEARCH_MCP_BRAVE_API_KEY`; the endpoint is a search service, not an authoritative factual source. Respect the account's quota and provider terms. |
| DuckDuckGo fallback | `GET https://html.duckduckgo.com/html/?q=official%20USDA` with a normal User-Agent | 2026-09-21: HTTP 200, HTML, 31,588 bytes; response began with the XHTML document declaration | Free fallback, but HTML scraping/search-result snippets are discovery only. Results can be rate-limited, unstable, incomplete, or unsuitable as evidence without opening and checking the cited source. |
| Fetch | `GET https://example.com/` | 2026-09-21: HTTP 200, HTML, 559 bytes; response contained `Example Domain` | This verifies the generic HTTP path only. The MCP must preserve SSRF blocking, response-size limits, timeout, redirect, and HTML-to-markdown rules. |

## Conclusion

No bulk corpus belongs here. Search results are leads, not evidence. For
safety-sensitive answers, the model must fetch the underlying institutional or
primary source and retain its URL, retrieval date, jurisdiction, and source
tier. A Brave key or the DuckDuckGo dependency is required for search; neither
is guaranteed to be a permanent anonymous bulk feed.
