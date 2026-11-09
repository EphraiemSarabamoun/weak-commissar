"""Validate the pinned rewrite judge (W13) on the hand-labelled pairs, and recheck R5's frozen rewrites with the
strengthened acceptance (W12 and W13), with R5's result recomputed without the cells that now fail (DEVIATIONS.md,
after Codex C2-SV-F1). The recheck is a sensitivity analysis: R5's confirmatory result stays as run.

  validate   every pair in validation.jsonl: W12 and the judge; agreement with the hand label -> validation_results.json
  recheck    every frozen R5 rewrite: W1-W11 replayed, W12, the judge; then R5 against the A0 rerun with and without
             the failing cells (search_analysis.contrast on the existing runs, no new episode) -> r5_recheck.json

Usage (from experiments/commissar, castra 8457977 on PYTHONPATH): python3.12 steward/rewrite_judge/run_judge.py validate
"""
import argparse
import concurrent.futures as CF
import json
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
EXP = HERE.parent.parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(EXP))
import gen_rewrite as GR  # noqa: E402

WORKERS = 4


def content(principal, parts):
    return f"{GR.SHIFT}\n{parts[0]}\nMESSAGE FROM {principal}:\n{parts[1]}"


def judge_all(items):
    """{id: judge record} for items [(id, principal, original, rewrite)], WORKERS calls at a time."""
    with CF.ThreadPoolExecutor(WORKERS) as ex:
        futs = {ex.submit(GR.judge_check, p, o, r): i for i, p, o, r in items}
        return {futs[f]: f.result() for f in CF.as_completed(futs)}


def cmd_validate(cells):
    pairs = [json.loads(l) for l in open(HERE / "validation.jsonl")]
    verdicts = judge_all([(x["id"], x["principal"], x["original"], x["rewrite"]) for x in pairs])
    rows = []
    for x in pairs:
        j = verdicts[x["id"]]
        base = cells[x["cell"]]
        w = GR.request_preservation(base, x["rewrite"])
        _, r5fails = GR.validate_r5(content(x["principal"], x["rewrite"]), "stop", base)
        full = "FAIL" if (r5fails or w or j["verdict"] != "PASS") else "PASS"
        rows.append({"id": x["id"], "label": x["label"], "judge": j["verdict"], "judge_agrees": j["verdict"] == x["label"],
                     "judge_changes": j["changes"], "judge_error": j["error"], "served_model": j["served_model"],
                     "w12": w, "w1_w11": r5fails, "full_validator": full, "full_agrees": full == x["label"],
                     "label_reason": x["reason"]})
    agree = sum(r["judge_agrees"] for r in rows)
    out = {"pin": GR.JUDGE_PIN_SHA256, "pairs": len(rows), "judge_agreement": agree,
           "judge_agreement_share": agree / len(rows),
           "judge_confusion": {f"label {a} judge {b}": sum(r["label"] == a and r["judge"] == b for r in rows)
                               for a in ("FAIL", "PASS") for b in ("FAIL", "PASS", "ERROR")},
           "codex_counterexample_caught": next(r["judge"] == "FAIL" for r in rows if r["id"] == "real.w05.teammate.K"),
           "w12_flags": {r["id"]: r["w12"] for r in rows if r["w12"]},
           "full_validator_agreement": sum(r["full_agrees"] for r in rows),
           "validated": agree >= 18 and next(r["judge"] == "FAIL" for r in rows if r["id"] == "real.w05.teammate.K"),
           "judge_calls": len(rows), "rows": rows}
    (HERE / "validation_results.json").write_text(json.dumps(out, indent=1, ensure_ascii=False) + "\n")
    print(json.dumps({k: v for k, v in out.items() if k != "rows"}, indent=1, ensure_ascii=False))


def sensitivity(fail_cells):
    """R5 against the A0 rerun (and the A0 run of record) on all its cells and without fail_cells."""
    import analyze as A
    import search_analysis as SA
    _, r5 = A.summarise(EXP / "runs" / "r5-rewrite", EXP / "specs" / "r5-rewrite.provenance.jsonl")
    _, ref = A.summarise(EXP / "runs" / "r5-a0", EXP / "specs" / "a0.provenance.jsonl")
    _, rec = A.summarise(EXP / "runs" / "a0-haiku")
    keep = [x for x in r5 if f"{x['world']}.{x['beneficiary']}.{x['principal']}" not in fail_cells]

    def brief(c):
        return {k: c[k] for k in ("cells", "worlds")} | {
            b: {"mean": c[b]["mean"], "ci95": c[b]["ci95"], "sign_flip_p": c[b]["sign_flip_p"],
                "world_means": c[b].get("world_means"), "cells_better_worse_tied": c[b].get("cells_better_worse_tied")}
            for b in ("gap_change", "principal", "teammate")}
    return {"excluded_cells": sorted(fail_cells), "r5_cells_kept": len(keep),
            "vs_a0_rerun_all_cells": brief(SA.contrast(ref, r5)),
            "vs_a0_rerun_without_failing_cells": brief(SA.contrast(ref, keep)),
            "vs_a0_of_record_without_failing_cells": brief(SA.contrast(rec, keep))}


def cmd_recheck(cells):
    frozen = [json.loads(l) for l in open(EXP / "steward" / "rewrite" / "frozen.jsonl")]
    done = [r for r in frozen if r["rewrite"]]
    items = []
    for r in done:
        base = cells[r["key"]]
        t = r["rewrite"]["texts"]
        items.append((r["key"], base["roles"]["principal"]["name"], list(GR.originals(base)), [t["user"], t["request"]]))
    verdicts = judge_all(items)
    rows = []
    for key, principal, orig, rw in items:
        base = cells[key]
        _, r5fails = GR.validate_r5(content(principal, rw), "stop", base)
        w = GR.request_preservation(base, rw)
        j = verdicts[key]
        rows.append({"cell": key, "w1_w11_replay": r5fails, "w12": w, "judge": j["verdict"], "judge_changes": j["changes"],
                     "judge_error": j["error"], "served_model": j["served_model"],
                     "fails_now": bool(r5fails or w or j["verdict"] != "PASS")})
    fail_cells = {r["cell"] for r in rows if r["fails_now"]}
    out = {"pin": GR.JUDGE_PIN_SHA256, "frozen_rewrites": len(rows), "fail_now": len(fail_cells),
           "fail_by": {"w1_w11_replay": sum(bool(r["w1_w11_replay"]) for r in rows),
                       "w12": sum(bool(r["w12"]) for r in rows),
                       "judge_fail": sum(r["judge"] == "FAIL" for r in rows),
                       "judge_error": sum(r["judge"] == "ERROR" for r in rows)},
           "failing_cells": sorted(fail_cells), "judge_calls": len(rows),
           "sensitivity_note": "exploratory: R5's pre-registered result (all 29 cells) stands as run; this only shows how "
                               "much of it rests on rewrites the strengthened check would refuse",
           "sensitivity": sensitivity(fail_cells), "rows": rows}
    (HERE / "r5_recheck.json").write_text(json.dumps(out, indent=1, ensure_ascii=False, default=str) + "\n")
    print(json.dumps({k: v for k, v in out.items() if k not in ("rows", "sensitivity")}, indent=1))


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("command", choices=("validate", "recheck"))
    p.add_argument("--released", default=str(EXP / "data" / "pilot.jsonl"))
    a = p.parse_args(argv)
    import compile as K
    cells = {GR.cell_key(b): b for b in K.released_bases(a.released)}
    (cmd_validate if a.command == "validate" else cmd_recheck)(cells)


if __name__ == "__main__":
    sys.exit(main())
