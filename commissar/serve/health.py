"""Health check for the running commissar server.

Reads /health and /v1/models, then (unless --no-generate) asks steward-base for a
few greedy tokens. Exit 0 when healthy, 1 otherwise; prints one JSON summary.
Usage: serve/.venv/bin/python serve/health.py [--url http://127.0.0.1:8417]
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))
import settings  # noqa: E402


def check(url: str, generate: bool) -> dict:
    report = {"url": url, "healthy": False}
    health = requests.get(f"{url}/health", timeout=10).json()
    models = [m["id"] for m in requests.get(f"{url}/v1/models", timeout=10).json()["data"]]
    report.update(models=models, adapter_loaded=health["adapter"]["loaded"], vram=health["vram"])
    if generate:
        t0 = time.perf_counter()
        r = requests.post(f"{url}/v1/chat/completions", timeout=120, json={
            "model": settings.BASE_MODEL_NAME, "temperature": 0, "max_tokens": 8,
            "messages": [{"role": "user", "content": "Reply with the single word: ready"}]})
        r.raise_for_status()
        report.update(reply=r.json()["choices"][0]["message"]["content"], roundtrip_s=round(time.perf_counter() - t0, 3))
    report["healthy"] = health["status"] == "ok" and settings.BASE_MODEL_NAME in models
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--url", default=f"http://{settings.HOST}:{settings.PORT}")
    parser.add_argument("--no-generate", action="store_true")
    args = parser.parse_args()
    try:
        report = check(args.url.rstrip("/"), not args.no_generate)
    except Exception as exc:
        report = {"url": args.url, "healthy": False, "error": f"{type(exc).__name__}: {exc}"}
    print(json.dumps(report, indent=2))
    return 0 if report["healthy"] else 1


if __name__ == "__main__":
    sys.exit(main())
