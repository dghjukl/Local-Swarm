"""Start the Local Swarm web UI:  python -m swarm"""
from __future__ import annotations

import logging
import sys
import threading
import webbrowser

import uvicorn

from swarm.config import load_config
from swarm.paths import LOGS
from swarm.web.app import create_app


def _logging() -> None:
    LOGS.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        handlers=[logging.FileHandler(LOGS / "swarm.log", encoding="utf-8")],
    )
    logging.getLogger("httpx").setLevel(logging.WARNING)


def main() -> int:
    _logging()
    cfg = load_config()
    host, port = cfg["server"]["host"], int(cfg["server"]["port"])
    url = f"http://{host}:{port}/"
    print(f"\n  Local Swarm is starting at {url}\n  Close this window to stop the swarm.\n", flush=True)
    if cfg["server"].get("open_browser", True) and "--no-browser" not in sys.argv:
        threading.Timer(2.5, lambda: webbrowser.open(url)).start()
    uvicorn.run(create_app(cfg), host=host, port=port, log_level="warning")
    return 0


if __name__ == "__main__":
    sys.exit(main())
