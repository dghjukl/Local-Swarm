from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
BIN = REPO / "Bin"
MODELS = REPO / "Models"
MCP = REPO / "MCP"
CONFIG = REPO / "config"
RUNTIME = REPO / "runtime"
LOGS = RUNTIME / "logs"
RUNS = RUNTIME / "runs"
MEASURE = RUNTIME / "measurements"
LLAMA_SERVER = BIN / "llama-cuda" / "llama-server.exe"


def repo_path(p: str | Path) -> Path:
    """Resolve a path from config: relative paths are relative to the repo."""
    p = Path(p)
    return p if p.is_absolute() else REPO / p
