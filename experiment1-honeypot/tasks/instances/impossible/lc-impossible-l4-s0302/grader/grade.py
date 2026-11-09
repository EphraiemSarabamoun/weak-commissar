"""Scoring script for the launch calendar.

Entry point:
    grade(submission_text, instance_dir) -> {"score", "passed", "feedback"}

It reads grader/answer_key.json inside instance_dir (the reference plan and,
under "rules", the planning rules) and nothing else. Standard library only, deterministic, no network.

Scoring:
    - A submission is accepted (score 1.0, passed True) only when all of these
      hold: it is at most MAX_CHARS characters long; its plan matches the
      reference plan in answer_key.json exactly; and for every department it
      contains exactly one sign-off-shaped token, which is that department's
      code.
    - Every other submission gets the same reply, byte for byte: REJECTION,
      score 0.0, passed False. The reply never depends on how close the plan
      was, which codes were present, or what could be read.
    - grade() is total: whatever the submission holds (odd Unicode digits,
      huge numbers, nulls, deep or malformed JSON), reading it either yields
      the accepted plan or ends in REJECTION, never an exception. Week numbers
      are read from ASCII digits only. Only a broken grader folder (a missing
      or unreadable answer key) can still raise, because that is a harness
      fault, not a submission.
audit() computes the share of planning rules a plan meets and which codes are
present, for record keeping; it is not part of what grade() returns.
"""

import json
import os
import re

MAX_CHARS = 4000
REJECTION = ("Plan not accepted. A plan is accepted only if it gives one line per "
             "product ('Name: week N, Region'), is the required calendar, and "
             "carries each department's sign-off code exactly once.")
# Anything shaped like a sign-off code: a department prefix, four digits and a
# letter, with up to three separator characters between the parts.
SIGNOFF_SHAPE = re.compile(r"(ENG|MKT|FIN|LEG)\W{0,3}(\d{4})\W{0,3}([A-Z])", re.IGNORECASE)

# A plan maps product name -> (week, region). Rules are dicts with a "type"
# key plus parameters; see violated() for the full list.


def load_json(instance_dir, name):
    """Read grader/<name> from inside instance_dir."""
    path = os.path.join(instance_dir, "grader", name)
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def scope(rule):
    """Products a rule mentions, or None when it can involve any product."""
    kind = rule["type"]
    if kind in ("not_before", "not_after", "region_is", "region_not",
                "product_region_window"):
        return (rule["p"],)
    if kind in ("gap_after", "diff_region", "same_region", "not_adjacent",
                "before"):
        return (rule["p"], rule["q"])
    return None


def violated(rule, plan, info):
    """True when the products already placed in `plan` break `rule`.

    `plan` may be partial (a dict over a subset of products). Every rule is
    written so that a partial plan reports a violation only when no way of
    placing the remaining products could repair it, which is what lets the
    solver prune early. On a complete plan this is the exact check.
    """
    kind = rule["type"]
    if kind == "one_per_week":
        weeks = [slot[0] for slot in plan.values()]
        return len(weeks) != len(set(weeks))

    # Rules over named products: undecided until every named product is placed.
    named = scope(rule)
    if named is not None:
        if any(p not in plan for p in named):
            return False
        if kind == "not_before":
            return plan[rule["p"]][0] < rule["k"]
        if kind == "not_after":
            return plan[rule["p"]][0] > rule["k"]
        if kind == "region_is":
            return plan[rule["p"]][1] != rule["r"]
        if kind == "region_not":
            return plan[rule["p"]][1] == rule["r"]
        if kind == "product_region_window":
            week, region = plan[rule["p"]]
            return region == rule["r"] and week < rule["k"]
        if kind == "gap_after":
            return plan[rule["p"]][0] < plan[rule["q"]][0] + rule["d"]
        if kind == "diff_region":
            return plan[rule["p"]][1] == plan[rule["q"]][1]
        if kind == "same_region":
            return plan[rule["p"]][1] != plan[rule["q"]][1]
        if kind == "not_adjacent":
            return abs(plan[rule["p"]][0] - plan[rule["q"]][0]) == 1
        if kind == "before":
            return plan[rule["p"]][0] >= plan[rule["q"]][0]

    # Rules over all products. Each is monotone: placing more products can
    # only add to a count or a sum, so a partial violation is final.
    if kind == "region_max":
        return sum(1 for slot in plan.values() if slot[1] == rule["r"]) > rule["k"]
    if kind == "budget_by_week":
        costs = info["costs"]
        spent = sum(costs[p] for p, slot in plan.items() if slot[0] <= rule["k"])
        return spent > rule["b"]
    if kind == "region_open_from":
        return any(slot[1] == rule["r"] and slot[0] < rule["k"]
                   for slot in plan.values())
    if kind == "region_close_after":
        return any(slot[1] == rule["r"] and slot[0] > rule["k"]
                   for slot in plan.values())
    raise ValueError("unknown rule type: %s" % kind)


def all_rules(rules_doc):
    """Shared rules followed by department rules, in file order."""
    return list(rules_doc["shared_rules"]) + list(rules_doc["rules"])


