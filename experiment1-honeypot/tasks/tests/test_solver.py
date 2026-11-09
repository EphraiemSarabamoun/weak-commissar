"""The exact counter agrees with brute-force enumeration.

The solver prunes with partial-plan checks, so it is cross-checked here
against a dumb enumerator that scores every complete calendar with the same
violated() the grader uses. Level 1 keeps the brute force to 174,960 plans.
"""

import itertools
import unittest
from unittest import mock

from honeypot_tasks import build as B
from honeypot_tasks.grade_template import violated
from honeypot_tasks.solver import count_solutions, plan_space, solutions


def brute_force(info, rules):
    """Every complete calendar with distinct weeks, scored rule by rule."""
    products = info["products"]
    count = 0
    for weeks in itertools.permutations(range(1, info["weeks"] + 1), len(products)):
        for regions in itertools.product(info["regions"], repeat=len(products)):
            plan = {p: (w, r) for p, w, r in zip(products, weeks, regions)}
            if not any(violated(rule, plan, info) for rule in rules):
                count += 1
    return count


class SolverAgreesWithBruteForce(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        # Level 1 cannot meet the shipped 1000-calendar subset floor; the
        # counter cross-check only needs some level-1 rule set.
        with mock.patch.dict(B.POLICY, {"min_triple_solutions": 2}):
            cls.built = B.build("hard", 3, level=1)
        cls.info = cls.built["info"]

    def test_plan_space_formula(self):
        self.assertEqual(brute_force(self.info, self.info["shared_rules"]),
                         plan_space(self.info))
        self.assertEqual(count_solutions(self.info, self.info["shared_rules"], 10 ** 9),
                         plan_space(self.info))

    def test_full_and_subset_counts(self):
        info = self.info
        shared = info["shared_rules"]
        cases = {"full": info["rules"]}
        for role in B.ROLES:
            cases["without_" + role] = [x for x in info["rules"] if x["dept"] != role]
            cases["only_" + role] = [x for x in info["rules"] if x["dept"] == role]
        for name, rules in cases.items():
            with self.subTest(case=name):
                self.assertEqual(count_solutions(info, shared + rules, 10 ** 9),
                                 brute_force(info, shared + rules))

    def test_cap_is_respected(self):
        self.assertEqual(count_solutions(self.info, self.info["shared_rules"], 17), 17)

    def test_unique_solution_is_planted_plan(self):
        found = solutions(self.info, self.info["shared_rules"] + self.info["rules"], 5)
        self.assertEqual(found, [self.built["planted"]])


if __name__ == "__main__":
    unittest.main()
