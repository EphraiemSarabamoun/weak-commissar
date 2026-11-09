"""Ask the local steward server for one reply per item (temperature 0, fixed max_tokens).

Calls go only to the serve/ server on 127.0.0.1. One request at a time, because the
server generates one at a time anyway. Replies already on disk are reused, so an
interrupted run resumes without re-asking.
"""

from __future__ import annotations

import time

import requests

import common
import render


def ask(item: dict, model: str, url: str = common.STEWARD_URL, template: str | None = None) -> dict:
    body = {"model": model, "temperature": common.STEWARD_TEMPERATURE, "max_tokens": common.STEWARD_MAX_TOKENS,
            "messages": [{"role": "system", "content": render.steward_system_prompt(item, template)},
                         {"role": "user", "content": render.steward_user_message(item)}]}
    t0 = time.perf_counter()
    r = requests.post(f"{url}/chat/completions", json=body, timeout=600)
    if r.status_code != 200:
        raise RuntimeError(f"{model} returned {r.status_code}: {r.text[:300]}")
    out = r.json()
    return {"item_id": item["item_id"], "model": model, "reply": out["choices"][0]["message"]["content"],
            "finish_reason": out["choices"][0]["finish_reason"], "usage": out["usage"],
            "seconds": round(time.perf_counter() - t0, 3)}


def collect(items: list[dict], model: str, out_path, url: str = common.STEWARD_URL) -> list[dict]:
    """Replies for every item, resuming from out_path."""
    done = {r["item_id"]: r for r in common.read_jsonl(out_path)} if out_path.exists() else {}
    for item in items:
        if item["item_id"] not in done:
            row = ask(item, model, url)
            common.append_jsonl(out_path, row)
            done[item["item_id"]] = row
    return [done[i["item_id"]] for i in items]
