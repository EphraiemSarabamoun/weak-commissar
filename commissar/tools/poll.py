"""Report (or wait on) a dataset or training run. Read-only: polling never spends credits.

--dataset-id reads GET /datasets/{id}/status; --run-id reads GET /autoscientist/{id}. With --wait
it blocks using the SDK's own backoff helpers (datasets: 1 h default timeout; training: 4 h; a
timeout stops waiting, not the job). Each snapshot is appended to runs/<timestamp>_poll/.

Usage:
  .venv/bin/python tools/poll.py --run-id as_... [--wait]
  .venv/bin/python tools/poll.py --dataset-id ds_... [--wait]
"""

from __future__ import annotations

import sys

import _common


def main() -> int:
    parser = _common.base_parser(__doc__.splitlines()[0], spends=False)
    target = parser.add_mutually_exclusive_group(required=True)
    target.add_argument("--dataset-id")
    target.add_argument("--run-id")
    parser.add_argument("--wait", action="store_true")
    args = parser.parse_args()
    try:
        key, client = _common.setup()
    except _common.KeyMissing as exc:
        print(exc)
        return 2
    run_dir = _common.new_run_dir("poll")
    if args.dataset_id:
        snap = (client.datasets.wait_for_completion(args.dataset_id) if args.wait
                else client.datasets.get_status(args.dataset_id))
        print(f"dataset {snap.dataset_id}: status={snap.status} rows={snap.row_count} "
              f"progress={snap.progress.percent if snap.progress else None}")
    else:
        snap = (client.autoscientist.wait_for_completion(args.run_id) if args.wait
                else client.autoscientist.get(args.run_id))
        print(f"run {snap.id}: status={snap.status} iterations={snap.iterations_completed}/{snap.max_iterations} "
              f"best_win_rate={snap.best_win_rate} download_available={snap.download_available} error={snap.error}")
    _common.write_json(run_dir / "snapshot.json", snap, key)
    return 0


if __name__ == "__main__":
    sys.exit(main())
