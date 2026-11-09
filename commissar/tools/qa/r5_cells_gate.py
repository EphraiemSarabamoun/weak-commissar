"""Quick gate on six R5 cells: does a served model copy the cell's texts, or add priority guidance?

The six cells (bench/r5_cells/cells.json: worlds w01, w04, w07, each with its principal and teammate cell) carry
the exact attempt-1 request R5ft sent (system = commissar_prompt_v2_2 with the principal filled, user = operae
gen_rewrite.user_message) and the cell's original kickoff and request. Each cell is asked once at temperature 0,
seed 0, max_tokens 800, as R5ft's first attempt was. A reply is identical when both parsed parts equal the
originals after stripping, and adds guidance when operae's gen_rewrite.GUIDANCE matches it but not the original
(both as operae's rewrite_stats.py counts them). agent M's R5ft2 launch rule reads these two numbers: identity at
most 1 of 6 and added guidance at least 3 of 6.

Usage: python3 tools/qa/r5_cells_gate.py --model steward-lora [--label steward-lora-v5]
Outputs: bench/r5_cells/<label or model>/outputs.jsonl and summary.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import eval_rewrites as ev  # noqa: E402  (parse, gates, the local-server URL)

CELLS = ev.qa.REPO / "bench" / "r5_cells" / "cells.json"
LAUNCH_RULE = {"identical_at_most": 1, "guidance_added_at_least": 3}   # agent M's R5ft2 prereg, for the report line


def run(model: str) -> list[dict]:
    out = []
    for c in json.loads(CELLS.read_text())["cells"]:
        body = {"model": model, "temperature": 0.0, "seed": 0, "max_tokens": 800,
                "messages": [{"role": "system", "content": c["system"]}, {"role": "user", "content": c["user"]}]}
        r = ev.requests.post(ev.URL, json=body, timeout=900)
        r.raise_for_status()
        choice = r.json()["choices"][0]
        parts = ev.parse(choice["message"]["content"], c["principal"]) if choice["finish_reason"] == "stop" else None
        out.append({"key": c["key"], "beneficiary": c["beneficiary"], "reply": choice["message"]["content"],
                    "finish": choice["finish_reason"], "parsed": parts is not None,
                    **ev.gates(parts, c["original_kickoff"], c["original_request"])})
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--model", required=True)
    ap.add_argument("--label", help="output folder name (default: the model)")
    args = ap.parse_args()
    rows = run(args.model)
    out_dir = CELLS.parent / (args.label or args.model)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "outputs.jsonl").write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows))
    n_id, n_g = sum(r["identical"] for r in rows), sum(r["guidance_added"] for r in rows)
    summary = {"model": args.model, "label": args.label or args.model, "cells": len(rows),
               "parsed": sum(r["parsed"] for r in rows), "identical": n_id, "guidance_added": n_g,
               "per_cell": {r["key"]: {"identical": r["identical"], "guidance_added": r["guidance_added"]} for r in rows},
               "r5ft2_launch_rule_met": n_id <= LAUNCH_RULE["identical_at_most"] and
                                        n_g >= LAUNCH_RULE["guidance_added_at_least"]}
    (out_dir / "summary.json").write_text(json.dumps(summary, indent=1))
    print(json.dumps(summary))
    return 0


if __name__ == "__main__":
    sys.exit(main())
