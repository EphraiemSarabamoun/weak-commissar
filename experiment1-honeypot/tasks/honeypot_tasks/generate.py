"""Command line: generate one instance, or the whole pre-generated set.

    python3 -m honeypot_tasks.generate --difficulty hard --seed 7 --out DIR [--level 2]
        [--pressure placeholder|low|high] [--cap N] [--no-readme]
    python3 -m honeypot_tasks.generate --pregenerate [--root instances] [--levels 2 4] [--jobs 12]
    python3 -m honeypot_tasks.generate --refresh [--root instances]   # scorer/prose changed only

--out names the instance directory itself (created; must be absent or empty).
The pre-generated set uses the default knobs (write.KNOB_DEFAULTS); use
variant.py to re-knob it for calibration cells.
--pregenerate builds instances/<difficulty>/<id>/ for the recorded seeds
below and rewrites instances/MANIFEST.json from every instance present.
"""

import argparse
import json
import multiprocessing
import os
import sys
import time

from . import build as B
from .write import KNOB_DEFAULTS, instance_id, refresh_instance, write_instance

# The recorded seeds for the pre-generated set: 12 hard and 12 impossible at
# level 4. Fresh seeds after the HP-F1 fix (sign-off codes, accept/reject
# feedback, >= 1000 calendars per 3-department subset); the earlier level-2
# and level-4 sets are kept on the git tag pre-hpf1-instances. Level 2 cannot
# reach 1000 calendars per subset, so it is no longer pre-generated.
# Hard seeds 205 and 210 were dropped: neither finished building inside the
# 40-minute generation budget on 2026-11-08 (slow, not shown to be impossible).
PREGEN = {
    4: {"hard": [201, 202, 203, 204, 206, 207, 208, 209, 211, 212],
        "impossible": list(range(301, 313))},
}


def generate_one(difficulty, seed, out, level=B.DEFAULT_LEVEL, knobs=None):
    built = B.build(difficulty, seed, level)
    write_instance(built, out, knobs)
    return built


def _pregen_task(task):
    """Worker for the process pool: build and write one instance."""
    difficulty, seed, level, out = task
    start = time.time()
    built = generate_one(difficulty, seed, out, level)
    return {"id": os.path.basename(out), "difficulty": difficulty, "level": level,
            "seed": seed, "rules": len(built["info"]["rules"]),
            "counts": built["counts"], "seconds": round(time.time() - start, 1)}


def write_manifest(root):
    """MANIFEST.json listing every instance under root, from its meta.json."""
    entries = []
    for difficulty in ("hard", "impossible"):
        folder = os.path.join(root, difficulty)
        for name in sorted(os.listdir(folder)) if os.path.isdir(folder) else []:
            with open(os.path.join(folder, name, "meta.json"), encoding="utf-8") as handle:
                meta = json.load(handle)
            entries.append({"id": name, "path": os.path.join(difficulty, name),
                            "difficulty": difficulty, "level": meta["level"],
                            "seed": meta["base"]["seed"],
                            "rules": meta["rules_total"] - 1, "counts": meta["counts"]})
    with open(os.path.join(root, "MANIFEST.json"), "w", encoding="utf-8") as handle:
        json.dump({"instances": entries}, handle, indent=2)
        handle.write("\n")
    return entries


def pregenerate(root, levels=None, jobs=1):
    """Build the recorded seeds for `levels` (default: all in PREGEN)."""
    tasks = []
    for level in levels or sorted(PREGEN):
        for difficulty, seeds in PREGEN[level].items():
            for seed in seeds:
                out = os.path.join(root, difficulty, instance_id(difficulty, seed, level))
                if os.path.isfile(os.path.join(out, "meta.json")):
                    continue  # already built (resume after an interrupted run)
                tasks.append((difficulty, seed, level, out))
    if jobs > 1:
        with multiprocessing.Pool(jobs) as pool:
            results = pool.imap_unordered(_pregen_task, tasks)
            for row in results:
                print("%s  rules=%d  triples=%s  %ss" % (
                    row["id"], row["rules"], sorted(row["counts"]["triples"].values()),
                    row["seconds"]), flush=True)
    else:
        for task in tasks:
            row = _pregen_task(task)
            print("%s  rules=%d  %ss" % (row["id"], row["rules"], row["seconds"]), flush=True)
    return write_manifest(root)


def main(argv=None):
    parser = argparse.ArgumentParser(prog="python3 -m honeypot_tasks.generate")
    parser.add_argument("--difficulty", choices=["hard", "impossible"])
    parser.add_argument("--seed", type=int)
    parser.add_argument("--out")
    parser.add_argument("--level", type=int, default=B.DEFAULT_LEVEL, choices=sorted(B.LEVELS))
    parser.add_argument("--pressure", default=KNOB_DEFAULTS["pressure"])
    parser.add_argument("--cap", type=int, default=KNOB_DEFAULTS["max_team_submissions"])
    parser.add_argument("--no-readme", action="store_true")
    parser.add_argument("--pregenerate", action="store_true")
    parser.add_argument("--refresh", action="store_true",
                        help="re-derive grade.py, prose and brief of every instance under --root")
    parser.add_argument("--root", default="instances")
    parser.add_argument("--levels", type=int, nargs="*", help="pregenerate only these levels")
    parser.add_argument("--jobs", type=int, default=1, help="parallel builds for --pregenerate")
    args = parser.parse_args(argv)
    if args.refresh:
        from .validate import find_instances
        for root in find_instances([args.root]):
            print(refresh_instance(root))
        write_manifest(args.root)
        return 0
    if args.pregenerate:
        pregenerate(args.root, args.levels, args.jobs)
        return 0
    if args.difficulty is None or args.seed is None or args.out is None:
        parser.error("--difficulty, --seed and --out are required (or use --pregenerate)")
    knobs = {"pressure": args.pressure, "max_team_submissions": args.cap,
             "grader_readme": not args.no_readme}
    built = generate_one(args.difficulty, args.seed, args.out, args.level, knobs)
    print(json.dumps({"out": args.out, "counts": built["counts"]}, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
