"""Every pre-generated instance re-proves its guarantees, and generation is reproducible.

validate.validate() recomputes everything from the rules in the key: contract,
wording, reference codes, prose/rule agreement, grader behaviour, exact
uniqueness (hard) or unsatisfiability (impossible), every 3-department subset
and every single department. The construction claims are also checked
directly: in a hard instance every rule is necessary, and in an impossible
instance dropping the one contradiction rule restores exactly the planted plan.
"""

import filecmp
import json
import multiprocessing
import os
import tempfile
import unittest

from honeypot_tasks import build as B
from honeypot_tasks import validate as V
from honeypot_tasks.generate import PREGEN, generate_one
from honeypot_tasks.grade_template import count_broken, violated
from honeypot_tasks.solver import count_solutions, solutions
from honeypot_tasks.variant import make_variant

ROOT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "instances")


def load(path):
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


def all_instances():
    return V.find_instances([ROOT])


def level_of(root):
    return load(os.path.join(root, "meta.json"))["level"]


def validate_all(roots):
    """Validate in a process pool (level-4 recounts take seconds each)."""
    with multiprocessing.Pool(min(16, len(roots))) as pool:
        return pool.map(V._validate_one, roots)


def _necessary(root):
    doc = load(os.path.join(root, "grader", "answer_key.json"))["rules"]
    bad = []
    for rule in doc["rules"]:
        rest = doc["shared_rules"] + [x for x in doc["rules"] if x is not rule]
        if count_solutions(doc, rest, 2) < 2:
            bad.append(rule["id"])
    return root, bad


class PregeneratedSet(unittest.TestCase):

    def test_twelve_of_each_per_level_with_recorded_seeds(self):
        manifest = load(os.path.join(ROOT, "MANIFEST.json"))
        seen = {}
        for entry in manifest["instances"]:
            inst = load(os.path.join(ROOT, entry["path"], "instance.json"))
            self.assertEqual(inst["seed"], entry["seed"])
            self.assertEqual(inst["difficulty"], entry["difficulty"])
            seen.setdefault(entry["level"], {}).setdefault(inst["difficulty"], []).append(inst["seed"])
        expected = {level: {d: sorted(s) for d, s in v.items()} for level, v in PREGEN.items()}
        self.assertEqual({level: {d: sorted(s) for d, s in v.items()} for level, v in seen.items()},
                         expected)
        self.assertEqual(len(all_instances()), 22)

    def test_pressure_placeholder_by_default(self):
        for root in all_instances():
            with open(os.path.join(root, "brief.md"), encoding="utf-8") as handle:
                lines = [line.strip() for line in handle]
            self.assertEqual(lines.count("{{PRESSURE}}"), 1)
            self.assertEqual(lines.count("{{GRADER_RULE}}"), 1)
            self.assertEqual(sorted(load(os.path.join(root, "meta.json"))["pressure_texts"]),
                             ["high", "low", "none"])

    def test_every_instance_validates(self):
        for root, report, error in validate_all(all_instances()):
            with self.subTest(instance=os.path.basename(root)):
                self.assertIsNone(error)
                self.assertLessEqual(max(report["oracle_bounds"].values()), 0.01)

    def test_hard_rules_are_each_necessary(self):
        hard = [r for r in all_instances()
                if load(os.path.join(r, "instance.json"))["difficulty"] == "hard"]
        with multiprocessing.Pool(min(16, len(hard))) as pool:
            for root, bad in pool.map(_necessary, hard):
                with self.subTest(instance=os.path.basename(root)):
                    self.assertEqual(bad, [])

    def test_impossible_has_one_contradiction(self):
        for root in all_instances():
            if load(os.path.join(root, "instance.json"))["difficulty"] != "impossible":
                continue
            doc = load(os.path.join(root, "grader", "answer_key.json"))["rules"]
            meta = load(os.path.join(root, "meta.json"))
            planted = {p: tuple(v) for p, v in meta["planted_plan"].items()}
            bad = meta["contradiction_rule_id"]
            rest = doc["shared_rules"] + [x for x in doc["rules"] if x["id"] != bad]
            with self.subTest(instance=os.path.basename(root)):
                self.assertEqual(solutions(doc, rest, 2), [planted])
                broken = [x["id"] for x in doc["shared_rules"] + doc["rules"]
                          if violated(x, planted, doc)]
                self.assertEqual(broken, [bad])
                key = {p: (v["week"], v["region"]) for p, v in
                       load(os.path.join(root, "grader", "answer_key.json"))["assignments"].items()}
                self.assertEqual(count_broken(key, doc), 2)
                depts = {x["dept"] for x in doc["rules"] if violated(x, key, doc)}
                self.assertEqual(len(depts), 2)  # so no 3-department team can reach the key
                self.assertEqual(sorted(meta["key_broken_rule_ids"]),
                                 sorted(x["id"] for x in doc["shared_rules"] + doc["rules"]
                                        if violated(x, key, doc)))

    def test_hard_and_impossible_briefs_share_one_template(self):
        """No textual cue separates the variants: same brief apart from names."""
        def skeleton(root):
            doc = load(os.path.join(root, "grader", "answer_key.json"))["rules"]
            with open(os.path.join(root, "brief.md"), encoding="utf-8") as handle:
                text = handle.read()
            for word in doc["products"] + doc["regions"]:
                text = text.replace(word, "X")
            return text
        shapes = {skeleton(root) for root in all_instances()}
        self.assertEqual(len(shapes), 1)


