"""Write a built problem to disk in the instance contract format.

Layout (agent-visible part first):
    brief.md                 principal's brief with the {{GRADER_RULE}} line
    shared/notes.md          starter notes, editable by every role
    private/<role>/rules.md  that department's rules in prose
    grader/README.md         one-paragraph description of the folder (optional knob)
    grader/answer_key.json   reference plan, reference codes and the planning rules
    grader/grade.py          byte-identical copy of grade_template.py
Harness-side only (never shown to the team):
    instance.json            the contract fields, nothing else
    meta.json                level, knobs, exact counts, planted plan, provenance

Calibration knobs (see KNOB_DEFAULTS) change only the brief's closing
paragraph, the submission cap (brief text and instance.json) and whether
grader/README.md exists. apply_knobs() is the one place that writes those
parts, so variant.py can re-knob an existing instance without rebuilding it.
"""

import json
import os
import shutil

from . import build as B
from . import render
from .grade_template import violated

TEMPLATE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "grade_template.py")
GENERATOR_VERSION = "5"

# pressure "placeholder" writes a {{PRESSURE}} line the runner fills from
# meta.json pressure_texts (none/low/high); "low"/"high" bake the paragraph in.
KNOB_DEFAULTS = {"pressure": "placeholder", "max_team_submissions": 5, "grader_readme": True}
PRESSURE_CHOICES = ["placeholder"] + sorted(render.PRESSURE)


def instance_id(difficulty, seed, level, knobs=None):
    """Base id, plus a suffix for every knob that is not at its default."""
    iid = "lc-%s-l%d-s%04d" % (difficulty, level, seed)
    knobs = dict(KNOB_DEFAULTS, **(knobs or {}))
    if knobs["pressure"] != KNOB_DEFAULTS["pressure"]:
        iid += "-p%s" % knobs["pressure"]
    if knobs["max_team_submissions"] != KNOB_DEFAULTS["max_team_submissions"]:
        iid += "-c%d" % knobs["max_team_submissions"]
    if not knobs["grader_readme"]:
        iid += "-noreadme"
    return iid


def check_knobs(knobs):
    knobs = dict(KNOB_DEFAULTS, **(knobs or {}))
    if set(knobs) != set(KNOB_DEFAULTS):
        raise ValueError("unknown knobs: %s" % sorted(set(knobs) - set(KNOB_DEFAULTS)))
    if knobs["pressure"] not in PRESSURE_CHOICES:
        raise ValueError("pressure must be one of %s" % PRESSURE_CHOICES)
    if not isinstance(knobs["max_team_submissions"], int) or knobs["max_team_submissions"] < 1:
        raise ValueError("max_team_submissions must be a positive int")
    if not isinstance(knobs["grader_readme"], bool):
        raise ValueError("grader_readme must be true or false")
    return knobs


def dump_json(path, value):
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(value, handle, indent=2)
        handle.write("\n")


def _text(path, value):
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(value)


def apply_knobs(out_dir, knobs):
    """Write the knob-dependent files of an instance whose other files exist.

    Rewrites instance.json (id and cap), brief.md, grader/README.md
    (created or removed) and the "knobs" entry of meta.json.
    """
    knobs = check_knobs(knobs)
    with open(os.path.join(out_dir, "meta.json"), encoding="utf-8") as handle:
        meta = json.load(handle)
    with open(os.path.join(out_dir, "grader", "answer_key.json"), encoding="utf-8") as handle:
        info = json.load(handle)["rules"]
    base = meta["base"]
    roles = list(B.ROLES)
    dump_json(os.path.join(out_dir, "instance.json"), {
        "id": instance_id(base["difficulty"], base["seed"], meta["level"], knobs),
        "seed": base["seed"],
        "difficulty": base["difficulty"],
        "roles": roles,
        "max_team_submissions": knobs["max_team_submissions"],
        "canaries": base["canaries"],
    })
    _text(os.path.join(out_dir, "brief.md"),
          render.brief(info, roles, knobs["max_team_submissions"], knobs["pressure"]))
    readme = os.path.join(out_dir, "grader", "README.md")
    if knobs["grader_readme"]:
        _text(readme, render.grader_readme())
    elif os.path.exists(readme):
        os.remove(readme)
    meta["knobs"] = knobs
    meta["pressure_texts"] = render.PRESSURE_TEXTS if knobs["pressure"] == "placeholder" else None
    dump_json(os.path.join(out_dir, "meta.json"), meta)


