"""Exact solution counting for launch-calendar rule sets.

The rule semantics come from grade_template.py (the file every instance ships
as grader/grade.py), so the counter and the scorer cannot disagree about what
a rule means. This module adds only the search: depth-first backtracking over
products, with one launch per week enforced natively and every other rule
checked as soon as its products are placed.

All counts are exact up to a cap: count_solutions(..., cap=c) returns
min(true count, c), and stops searching once it reaches c.
"""

from .grade_template import scope, violated


def _prepare(info, rules):
    """Order the products, filter their domains, and assign each rule a depth.

    Returns (products_in_search_order, domains, checks_at_depth). A rule naming
    one product only filters that product's domain up front. Products are then
    searched fail-first: smallest filtered domain first, ties broken by how
    many multi-product rules mention the product. A rule naming several
    products is checked at the depth where its last product is placed; a rule
    over all products is checked at every depth (each such rule is monotone,
    see violated()). The order changes only speed, never the count.
    """
    names = info["products"]
    unary = {p: [] for p in names}
    multi = []
    glob = []
    for rule in rules:
        if rule["type"] == "one_per_week":
            continue  # enforced by the search itself
        named = scope(rule)
        if named is None:
            glob.append(rule)
        elif len(named) == 1:
            unary[named[0]].append(rule)
        else:
            multi.append(rule)
    domain_of = {}
    for p in names:
        allowed = []
        for week in range(1, info["weeks"] + 1):
            for region in info["regions"]:
                trial = {p: (week, region)}
                if not any(violated(rule, trial, info) for rule in unary[p]):
                    allowed.append((week, region))
        domain_of[p] = allowed
    degree = {p: sum(1 for rule in multi if p in scope(rule)) for p in names}
    products = sorted(names, key=lambda p: (len(domain_of[p]), -degree[p], p))
    order = {p: i for i, p in enumerate(products)}
    checks = [list(glob) for _ in products]
    for rule in multi:
        checks[max(order[p] for p in scope(rule))].append(rule)
    return products, [domain_of[p] for p in products], checks


def search(info, rules, cap, collect=False):
    """Count (and optionally collect) plans meeting every rule, up to cap.

    Returns (count, collected_plans, nodes_visited). nodes_visited is the
    number of partial plans the search touched, a rough measure of how much
    trial and error the rule set demands.
    """
    products, domains, checks = _prepare(info, rules)
    plan = {}
    used = set()
    found = []
    count = [0]
    nodes = [0]

    def place(depth):
        nodes[0] += 1
        if depth == len(products):
            count[0] += 1
            if collect:
                found.append(dict(plan))
            return count[0] >= cap
        name = products[depth]
        for week, region in domains[depth]:
            if week in used:
                continue
            plan[name] = (week, region)
            used.add(week)
            if not any(violated(rule, plan, info) for rule in checks[depth]):
                if place(depth + 1):
                    used.discard(week)
                    del plan[name]
                    return True
            used.discard(week)
            del plan[name]
        return False

    place(0)
    return count[0], found, nodes[0]


def count_solutions(info, rules, cap):
    """min(number of plans meeting every rule, cap)."""
    return search(info, rules, cap)[0]


def solutions(info, rules, limit):
    """Up to `limit` plans meeting every rule, in search order."""
    return search(info, rules, limit, collect=True)[1]


def plan_space(info):
    """Number of plans with one launch per week and any region: P(W, N) * R^N."""
    weeks, n, r = info["weeks"], len(info["products"]), len(info["regions"])
    total = 1
    for i in range(n):
        total *= weeks - i
    return total * r ** n
