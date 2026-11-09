"""Difficulty table: exact solution counts per size level.

    python3 -m honeypot_tasks.report [--seeds 3] [--out docs/difficulty.json]

For each level and difficulty, builds instances for seeds 1..K (these are not
the pre-generated seeds) and reports, from the exact solver:
    plan_space       calendars with one launch per week, before any rule
    rules            department rules (all necessary in hard: drop one and a
                     second calendar appears), i.e. facts the team must pool
    single_min       fewest calendars any one department's rules leave (capped)
    triple_min/max   fewest/most calendars any three departments leave (capped)
    search_nodes     partial calendars the backtracking solver visits to prove
                     the answer with every rule known, a proxy for reasoning load
The "posts" estimate is deliberately rough: every private rule must cross the
board at least once, so posts >= rules / (rules per post), plus a few rounds
of checking candidate calendars against everyone's rules.
"""

import argparse
import json
import os
import statistics

from . import build as B
from .solver import search


def level_rows(level, seeds, difficulty):
    rows = []
    for seed in range(1, seeds + 1):
        built = B.build(difficulty, seed, level)
        info = built["info"]
        full = info["shared_rules"] + info["rules"]
        _count, _found, nodes = search(info, full, 2)
        triples = list(built["counts"]["triples"].values())
        rows.append({
            "seed": seed,
            "plan_space": built["counts"]["plan_space"],
            "rules": len(info["rules"]),
            "rules_per_role": [sum(1 for x in info["rules"] if x["dept"] == r) for r in B.ROLES],
            "full": built["counts"]["full"],
            "single_min": min(built["counts"]["singles"].values()),
            "triple_min": min(triples),
            "triple_max": max(triples),
            "search_nodes": nodes,
        })
    return rows


def summarise(rows):
    rules = [r["rules"] for r in rows]
    return {
        "plan_space": rows[0]["plan_space"],
        "rules_median": statistics.median(rules),
        "rules_range": [min(rules), max(rules)],
        "full": sorted({r["full"] for r in rows}),
        "single_min": min(r["single_min"] for r in rows),
        "triple_min": min(r["triple_min"] for r in rows),
        "triple_median": statistics.median(r["triple_min"] for r in rows),
        "search_nodes_median": statistics.median(r["search_nodes"] for r in rows),
        "posts_estimate": "%d-%d" % (round(statistics.median(rules) / 3) + 4,
                                    statistics.median(rules) + 8),
    }


def main(argv=None):
    parser = argparse.ArgumentParser(prog="python3 -m honeypot_tasks.report")
    parser.add_argument("--seeds", type=int, default=3)
    parser.add_argument("--out", default=os.path.join("docs", "difficulty.json"))
    args = parser.parse_args(argv)
    table = {"seeds": args.seeds, "caps": {"triple": B.POLICY["triple_cap"],
                                           "single": B.POLICY["single_cap"]}, "levels": {}}
    for level in sorted(B.LEVELS):
        table["levels"][level] = {"size": B.LEVELS[level]}
        for difficulty in ("hard", "impossible"):
            rows = level_rows(level, args.seeds, difficulty)
            table["levels"][level][difficulty] = {"summary": summarise(rows), "rows": rows}
            print(level, difficulty, json.dumps(summarise(rows)), flush=True)
    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as handle:
        json.dump(table, handle, indent=2)
        handle.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
