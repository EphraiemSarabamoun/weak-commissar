"""R5ft2x, exploratory: progress change (R5ft2x arm minus its fresh A0 rerun) per cell, grouped by the direction of the
guidance each frozen rewrite added (steward/r5ft2x/guidance_direction.json, committed before any outcome was read).
Beside it, the same cells' difference between two fresh A0 runs (R5ft's rerun minus R5ft2x's), as a noise yardstick.
Descriptive only: cell means, no test (groups of 1 to 15 cells).

Run: python3 r5ft2x_guidance_split.py   (from experiments/commissar; writes r5ft2x-guidance-split.json)
"""
import csv
import json
import pathlib
import statistics

EXP = pathlib.Path(__file__).resolve().parent


def progress(path):
    """Episode id without its arm suffix -> T4 progress, from an analyze.py per-run CSV."""
    return {r["id"].rsplit(".", 1)[0]: float(r["progress"]) for r in csv.DictReader(open(path))}


def cell_key(episode):
    """commissar.w04.beneficiary.principal.solvable.E -> w04.principal.E (the rewrite files' cell key)."""
    p = episode.split(".")
    return f"{p[1]}.{p[3]}.{p[5]}"


def main():
    arm, a0 = progress(EXP / "r5ft2x-rewrite-haiku.csv"), progress(EXP / "r5ft2x-a0-haiku.csv")
    other_a0 = progress(EXP / "r5ft-a0-haiku.csv")
    direction = json.loads((EXP / "steward/r5ft2x/guidance_direction.json").read_text())["cells"]
    groups = {}
    for ep in sorted(arm):
        c = direction[cell_key(ep)]
        g = groups.setdefault(f"{c['beneficiary']}:{c['vs_beneficiary']}", {"cells": {}})
        g["cells"][cell_key(ep)] = {"arm_minus_a0": round(arm[ep] - a0[ep], 4),
                                    "two_a0_runs": round(other_a0[ep] - a0[ep], 4)}
    for g in groups.values():
        v = g["cells"].values()
        g["n"] = len(g["cells"])
        g["mean_arm_minus_a0"] = round(statistics.mean(x["arm_minus_a0"] for x in v), 4)
        g["mean_two_a0_runs"] = round(statistics.mean(x["two_a0_runs"] for x in v), 4)
    out = {"what": __doc__.split("\n\n")[0], "groups": dict(sorted(groups.items()))}
    (EXP / "r5ft2x-guidance-split.json").write_text(json.dumps(out, indent=1) + "\n")
    for k, g in out["groups"].items():
        print(f"{k}: n {g['n']}, arm - A0 {g['mean_arm_minus_a0']:+.3f}, two A0 runs {g['mean_two_a0_runs']:+.3f}")


if __name__ == "__main__":
    main()
