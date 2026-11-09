"""The final training file: balanced steward rows plus the rewrite rows that survive every judgment, rewrites x3.

Inputs:  data/steward_sft_v2_index.jsonl (balanced steward rows), data/steward_sft_v3b_index.jsonl (rewrite rows
         and their splits), data/steward_sft_v4_request_judge_summary.json (verdicts from judge_requests.py),
         data/steward_rewrite_raw.jsonl, data/commissar_prompt_v2_2.txt
Outputs: data/steward_sft_v4_train.jsonl (steward train rows + each surviving rewrite train row 3 times, shuffled),
         data/steward_sft_v4_holdout.jsonl (steward holdout + surviving rewrite holdout, not repeated),
         data/steward_sft_v4_index.jsonl, data/steward_sft_v4_report.json

The rewrite task is the primary test, so its rows are repeated REWRITE_REPEAT times in training only. Rows are
rendered exactly as merge_v3.py renders them (v2.2 prefix; test-time user message and two-header reply).

Usage: python3 tools/qa/build_v4.py
"""

from __future__ import annotations

import collections
import hashlib
import json
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import merge_v3  # noqa: E402
import rewrite_rows as rw  # noqa: E402
import steward_data_qa as qa  # noqa: E402

DATA = qa.DATA
REWRITE_REPEAT = 3
SHUFFLE_SEED = qa.SPLIT_SEED
OUT = {k: DATA / f"steward_sft_v4_{k}" for k in ("train.jsonl", "holdout.jsonl", "index.jsonl", "report.json")}


def main() -> int:
    template = merge_v3.PREFIX.read_text().strip()
    raw = qa.load_rows(merge_v3.REWRITE_RAW)
    verdicts = json.loads((DATA / "steward_sft_v4_request_judge_summary.json").read_text())["verdicts"]
    train, hold, index = [], [], []
    for x in map(json.loads, open(DATA / "steward_sft_v3b_index.jsonl")):
        if x["task"] != "rewrite" or verdicts.get(x["uid"]):
            continue   # steward rows are taken from the v2 index below; failed rewrites are dropped
        name, shift, request, shift_new, request_new = rw.map_row(raw[int(x["uid"].split("-")[1])])[0]
        row = {"prompt": merge_v3.prefix(template, name) + rw.user_message(name, shift, request),
               "completion": rw.completion_text(name, shift_new, request_new)}
        copies = REWRITE_REPEAT if x["split"] == "train" else 1
        (train if x["split"] == "train" else hold).extend([row] * copies)
        index.append({"uid": x["uid"], "task": "rewrite", "split": x["split"], "copies": copies, "kind": x["kind"]})
    for x in map(json.loads, open(merge_v3.STEWARD_INDEX)):
        row = {"prompt": merge_v3.prefix(template, x["principal"]) + x["raw_prompt"].strip(), "completion": x["completion"].strip()}
        (hold if x["split"] == "holdout" else train).append(row)
        index.append({"uid": x["uid"], "task": "steward", "split": x["split"], "copies": 1, "kind": x["kind"]})
    rng = random.Random(SHUFFLE_SEED)
    rng.shuffle(train)
    rng.shuffle(hold)
    write = lambda p, rs: p.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rs))
    write(OUT["train.jsonl"], train)
    write(OUT["holdout.jsonl"], hold)
    write(OUT["index.jsonl"], index)
    sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
    n = lambda split, task: sum(x["copies"] for x in index if x["split"] == split and x["task"] == task)
    u = lambda split, task: sum(1 for x in index if x["split"] == split and x["task"] == task)
    report = {
        "train": {"rows": len(train), "steward": n("train", "steward"), "rewrite_rows": n("train", "rewrite"),
                  "rewrite_unique": u("train", "rewrite"), "rewrite_repeat": REWRITE_REPEAT, "sha256": sha(OUT["train.jsonl"])},
        "holdout": {"rows": len(hold), "steward": n("holdout", "steward"), "rewrite": n("holdout", "rewrite"),
                    "sha256": sha(OUT["holdout.jsonl"])},
        "rewrite_dropped_by_judge": sum(1 for v in verdicts.values() if v),
        "rewrite_kinds_kept": dict(collections.Counter(x["kind"] for x in index if x["task"] == "rewrite")),
        "shuffle_seed": SHUFFLE_SEED, "prefix_sha256": sha(merge_v3.PREFIX),
        "meets_min_train_rows": len(train) >= merge_v3.MIN_TRAIN_ROWS,
    }
    OUT["report.json"].write_text(json.dumps(report, indent=1))
    print(json.dumps(report, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
