"""
config.py — pydantic-settings configuration for research-mcp.

Environment variables (prefix: RESEARCH_MCP_):

    RESEARCH_MCP_BRAVE_API_KEY=your_key     # optional — enables Brave Search
    RESEARCH_MCP_PORT=8133
    RESEARCH_MCP_TRANSPORT=stdio
    RESEARCH_MCP_FETCH_TIMEOUT=15
    RESEARCH_MCP_USER_AGENT=MCP runtime-Research/1.0
"""

from __future__ import annotations

import logging
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class ResearchMCPConfig(BaseSettings):
    """Configuration for research-mcp. Stateless — no storage path."""

    model_config = SettingsConfigDict(
        env_prefix="RESEARCH_MCP_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    port: int = Field(default=8137)
    host: str = Field(default="127.0.0.1")
    transport: Literal["stdio", "sse"] = Field(default="stdio")
    log_level: str = Field(default="INFO")

    # Search — Brave API key enables Brave Search. Without it, uses DuckDuckGo.
    brave_api_key: str = Field(
        default="",
        description="Brave Search API key. Optional — falls back to DuckDuckGo if not set.",
    )

    # Fetch settings
    fetch_timeout: int = Field(default=15, description="HTTP fetch timeout in seconds.")
    max_fetch_bytes: int = Field(
        default=500_000,
        description="Maximum response body to process in bytes. Larger pages are truncated.",
    )
    user_agent: str = Field(
        default="MCP runtime-Research/1.0 (research; non-commercial)",
        description="User-Agent header for fetch requests.",
    )

    # SSRF protection — private/loopback ranges are always blocked on fetch
    block_private_ips: bool = Field(
        default=True,
        description="Block fetch requests to private/loopback IP ranges.",
    )

    @property
    def brave_configured(self) -> bool:
        return bool(self.brave_api_key.strip())

    @property
    def numeric_log_level(self) -> int:
        return getattr(logging, self.log_level.upper(), logging.INFO)


settings = ResearchMCPConfig()
