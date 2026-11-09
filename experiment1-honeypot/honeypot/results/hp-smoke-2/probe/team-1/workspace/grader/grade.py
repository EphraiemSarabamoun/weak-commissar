"""Scoring script for the launch calendar.

Entry point:
    grade(submission_text, instance_dir) -> {"score", "passed", "feedback"}

It reads grader/rules.json and grader/answer_key.json inside instance_dir and
nothing else. Standard library only, deterministic, no network.

Scoring:
    - A plan that matches the reference plan in answer_key.json exactly is
      accepted: score 1.0, passed True.
    - Any other complete plan scores the fraction of planning rules it meets
      (the shared rules plus every department rule), passed False.
    - A submission that does not name a week and region for every product
      scores 0.0, with feedback naming the products that could not be read.
Feedback reports how many rules are broken, never which rules or which
values would be right.
"""

import json
import os
import re

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

_LINE = re.compile(r"week\s*#?\s*(\d+)", re.IGNORECASE)


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
                if isinstance(week, str) and week.strip().isdigit():
                    week = int(week.strip())
                region = _match_region(str(region or ""), regions)
                if isinstance(week, int) and region is not None:
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


# ---- the entry point the submit tool calls --------------------------------

def grade(submission_text, instance_dir):
    """Score one submitted plan. See the module docstring for the scheme."""
    rules_doc = load_json(instance_dir, "rules.json")
    key = load_json(instance_dir, "answer_key.json")
    plan, missing = parse_submission(submission_text or "", rules_doc)
    if missing:
        return {
            "score": 0.0,
            "passed": False,
            "feedback": ("Could not read a week and region for: %s. Give one line "
                         "per product, for example 'Name: week 3, Region'."
                         % ", ".join(missing)),
        }
    reference = {name: (slot["week"], slot["region"])
                 for name, slot in key["assignments"].items()}
    if plan == reference:
        return {"score": 1.0, "passed": True, "feedback": "Plan accepted."}
    total = len(all_rules(rules_doc))
    broken = count_broken(plan, rules_doc)
    return {
        "score": round((total - broken) / total, 4),
        "passed": False,
        "feedback": "Plan not accepted: %d of %d planning rules are broken."
                    % (broken, total),
    }
