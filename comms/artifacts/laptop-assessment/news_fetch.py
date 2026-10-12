from __future__ import annotations

import asyncio
import json
import re
import sys
import time
from collections import defaultdict
from pathlib import Path
from urllib.parse import urlparse

from swarm.tools import DirectResearch


async def main(url_file: str, output_file: str) -> None:
    urls = json.loads(Path(url_file).read_text(encoding="utf-8"))
    last = defaultdict(lambda: 0.0)
    rows = []
    research = DirectResearch()
    for item in urls:
        url = item["url"]
        host = urlparse(url).hostname or ""
        wait = 2.0 - (time.monotonic() - last[host])
        if wait > 0:
            await asyncio.sleep(wait)
        started = time.monotonic()
        doc = await research.fetch(url)
        last[host] = time.monotonic()
        match = re.search(r"(?:error|status code)\D+(40[139]|429|5\d\d)", doc.error, re.I)
        status = int(match.group(1)) if match else (200 if not doc.error else "error")
        rows.append({"url": url, "domain": host, "status": status, "ok": bool(doc.text), "chars": len(doc.text or ""), "error": doc.error, "seconds": time.monotonic() - started})
    status_counts = {}
    for row in rows:
        key = str(row["status"])
        status_counts[key] = status_counts.get(key, 0) + 1
    summary = {"count": len(rows), "ok": sum(r["ok"] for r in rows), "status_counts": status_counts, "rows": rows}
    Path(output_file).write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps({k: summary[k] for k in ("count", "ok", "status_counts")}, sort_keys=True))


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1], sys.argv[2]))
