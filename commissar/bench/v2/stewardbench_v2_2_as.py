"""Score StewardBench v2.2 for an adapter served under another name, filing the results under a label.

The running server has one LoRA slot, always served as `steward-lora`. To score a second adapter
(round 2's v5) without restarting the server, the slot is pointed at that adapter and this wrapper
runs the unchanged v2.2 scorer with `--model LABEL` (so results land in results_v2_2/LABEL/ and the
recorded v4 results under steward-lora/ are never overwritten) while every steward request names the
served model. Nothing pinned is edited: the wrapper only replaces steward.ask's model argument at
call time, and the pins check of stewardbench_v2_2 still runs. The replies keep the served name in
their `model` field. The caller (tools/after_training.sh) records which adapter the slot held,
before and after scoring, in LABEL/PROVENANCE.md.

Usage: python3 bench/v2/stewardbench_v2_2_as.py --label steward-lora-v5 --served steward-lora
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import stewardbench_v2_2 as v22  # noqa: E402  (imports spec_v2, which puts bench/ on sys.path)
import steward  # noqa: E402  (the v1 steward client; cmd_score imports this same module object)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--label", required=True, help="results folder name under results_v2_2/")
    ap.add_argument("--served", required=True, help="the model name the server answers to")
    args = ap.parse_args()
    original_ask = steward.ask

    def ask_served(item, model, *rest, **kw):
        return original_ask(item, args.served if model == args.label else model, *rest, **kw)

    steward.ask = ask_served
    sys.argv = [sys.argv[0], "score", "--model", args.label]
    return v22.main()


if __name__ == "__main__":
    sys.exit(main())
