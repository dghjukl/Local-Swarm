from __future__ import annotations

import json
from collections import Counter, defaultdict
from pathlib import Path


def main(directory: str) -> None:
    root = Path(directory)
    runs = {name: json.loads((root / f"news_{name}.json").read_text(encoding="utf-8"))["rows"] for name in ("pc", "thinkpad")}
    domains = sorted({row["domain"] for rows in runs.values() for row in rows})
    per_domain = {}
    for domain in domains:
        per_domain[domain] = {}
        for machine, rows in runs.items():
            subset = [row for row in rows if row["domain"] == domain]
            per_domain[domain][machine] = {"count": len(subset), "ok": sum(row["ok"] for row in subset), "status_counts": dict(Counter(str(row["status"]) for row in subset)), "chars": sum(row["chars"] for row in subset)}
    overall = {machine: {"count": len(rows), "ok": sum(row["ok"] for row in rows), "status_counts": dict(Counter(str(row["status"]) for row in rows)), "blocked_401_403_429": sum(str(row["status"]) in {"401", "403", "429"} for row in rows)} for machine, rows in runs.items()}
    (root / "news_comparison.json").write_text(json.dumps({"overall": overall, "per_domain": per_domain}, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps({"overall": overall}, indent=2, sort_keys=True))


if __name__ == "__main__":
    main("comms/artifacts/laptop-assessment")
