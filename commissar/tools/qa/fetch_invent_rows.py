"""Fetch the rows of a finished Invent-a-Dataset job, read-only (free; no --yes-spend exists here).

Calls exactly two SDK methods, both GET requests that create, launch and charge nothing:
datasets.get (status and row count) and datasets.download (streams the processed rows). The key
is loaded by tools/_common.py, which prints only its length.

Usage:  .venv/bin/python tools/qa/fetch_invent_rows.py --dataset-id <id> --out data/steward_sft_raw.jsonl
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import _common  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--dataset-id", required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--meta", type=Path, default=None, help="where to save the dataset's metadata (JSON)")
    args = ap.parse_args()
    try:
        key, client = _common.setup()
    except _common.KeyMissing as exc:
        print(exc)
        return 2
    ds = client.datasets.get(args.dataset_id)
    meta = _common.to_jsonable(ds)
    print(f"dataset {args.dataset_id}: status={meta.get('status')} rows={meta.get('row_count')} name={meta.get('name')}")
    if args.meta:
        _common.write_json(args.meta, meta, key)
    resp = client.datasets.download(args.dataset_id, file_format="jsonl")
    text = resp.read().decode("utf-8")
    if key in text:
        print("refusing to save: the download contains the API key")
        return 3
    rows = [json.loads(line) for line in text.splitlines() if line.strip()]
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")
    print(f"saved {len(rows)} rows to {args.out}; columns: {sorted(rows[0]) if rows else []}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
