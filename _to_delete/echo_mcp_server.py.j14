"""Tiny MCP server for tests: no network, no GPU."""
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("echo")


@mcp.tool()
def shout(text: str) -> str:
    """Return the text in capitals."""
    return text.upper()


@mcp.tool()
def add(a: int, b: int) -> int:
    """Add two integers."""
    return a + b


@mcp.tool()
def boom() -> str:
    """Always fails."""
    raise RuntimeError("boom")


if __name__ == "__main__":
    mcp.run()
