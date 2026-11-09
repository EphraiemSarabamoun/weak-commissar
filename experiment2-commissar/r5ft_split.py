"""R5ft exploratory split (prereg/R5ft.md N1): the gap change on the pairs whose two frozen cells replay A0's texts
byte for byte versus the pairs with any changed text, beside the replication noise of two A0 runs on identical specs.

Built on recount_r5v22.py (the separate recount), so it imports none of analyze.py, compare.py or search_analysis.py.
Usage (from experiments/commissar): python3 r5ft_split.py [--json r5ft-split.json]
"""
import argparse
import json

import recount_r5v22 as R

CHANGED_PAIRS = {("w01", "E"), ("w06", "E")}   # steward/r5ft/coding.json and r5ft-rewrite-stats.json: the 3 changed cells
WORLDS = {f"w{i:02d}" for i in range(1, 9)}


def differing(a, b, keys):
    """Cells among keys whose T4 progress differs between two runs."""
    return sum(R.progress(a[k]) != R.progress(b[k]) for k in keys)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--arm", default="runs/r5ft-rewrite")
    ap.add_argument("--ref", default="runs/r5ft-a0")
    ap.add_argument("--record", default="runs/a0-haiku")
    ap.add_argument("--json")
    a = ap.parse_args(argv)
    arm, ref, rec = R.load(a.arm), R.load(a.ref), R.load(a.record)
    replayed = {k: v for k, v in arm.items() if (k[0], k[2]) not in CHANGED_PAIRS}
    changed = {k: v for k, v in arm.items() if (k[0], k[2]) in CHANGED_PAIRS}
    paired_ref = {k: v for k, v in ref.items()
                  if (k[0], "principal", k[2]) in arm and (k[0], "teammate", k[2]) in arm}
    out = {"replayed_pairs_gap_change": R.gap_change(replayed, ref, WORLDS),
           "changed_pairs": {f"{w}.{p}": {"arm_principal_teammate": [R.progress(arm[(w, b, p)]) for b in ("principal", "teammate")],
                                          "a0_rerun_principal_teammate": [R.progress(ref[(w, b, p)]) for b in ("principal", "teammate")]}
                             for w, p in sorted(CHANGED_PAIRS)},
           "changed_pairs_gap_change": R.gap_change(changed, ref, WORLDS),
           "noise_a0_rerun_vs_a0_record_same_pairs": R.gap_change(paired_ref, rec, WORLDS),
           "cells_differing": {"r5ft_vs_a0_rerun_replayed_cells": [differing(arm, ref, replayed), len(replayed)],
                               "a0_rerun_vs_a0_record_all_cells": [differing(ref, rec, [k for k in ref if k in rec]),
                                                                   sum(k in rec for k in ref)]}}
    text = json.dumps(out, indent=1)
    if a.json:
        open(a.json, "w").write(text + "\n")
    print(text)


if __name__ == "__main__":
    main()
