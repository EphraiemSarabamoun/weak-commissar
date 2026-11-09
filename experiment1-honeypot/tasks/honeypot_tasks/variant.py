"""Re-knob an existing instance for calibration, without rebuilding the puzzle.

    python3 -m honeypot_tasks.variant SRC --out DST [--pressure low|high]
        [--cap N] [--no-readme | --readme]

Copies SRC to DST and rewrites only the knob-dependent parts (brief closing
paragraph, submission cap, grader/README.md presence, instance id suffix).
The rules, the key and the reference codes are untouched, so the same puzzle
can sit in several calibration cells. SRC may be a directory of instances:
every instance under it is copied to DST/<new id>/.
"""

import argparse
import json
import os
import shutil
import sys

from .validate import find_instances
from .write import KNOB_DEFAULTS, apply_knobs, check_knobs, instance_id


def make_variant(src, dst_parent, knobs, flat_dst=None):
    """Copy one instance and apply knobs. Returns the new directory."""
    with open(os.path.join(src, "meta.json"), encoding="utf-8") as handle:
        meta = json.load(handle)
    knobs = check_knobs(dict(meta.get("knobs", KNOB_DEFAULTS), **knobs))
    base = meta["base"]
    dst = flat_dst or os.path.join(
        dst_parent, instance_id(base["difficulty"], base["seed"], meta["level"], knobs))
    if os.path.exists(dst) and os.listdir(dst):
        raise FileExistsError("refusing to write into non-empty %s" % dst)
    shutil.copytree(src, dst, ignore=shutil.ignore_patterns("__pycache__"),
                    dirs_exist_ok=True)
    apply_knobs(dst, knobs)
    return dst


def main(argv=None):
    parser = argparse.ArgumentParser(prog="python3 -m honeypot_tasks.variant")
    parser.add_argument("src")
    parser.add_argument("--out", required=True)
    parser.add_argument("--pressure")
    parser.add_argument("--cap", type=int)
    readme = parser.add_mutually_exclusive_group()
    readme.add_argument("--no-readme", dest="readme", action="store_false", default=None)
    readme.add_argument("--readme", dest="readme", action="store_true")
    args = parser.parse_args(argv)
    knobs = {}
    if args.pressure is not None:
        knobs["pressure"] = args.pressure
    if args.cap is not None:
        knobs["max_team_submissions"] = args.cap
    if args.readme is not None:
        knobs["grader_readme"] = args.readme
    if os.path.isfile(os.path.join(args.src, "instance.json")):
        print(make_variant(args.src, None, knobs, flat_dst=args.out))
        return 0
    for src in find_instances([args.src]):
        print(make_variant(src, args.out, knobs))
    return 0


if __name__ == "__main__":
    sys.exit(main())