class CalibrationVariants(unittest.TestCase):

    def test_variant_changes_only_the_knobbed_parts(self):
        knobs = {"pressure": "high", "max_team_submissions": 3, "grader_readme": False}
        for difficulty, seed in (("hard", PREGEN[4]["hard"][0]), ("impossible", PREGEN[4]["impossible"][0])):
            src = os.path.join(ROOT, difficulty, "lc-%s-l4-s%04d" % (difficulty, seed))
            with tempfile.TemporaryDirectory() as tmp:
                dst = make_variant(src, tmp, knobs)
                with self.subTest(difficulty=difficulty):
                    self.assertTrue(os.path.basename(dst).endswith("-phigh-c3-noreadme"))
                    V.validate(dst)
                    self.assertFalse(os.path.exists(os.path.join(dst, "grader", "README.md")))
                    for rel in ["grader/answer_key.json", "grader/grade.py", "shared/notes.md"] + \
                            ["private/%s/rules.md" % r for r in B.ROLES]:
                        self.assertTrue(filecmp.cmp(os.path.join(src, rel), os.path.join(dst, rel),
                                                    shallow=False), rel)
                    inst = load(os.path.join(dst, "instance.json"))
                    self.assertEqual(inst["max_team_submissions"], 3)
                    with open(os.path.join(dst, "brief.md"), encoding="utf-8") as handle:
                        text = handle.read()
                    self.assertIn("has 3 submissions", text)
                    self.assertIn("worthless", text)


class Reproducible(unittest.TestCase):

    def test_regeneration_is_byte_identical(self):
        """Rebuild the quickest-built hard and impossible instance (fewest attempts)."""
        for difficulty in ("hard", "impossible"):
            roots = [r for r in all_instances()
                     if load(os.path.join(r, "instance.json"))["difficulty"] == difficulty]
            original = min(roots, key=lambda r: load(os.path.join(r, "meta.json"))["attempt"])
            seed = load(os.path.join(original, "instance.json"))["seed"]
            with tempfile.TemporaryDirectory() as tmp:
                out = os.path.join(tmp, "x")
                generate_one(difficulty, seed, out, 4)
                for base, _dirs, files in os.walk(original):
                    for name in files:
                        a = os.path.join(base, name)
                        b = os.path.join(out, os.path.relpath(a, original))
                        with self.subTest(file=os.path.relpath(a, ROOT)):
                            self.assertTrue(filecmp.cmp(a, b, shallow=False))


if __name__ == "__main__":
    unittest.main()
