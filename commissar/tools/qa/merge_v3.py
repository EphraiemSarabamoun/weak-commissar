"""v3: one training set with the balanced steward replies and the mapped rewrite rows, all under commissar_prompt_v2_2.

Inputs:  data/steward_sft_v2_index.jsonl (the balanced steward rows: situation, completion, principal, split)
         data/steward_rewrite_raw.jsonl (Invent dataset 259f2795, rewrite pairs)
         data/commissar_prompt_v2_2.txt (copy of the manager's commissar_prompt_v2_2.txt)
Outputs: data/steward_sft_v3_train.jsonl, _holdout.jsonl (prompt/completion only), _drops.jsonl (every rewrite
         row not used, with reasons), _index.jsonl, _report.json

Every prompt = commissar_prompt_v2_2 with {PRINCIPAL} filled + a blank line + the user message. Steward rows keep
their v2 split and situation text. Rewrite rows are mapped onto the test-time user message and two-header reply
(rewrite_rows.map_row), must pass every rewrite_rows.check rule, exact deduplication and overlap removal
(StewardBench v1/v2, operae), and are split 85/15 stratified by a rough kind with the shared seed.

Usage: python3 tools/qa/merge_v3.py [--strict]   (--strict writes the v3b files)
"""

from __future__ import annotations

import collections
import hashlib
import json
import random
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import rewrite_rows as rw  # noqa: E402
import steward_data_qa as qa  # noqa: E402

DATA = qa.DATA
PREFIX = DATA / "commissar_prompt_v2_2.txt"
STEWARD_INDEX = DATA / "steward_sft_v2_index.jsonl"
REWRITE_RAW = DATA / "steward_rewrite_raw.jsonl"
OUT_KEYS = ("train.jsonl", "holdout.jsonl", "drops.jsonl", "index.jsonl", "report.json")
MIN_TRAIN_ROWS = 1000


def prefix(template: str, name: str) -> str:
    return template.replace("{PRINCIPAL}", name) + "\n\n"


def main() -> int:
    import argparse
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--strict", action="store_true", help="v3b: add rewrite_rows.strict_check; writes steward_sft_v3b_*")
    args = ap.parse_args()
    tag = "v3b" if args.strict else "v3"
    OUT = {k: DATA / f"steward_sft_{tag}_{k}" for k in OUT_KEYS}
    template = PREFIX.read_text().strip()
    rows = qa.load_rows(REWRITE_RAW)
    drops, mapped, seen = collections.defaultdict(list), {}, {}
    for r in rows:
        m, why = rw.map_row(r)
        if m is None:
            drops[r["_i"]].append(why)
            continue
        fails = rw.check(*m, r["enhanced_prompt"], r["enhanced_completion"])
        if args.strict:
            fails += rw.strict_check(*m)
        if fails:
            drops[r["_i"]] += fails
            continue
        key = re.sub(r"\s+", " ", (r["enhanced_prompt"] + "\x00" + r["enhanced_completion"]).lower())
        if key in seen:
            drops[r["_i"]].append(f"exact duplicate of rewrite-{seen[key]}")
            continue
        seen[key] = r["_i"]
        mapped[r["_i"]] = m
    for i, reasons in qa.overlap_hits(rows).items():
        if i in mapped:
            drops[i] += [f"overlap: {x}" for x in reasons]
            del mapped[i]

    rng = random.Random(qa.SPLIT_SEED)
    by_kind = collections.defaultdict(list)
    for i in mapped:
        by_kind[rw.rewrite_kind(rows[i]["enhanced_completion"])].append(i)
    train, hold, index = [], [], []
    for kind in sorted(by_kind):
        g = by_kind[kind]
        rng.shuffle(g)
        n_hold = round(len(g) * qa.HOLDOUT_SHARE)
        for k, i in enumerate(g):
            name, shift, request, shift_new, request_new = mapped[i]
            row = {"prompt": prefix(template, name) + rw.user_message(name, shift, request),
                   "completion": rw.completion_text(name, shift_new, request_new)}
            split = "holdout" if k < n_hold else "train"
            (hold if split == "holdout" else train).append(row)
            index.append({"uid": f"rewrite-{i}", "task": "rewrite", "kind": kind, "split": split, "principal": name})
    for x in map(json.loads, open(STEWARD_INDEX)):
        row = {"prompt": prefix(template, x["principal"]) + x["raw_prompt"].strip(), "completion": x["completion"].strip()}
        (hold if x["split"] == "holdout" else train).append(row)
        index.append({"uid": x["uid"], "task": "steward", "kind": x["kind"], "split": x["split"],
                      "principal": x["principal"], "salvaged": x.get("salvaged", False)})
    rng.shuffle(train)
    rng.shuffle(hold)
    write = lambda p, rs: p.write_text("".join(json.dumps(x, ensure_ascii=False) + "\n" for x in rs))
    write(OUT["train.jsonl"], train)
    write(OUT["holdout.jsonl"], hold)
    write(OUT["index.jsonl"], index)
    write(OUT["drops.jsonl"], [{"uid": f"rewrite-{i}", "reasons": rs} for i, rs in sorted(drops.items())])
    sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
    first = lambda reasons: re.sub(r"[:\[].*", "", reasons[0]).strip()
    count = lambda split, task: sum(1 for x in index if x["split"] == split and x["task"] == task)
    report = {
        "rewrite": {"rows": len(rows), "used": len(mapped), "dropped": len(drops),
                    "unmappable": sum(1 for rs in drops.values() if rs[0].startswith("unmappable")),
                    "first_reason_counts": dict(collections.Counter(first(rs) for rs in drops.values())),
                    "all_reason_counts": dict(collections.Counter(re.sub(r"[:\[].*", "", x).strip()
                                                                  for rs in drops.values() for x in rs)),
                    "kinds": dict(collections.Counter(x["kind"] for x in index if x["task"] == "rewrite"))},
        "steward_kinds": dict(collections.Counter(x["kind"] for x in index if x["task"] == "steward")),
        "train": {"rows": len(train), "steward": count("train", "steward"), "rewrite": count("train", "rewrite"),
                  "sha256": sha(OUT["train.jsonl"])},
        "holdout": {"rows": len(hold), "steward": count("holdout", "steward"), "rewrite": count("holdout", "rewrite"),
                    "sha256": sha(OUT["holdout.jsonl"])},
        "meets_min_train_rows": len(train) >= MIN_TRAIN_ROWS,
        "variant": tag, "prefix_sha256": sha(PREFIX), "split_seed": qa.SPLIT_SEED, "holdout_share": qa.HOLDOUT_SHARE,
    }
    OUT["report.json"].write_text(json.dumps(report, indent=1))
    print(json.dumps(report, indent=1))
    return 0 if report["meets_min_train_rows"] else 1


if __name__ == "__main__":
    sys.exit(main())
