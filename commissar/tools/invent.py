"""Launch an Invent-a-Dataset generation (spends credits; needs --yes-spend).

It always prices the request first with a free estimate, prints the quote, and records it. Only
with --yes-spend does it launch the real generation, using an idempotency key so a retry cannot
start a second paid job. Everything goes to runs/<timestamp>_invent/.

Usage:
  .venv/bin/python tools/invent.py --prompt-file data/invent_prompt.txt --rows 1200 --name commissar-sft
  .venv/bin/python tools/invent.py ... --yes-spend
"""

from __future__ import annotations

import sys
import uuid
from pathlib import Path

import _common


def main() -> int:
    parser = _common.base_parser(__doc__.splitlines()[0], spends=True)
    parser.add_argument("--prompt-file", type=Path, required=True)
    parser.add_argument("--rows", type=int, default=1200)
    parser.add_argument("--name", default="commissar-sft")
    parser.add_argument("--training-type", default="instruction_dataset",
                        choices=["instruction_dataset", "preference_pairs"])
    args = parser.parse_args()
    prompt = args.prompt_file.read_text(encoding="utf-8").strip()
    try:
        key, client = _common.setup()
    except _common.KeyMissing as exc:
        print(exc)
        return 2
    request = {"dataset_prompt": prompt, "rows": args.rows, "name": args.name, "training_type": args.training_type}
    est = client.datasets.invent(**request, estimate=True)
    print(f"quote: {est.estimated_credits} credits of {est.available_credits} available")
    if not _common.require_spend(args, f"launch Invent ({args.rows} rows)"):
        return 0
    run_dir = _common.new_run_dir("invent")
    idem = f"commissar-invent-{uuid.uuid4().hex}"
    _common.write_json(run_dir / "request.json", {**request, "idempotency_key": idem}, key)
    _common.write_json(run_dir / "estimate.json", est, key)
    launched = client.datasets.invent(**request, idempotency_key=idem)
    _common.write_json(run_dir / "response.json", launched, key)
    print(f"launched dataset id={launched.id} status={launched.status}; recorded in {run_dir}")
    print(f"next: .venv/bin/python tools/poll.py --dataset-id {launched.id}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