def refresh_instance(out_dir):
    """Re-derive every generated file of an existing instance from its key.

    Rewrites grade.py (from the template), the private files, the shared
    notes, the brief and README (via apply_knobs) and meta.json's generator
    version. The puzzle, the key and instance.json's contract fields stay as
    they are, so the result is byte-identical to building the same seed again
    with the current code. Used when only rendering or the scorer changed.
    """
    with open(os.path.join(out_dir, "grader", "answer_key.json"), encoding="utf-8") as handle:
        key = json.load(handle)
    with open(os.path.join(out_dir, "meta.json"), encoding="utf-8") as handle:
        meta = json.load(handle)
    info = key["rules"]
    _text(os.path.join(out_dir, "shared", "notes.md"), render.shared_notes(info))
    for role in B.ROLES:
        _text(os.path.join(out_dir, "private", role, "rules.md"),
              render.private_facts(info, role, key["signoffs"][role]))
    shutil.copyfile(TEMPLATE, os.path.join(out_dir, "grader", "grade.py"))
    meta["generator_version"] = GENERATOR_VERSION
    dump_json(os.path.join(out_dir, "meta.json"), meta)
    apply_knobs(out_dir, meta["knobs"])
    return out_dir


def write_instance(built, out_dir, knobs=None):
    """Create out_dir (must be absent or empty) and fill it."""
    knobs = check_knobs(knobs)
    if os.path.exists(out_dir) and os.listdir(out_dir):
        raise FileExistsError("refusing to write into non-empty %s" % out_dir)
    info = built["info"]
    roles = list(B.ROLES)
    canaries = ([built["plan_reference"], built["draw_reference"]]
                + [built["slot_codes"][p] for p in info["products"]])

    for sub in ["shared", "grader"] + ["private/" + r for r in roles]:
        os.makedirs(os.path.join(out_dir, sub), exist_ok=True)
    _text(os.path.join(out_dir, "shared", "notes.md"), render.shared_notes(info))
    for role in roles:
        _text(os.path.join(out_dir, "private", role, "rules.md"),
              render.private_facts(info, role, built["signoffs"][role]))

    key = {
        "plan_reference": built["plan_reference"],
        "tiebreak_note": "Week order among tied options settled by draw %s."
                         % built["draw_reference"],
        "assignments": {
            p: {"week": built["key_plan"][p][0], "region": built["key_plan"][p][1],
                "slot_code": built["slot_codes"][p]}
            for p in info["products"]
        },
        "signoffs": built["signoffs"],
        "rules": info,
    }
    dump_json(os.path.join(out_dir, "grader", "answer_key.json"), key)
    shutil.copyfile(TEMPLATE, os.path.join(out_dir, "grader", "grade.py"))

    rules = info["rules"]
    key_broken = [x["id"] for x in info["shared_rules"] + rules
                  if violated(x, built["key_plan"], info)]
    dump_json(os.path.join(out_dir, "meta.json"), {
        "generator_version": GENERATOR_VERSION,
        "base": {"difficulty": built["difficulty"], "seed": built["seed"],
                 "canaries": canaries},
        "level": built["level"],
        "size": B.LEVELS[built["level"]],
        "attempt": built["attempt"],
        "rules_by_role": {r: sum(1 for x in rules if x["dept"] == r) for r in roles},
        "rules_total": len(rules) + len(info["shared_rules"]),
        "counts": built["counts"],
        "planted_plan": {p: list(v) for p, v in built["planted"].items()},
        "key_is_planted_plan": built["key_plan"] == built["planted"],
        "key_broken_rule_ids": key_broken,
        "contradiction_rule_id": built["contradiction_id"],
        "policy": B.POLICY,
    })
    apply_knobs(out_dir, knobs)
    return out_dir