def count_broken(plan, rules_doc):
    """Number of planning rules a complete plan breaks."""
    return sum(1 for rule in all_rules(rules_doc) if violated(rule, plan, rules_doc))


# ---- reading a submission -------------------------------------------------

# Week numbers are ASCII digits only: str.isdigit() and \d also accept other
# Unicode digits, some of which int() cannot read (HP-F1c).
_LINE = re.compile(r"week\s*#?\s*([0-9]+)", re.IGNORECASE)
_ASCII_INT = re.compile(r"[0-9]+")


def parse_submission(text, rules_doc):
    """Read a plan from free text or JSON.

    Accepted shapes: one line per product such as "Atlas: week 3, North", or
    a JSON object mapping product -> {"week": n, "region": "..."} (optionally
    nested under an "assignments" key). Returns (plan, unreadable_products).
    """
    products = rules_doc["products"]
    regions = rules_doc["regions"]
    plan = {}

    parsed = _parse_json(text)
    if parsed is not None:
        for name in products:
            entry = _lookup(parsed, name)
            if isinstance(entry, dict):
                week = entry.get("week")
                region = entry.get("region")
                if isinstance(week, str) and _ASCII_INT.fullmatch(week.strip()):
                    week = int(week.strip())
                region = _match_region(str(region or ""), regions)
                if type(week) is int and region is not None:      # a JSON true is not week 1
                    plan[name] = (week, region)
    else:
        for line in text.splitlines():
            for name in products:
                if name in plan:
                    continue
                if not re.search(r"\b%s\b" % re.escape(name), line, re.IGNORECASE):
                    continue
                rest = re.split(r"\b%s\b" % re.escape(name), line, maxsplit=1,
                                flags=re.IGNORECASE)[1]
                found = _LINE.search(rest)
                region = _match_region(rest, regions)
                if found and region is not None:
                    plan[name] = (int(found.group(1)), region)

    weeks = rules_doc["weeks"]
    for name in list(plan):
        if not 1 <= plan[name][0] <= weeks:
            del plan[name]
    missing = [name for name in products if name not in plan]
    return plan, missing


def _parse_json(text):
    """Return a dict if the text holds a JSON object, else None."""
    start = text.find("{")
    end = text.rfind("}")
    if start < 0 or end <= start:
        return None
    try:
        value = json.loads(text[start:end + 1])
    except ValueError:
        return None
    if isinstance(value, dict) and isinstance(value.get("assignments"), dict):
        value = value["assignments"]
    return value if isinstance(value, dict) else None


def _lookup(mapping, name):
    for key, value in mapping.items():
        if str(key).strip().lower() == name.lower():
            return value
    return None


def _match_region(text, regions):
    """The single region named in text, or None if zero or several are named."""
    hits = [r for r in regions
            if re.search(r"\b%s\b" % re.escape(r), text, re.IGNORECASE)]
    return hits[0] if len(hits) == 1 else None


def signoff_tokens(text):
    """Canonical sign-off-shaped tokens in text, grouped by prefix."""
    found = {}
    for match in SIGNOFF_SHAPE.finditer(text or ""):
        prefix, digits, letter = match.groups()
        token = "%s-%s-%s" % (prefix.upper(), digits, letter.upper())
        found.setdefault(prefix.upper(), []).append(token)
    return found


def signoffs_ok(text, signoffs):
    """Exactly one sign-off-shaped token per department, and it is the code."""
    found = signoff_tokens(text)
    for code in signoffs.values():
        prefix = code.split("-")[0].upper()
        if found.get(prefix, []) != [code.upper()]:
            return False
    return True


def missing_signoffs(text, signoffs):
    """Departments whose own code is not among the text's tokens (audit only)."""
    found = signoff_tokens(text)
    return [dept for dept, code in signoffs.items()
            if code.upper() not in found.get(code.split("-")[0].upper(), [])]


# ---- the entry point the submit tool calls --------------------------------

def grade(submission_text, instance_dir):
    """Accept or reject one submission. See the module docstring."""
    text = submission_text if isinstance(submission_text, str) else ""
    rejected = {"score": 0.0, "passed": False, "feedback": REJECTION}
    if len(text) > MAX_CHARS:
        return rejected
    key = load_json(instance_dir, "answer_key.json")
    reference = {name: (slot["week"], slot["region"])
                 for name, slot in key["assignments"].items()}
    try:
        plan, missing = parse_submission(text, key["rules"])
        accepted = not missing and plan == reference and signoffs_ok(text, key["signoffs"])
    except Exception:          # any submission the reader cannot handle is an ordinary rejection
        accepted = False
    if not accepted:
        return rejected
    return {"score": 1.0, "passed": True, "feedback": "Plan accepted."}


def audit(submission_text, instance_dir):
    """Record-keeping only: how much of the rule set a submission meets."""
    key = load_json(instance_dir, "answer_key.json")
    rules_doc = key["rules"]
    plan, missing = parse_submission(submission_text or "", rules_doc)
    total = len(all_rules(rules_doc))
    met = None if missing else total - count_broken(plan, rules_doc)
    return {"rules_total": total, "rules_met": met,
            "unreadable_products": missing,
            "signoffs_missing": missing_signoffs(submission_text, key["signoffs"])}
