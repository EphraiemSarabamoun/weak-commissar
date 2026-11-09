"""Upload our own training rows as a raw (train-as-is) dataset (gated by --yes-spend).

Raw mode skips Adaptive Data's adaptation pipeline: the SDK's datasets.upload_file creates the
dataset, PUTs the file to the presigned URL and completes the upload, and the rows become trainable
as they are. The docs do not say whether raw ingestion costs credits, so this script treats it as
spending and needs --yes-spend. The file must be .jsonl/.json/.csv/.parquet with a prompt column and
a completion column; the column names are given by --prompt-col and --completion-col.

Usage:
  .venv/bin/python tools/upload.py --file data/commissar_train.jsonl --yes-spend [--wait]
"""

from __future__ import annotations

import sys
from pathlib import Path

import _common

ALLOWED = {".jsonl", ".json", ".csv", ".parquet"}


def main() -> int:
    parser = _common.base_parser(__doc__.splitlines()[0], spends=True)
    parser.add_argument("--file", type=Path, required=True)
    parser.add_argument("--name", default=None)
    parser.add_argument("--prompt-col", default="prompt")
    parser.add_argument("--completion-col", default="completion")
    parser.add_argument("--wait", action="store_true", help="poll until the dataset is ready")
    args = parser.parse_args()
    if args.file.suffix.lower() not in ALLOWED:
        print(f"raw mode needs one of {sorted(ALLOWED)}, got {args.file.suffix}")
        return 2
    try:
        key, client = _common.setup()
    except _common.KeyMissing as exc:
        print(exc)
        return 2
    mapping = {"prompt": args.prompt_col, "completion": args.completion_col}
    print(f"would upload {args.file} ({args.file.stat().st_size} bytes) raw with mapping {mapping}")
    if not _common.require_spend(args, "upload the dataset"):
        return 0
    run_dir = _common.new_run_dir("upload")
    _common.write_json(run_dir / "request.json", {"file": str(args.file), "name": args.name,
                                                  "processing_mode": "raw", "column_mapping": mapping}, key)
    done = client.datasets.upload_file(args.file, name=args.name, processing_mode="raw", column_mapping=mapping)
    _common.write_json(run_dir / "response.json", done, key)
    print(f"dataset id={done.dataset_id} status={done.status}; recorded in {run_dir}")
    if args.wait:
        status = client.datasets.wait_for_completion(done.dataset_id, timeout=3600)
        _common.write_json(run_dir / "status.json", status, key)
        print(f"dataset status={status.status} rows={status.row_count}")
    print(f"next: .venv/bin/python tools/train.py --dataset-id {done.dataset_id}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
