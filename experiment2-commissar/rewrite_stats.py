"""Rewrite statistics for a frozen R5-type arm (the prereg's "fact and request preservation" secondaries): attempts,
failures by rule, W13 judge calls and verdicts, coverage, attempts per cell, the length ratio of the frozen requests,
added priority guidance, changed kickoffs, and how many frozen cells are byte-identical to their originals.

Reads only the arm's attempts log and frozen file plus the released bases (for the original texts).
Usage (from experiments/commissar, python3.12 with castra on PYTHONPATH):
  python3.12 rewrite_stats.py steward/r5ft/attempts.jsonl steward/r5ft/frozen.jsonl --json r5ft-rewrite-stats.json
"""
import argparse
import collections
import json
import pathlib
import statistics as st
import sys

EXP = pathlib.Path(__file__).resolve().parent
sys.path[:0] = [str(EXP), str(EXP / "steward")]


def rule(failure):
    """'W8' from a failure string such as 'W8: ...'."""
    return failure.split(":")[0].split(" ")[0]


def stats(attempt_rows, frozen, bases):
    import gen_rewrite as GR
    tries = [r for r in attempt_rows if "failures" in r]
    judged = [r["judge"] for r in tries if r.get("judge")]
    by_rule = collections.Counter(x for r in tries for x in {rule(f) for f in r["failures"]})
    done = [r for r in frozen if r["rewrite"]]
    orig = {k: GR.originals(b) for k, b in bases.items()}
    # (kickoff + request) length over the originals' (kickoff + request), as r5v22-rewrite-stats.json reports it
    ratios = [(len(r["rewrite"]["texts"]["user"]) + len(r["rewrite"]["texts"]["request"]))
              / (len(orig[r["key"]][0]) + len(orig[r["key"]][1])) for r in done]

    def guided(text):
        return bool(GR.GUIDANCE.search(text))
    return {"attempts": len(tries), "transport_errors": sum("transport_error" in r for r in attempt_rows),
            "attempts_accepted": sum(not r["failures"] for r in tries),
            "attempts_with_rule_failure": dict(sorted(by_rule.items())),
            "judge_calls": len(judged),
            "judge_verdicts": dict(collections.Counter(j.get("verdict") or "ERROR" for j in judged)),
            "judge_served_models": sorted({j.get("served_model") for j in judged if j.get("served_model")}),
            "response_models": sorted({r["response_model"] for r in tries}),
            "cells": len(frozen), "cells_rewritten": len(done),
            "missing": [r["key"] for r in frozen if not r["rewrite"]],
            "attempts_per_cell": {r["key"]: r["attempts_used"] for r in frozen},
            "accepted_at_attempt": dict(sorted(collections.Counter(str(r["rewrite"]["attempt"]) for r in done).items(),
                                               key=lambda kv: int(kv[0]))),
            "length_ratio": ratios and {"min": round(min(ratios), 3), "max": round(max(ratios), 3),
                                        "mean": round(st.mean(ratios), 3)},
            "adds_priority_guidance": sum(guided(r["rewrite"]["texts"]["user"] + " " + r["rewrite"]["texts"]["request"])
                                          and not guided(" ".join(orig[r["key"]])) for r in done),
            "kickoff_changed": sum(r["rewrite"]["texts"]["user"] != orig[r["key"]][0] for r in done),
            "byte_identical": {"request": sum(r["rewrite"]["texts"]["request"].strip() == orig[r["key"]][1].strip()
                                              for r in done),
                               "kickoff": sum(r["rewrite"]["texts"]["user"].strip() == orig[r["key"]][0].strip()
                                              for r in done),
                               "both": sum(r["rewrite"]["texts"]["request"].strip() == orig[r["key"]][1].strip()
                                           and r["rewrite"]["texts"]["user"].strip() == orig[r["key"]][0].strip()
                                           for r in done),
                               "of": len(done)}}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("attempts")
    ap.add_argument("frozen")
    ap.add_argument("--json")
    a = ap.parse_args(argv)
    import compile as K
    import gen_rewrite as GR
    bases = {GR.cell_key(b): b for b in K.released_bases(EXP / "data" / "pilot.jsonl")}
    rows = [json.loads(l) for l in open(a.attempts)]
    frozen = [json.loads(l) for l in open(a.frozen)]
    text = json.dumps(stats(rows, frozen, bases), indent=1)
    if a.json:
        pathlib.Path(a.json).write_text(text + "\n")
    print(text)


if __name__ == "__main__":
    main()
