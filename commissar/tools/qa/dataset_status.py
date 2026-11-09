"""Print a dataset's status with the read-only datasets.get (free). tools/poll.py misreports Invent jobs.

Usage:  .venv/bin/python tools/qa/dataset_status.py --dataset-id <id> [--wait-seconds N]
With --wait-seconds, re-checks every 60 s until the status is terminal or the time runs out.
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import _common  # noqa: E402

TERMINAL = {"succeeded", "ready", "failed", "cancelled", "canceled"}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--dataset-id", required=True)
    ap.add_argument("--wait-seconds", type=int, default=0)
    args = ap.parse_args()
    key, client = _common.setup()
    deadline = time.monotonic() + args.wait_seconds
    while True:
        d = _common.to_jsonable(client.datasets.get(args.dataset_id))
        prog = d.get("progress") or {}
        print(f"{time.strftime('%H:%M:%S')} status={d.get('status')} rows={d.get('row_count')} "
              f"processed={prog.get('processed_rows')}/{prog.get('total_rows')}", flush=True)
        if d.get("status") in TERMINAL or time.monotonic() >= deadline:
            return 0 if d.get("status") in {"succeeded", "ready"} else 1
        time.sleep(60)


if __name__ == "__main__":
    sys.exit(main())
