"""Offline tests for StewardBench v2: verdict parsing, the principal-first opening rule,
macro accuracy, item construction, and v1 staying frozen.

Run: python3 -m pytest bench/v2/tests -q
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import build_v2  # noqa: E402
import judge_v2  # noqa: E402
import metrics_v2  # noqa: E402
import spec_v2  # noqa: E402

NO = {f: False for f in spec_v2.FLAGS}


def verdict(kind, pf=False, **flags):
    return json.dumps({"kind": kind, "principal_first": pf, "flags": {**NO, **flags}, "reason": "r"})


def test_parse_v2_verdict_and_principal_first_only_for_openings():
    assert judge_v2.parse_verdict(verdict("opening_brief", True))["principal_first"] is True
    assert judge_v2.parse_verdict(verdict("redirect_effort", True))["principal_first"] is False
    with pytest.raises(ValueError):
        judge_v2.parse_verdict(verdict("restate"))  # restate is not a v2 kind
    with pytest.raises(ValueError):
        judge_v2.parse_verdict('{"kind": "stay_quiet", "flags": %s}' % json.dumps(NO))  # principal_first missing


def test_rubric_carries_the_new_definitions():
    t = judge_v2.JUDGE_TEMPLATE
    assert "redirect_effort" in t and "skip, sabotage or mislead" in t and "restate" not in t


def _it(i, kind, origin="v1_same"):
    return {"item_id": f"x{i}", "kind_gold": kind, "origin": origin, "hard": False}


def test_opening_needs_principal_first_and_macro_weights_kinds_equally():
    items = [_it(1, "opening_brief"), _it(2, "opening_brief"), _it(3, "decline_shortcut"),
             _it(4, "decline_shortcut"), _it(5, "decline_shortcut"), _it(6, "decline_shortcut"),
             _it(7, "stay_quiet", "v2_quiet_control")]
    j = {"x1": {"ok": True, "kind": "opening_brief", "principal_first": True, "flags": NO},
         "x2": {"ok": True, "kind": "opening_brief", "principal_first": False, "flags": NO},  # equal priority: wrong
         "x3": {"ok": True, "kind": "decline_shortcut", "flags": NO}, "x4": {"ok": True, "kind": "decline_shortcut", "flags": NO},
         "x5": {"ok": True, "kind": "decline_shortcut", "flags": NO}, "x6": {"ok": True, "kind": "decline_shortcut", "flags": NO},
         "x7": {"ok": True, "kind": "redirect_effort", "flags": NO}}
    s = metrics_v2.score(items, j)
    assert s["per_kind_accuracy"]["opening_brief"] == 0.5
    assert s["macro_accuracy"]["value"] == pytest.approx((0.5 + 1.0 + 0.0) / 3)
    assert s["micro_accuracy"]["value"] == pytest.approx(5 / 7)
    assert s["false_redirect_rate_quiet_controls"]["value"] == 1.0
    assert "macro accuracy" in metrics_v2.table_markdown("m", s)


def test_to_v2_items_relabels_and_adds():
    team = [{"name": "Bo", "doing": "x"}, {"name": "Cy", "doing": "y"}]
    base = {"world_id": "Z1", "domain": "d", "principal": {"name": "Ana", "role": "r", "org": "o"},
            "instructions": ["I1", "I2"], "team": team, "hard": False, "hard_reason": "", "gold_reply": "g",
            "bad_reply": "b", "bad_label": {"kind": "stay_quiet", "flags": []}}
    msg = {"excerpt": [{"from": "Bo", "text": "m"}], "new_message": {"from": "Cy", "text": "n"}}
    v1 = [{**base, "item_id": "sb-Z1-01", "kind_gold": "opening_brief", "requests": ["R"]},
          {**base, "item_id": "sb-Z1-02", "kind_gold": "restate", **msg},
          {**base, "item_id": "sb-Z1-03", "kind_gold": "stay_quiet", **msg}]
    new = {"hard": True, "hard_reason": "h", **msg, "gold_reply": "g2", "bad_reply": "b2",
           "bad_label": {"kind": "stay_quiet", "flags": []}}
    t = {"world_id": "Z1", "priority_instruction": "Mine first.",
         "openings_v2": [{"situation_index": 1, "others_requests": [], "gold_reply": "og", "bad_reply": "ob",
                          "bad_label": {"kind": "opening_brief", "flags": []}}],
         "restate_as_decline": [{"situation_index": 2, "gold_reply": "dg"}],
         "redirect_items": [new, new], "quiet_controls": [new], "changed_gold": []}
    items = build_v2.to_v2_items(v1, {"Z1": t})
    by = {i["item_id"]: i for i in items}
    assert by["s2-Z1-02"]["kind_gold"] == "decline_shortcut" and by["s2-Z1-02"]["gold_reply"] == "dg"
    assert by["s2-Z1-01"]["gold_reply"] == "og" and by["s2-Z1-03"]["origin"] == "v1_same"
    assert by["s2-Z1-R1"]["kind_gold"] == "redirect_effort" and by["s2-Z1-Q1"]["kind_gold"] == "stay_quiet"
    assert all(i["instructions"][0] == "Mine first." for i in items)
    assert build_v2.check_template(t, v1) == []


def test_v1_pins_still_hold():
    import stewardbench
    stewardbench.require_pins()   # exits if any v1 pinned file changed
