"""Build StewardBench v2 items from the frozen v1 items plus the v2 templates.

Inputs:  bench/items.jsonl (v1, frozen), v2/templates/worlds_v2_*.json (per AUTHORING_v2.md),
         v2/templates/hand_replies_v2.json (replies written and labelled by hand)
Outputs: v2/items_v2.jsonl, v2/manifest_v2.json, v2/validation_v2.jsonl

What changes per v1 item (origin field):
  v1_opening   opening_brief, v2 gold reply (principal-first), others_requests listed
  v1_restate   relabelled decline_shortcut, v2 gold reply
  v1_changed   the authors' changed_gold entries, new kind
  v1_same      kind unchanged
and new items: v2_redirect (redirect_effort) and v2_quiet_control (stay_quiet: one honest
attempt on someone else's request, truthful report, back to the principal's work).
Every item's instructions gain the world's priority line first, as v3 training rows do.
"""

from __future__ import annotations

import collections
import glob
import json
import random
import sys
from pathlib import Path

import spec_v2
import build_items   # v1 checks: operae names, collisions, normalisation (frozen)
import render

common = spec_v2.common


def load_v2_templates() -> dict:
    out = {}
    for path in sorted(glob.glob(str(spec_v2.TEMPLATES_DIR / "worlds_v2_*.json"))):
        for w in json.loads(Path(path).read_text()):
            out[w["world_id"]] = w
    return out


def check_template(w: dict, v1_world_items: list[dict]) -> list[str]:
    errs, wid = [], w["world_id"]
    kinds = {int(it["item_id"].rsplit("-", 1)[1]): it["kind_gold"] for it in v1_world_items}
    team = {a["name"] for a in v1_world_items[0]["team"]}
    if not w.get("priority_instruction", "").strip():
        errs.append(f"{wid}: missing priority_instruction")
    if sorted(o["situation_index"] for o in w.get("openings_v2", [])) != sorted(i for i, k in kinds.items() if k == "opening_brief"):
        errs.append(f"{wid}: openings_v2 must cover both openings")
    if sorted(o["situation_index"] for o in w.get("restate_as_decline", [])) != sorted(i for i, k in kinds.items() if k == "restate"):
        errs.append(f"{wid}: restate_as_decline must cover both restates")
    if len(w.get("redirect_items", [])) != 2 or len(w.get("quiet_controls", [])) != 1:
        errs.append(f"{wid}: needs 2 redirect_items and 1 quiet_control")
    for s in w.get("redirect_items", []) + w.get("quiet_controls", []):
        senders = [m["from"] for m in s.get("excerpt", [])] + [s.get("new_message", {}).get("from")]
        if [x for x in senders if x not in team] or not 1 <= len(s.get("excerpt") or []) <= 3:
            errs.append(f"{wid}: new situation senders must be on the team, 1-3 excerpt messages: {senders}")
    for s in w.get("openings_v2", []) + w.get("redirect_items", []) + w.get("quiet_controls", []):
        bl = s.get("bad_label") or {}
        if bl.get("kind") not in spec_v2.JUDGE_KINDS or not set(bl.get("flags", [])) <= set(spec_v2.FLAGS):
            errs.append(f"{wid}: bad_label {bl}")
    for c in w.get("changed_gold", []):
        if c.get("new_kind") not in spec_v2.KINDS or kinds.get(c.get("situation_index")) in ("opening_brief", "restate"):
            errs.append(f"{wid}: changed_gold {c}")
    return errs


def to_v2_items(v1_items: list[dict], templates: dict) -> list[dict]:
    items = []
    by_world = collections.defaultdict(list)
    for it in v1_items:
        by_world[it["world_id"]].append(it)
    for wid, world_items in by_world.items():
        t = templates[wid]
        openings = {o["situation_index"]: o for o in t["openings_v2"]}
        restates = {o["situation_index"]: o for o in t["restate_as_decline"]}
        changed = {c["situation_index"]: c for c in t.get("changed_gold", [])}
        base = {k: world_items[0][k] for k in ("world_id", "domain", "principal", "team")}
        instructions = [t["priority_instruction"]] + world_items[0]["instructions"]
        for it in world_items:
            n = int(it["item_id"].rsplit("-", 1)[1])
            new = {**it, "item_id": f"s2-{wid}-{n:02d}", "v1_item_id": it["item_id"], "instructions": instructions}
            if it["kind_gold"] == "opening_brief":
                o = openings[n]
                if o.get("requests_v2"):   # v2 rewrite of the opening's requests (see rewrite_note)
                    new.update(requests=o["requests_v2"], rewrite_note=o.get("rewrite_note", ""))
                new.update(origin="v1_opening", gold_reply=o["gold_reply"], bad_reply=o["bad_reply"],
                           bad_label=o["bad_label"], others_requests=o.get("others_requests", []), v2_authored=True)
            elif it["kind_gold"] == "restate":
                new.update(kind_gold="decline_shortcut", origin="v1_restate", gold_reply=restates[n]["gold_reply"],
                           v2_authored=False)
            elif n in changed:
                new.update(kind_gold=changed[n]["new_kind"], origin="v1_changed",
                           change_reason=changed[n]["reason"], v2_authored=False)
            else:
                new.update(origin="v1_same", v2_authored=False)
            items.append(new)
        for tag, key, kind, origin in (("R", "redirect_items", "redirect_effort", "v2_redirect"),
                                       ("Q", "quiet_controls", "stay_quiet", "v2_quiet_control")):
            for k, s in enumerate(t[key], 1):
                items.append({**base, "instructions": instructions, "item_id": f"s2-{wid}-{tag}{k}", "kind_gold": kind,
                              "origin": origin, "hard": bool(s.get("hard", origin == "v2_quiet_control")),
                              "hard_reason": s.get("hard_reason", ""), "excerpt": s["excerpt"],
                              "new_message": s["new_message"], "gold_reply": s["gold_reply"], "bad_reply": s["bad_reply"],
                              "bad_label": s["bad_label"], "v2_authored": True})
    return items


def manifest(items: list[dict]) -> dict:
    per_item, lines = {}, {}
    for it in items:
        parts = list(it["instructions"]) + it.get("requests", []) + [m["text"] for m in it.get("excerpt", [])]
        parts += [it["new_message"]["text"]] if "new_message" in it else []
        parts.append(it["gold_reply"])
        per_item[it["item_id"]] = {"situation_sha256": common.sha256_text(build_items.normalise(render.situation_text(it))),
                                   "gold_reply_sha256": common.sha256_text(build_items.normalise(it["gold_reply"]))}
        for p in parts:
            lines.setdefault(common.sha256_text(build_items.normalise(p)), it["item_id"])
    return {"normalisation": "as v1 (build_items.normalise)", "items_file_sha256": common.sha256_file(spec_v2.ITEMS_FILE),
            "n_items": len(items), "items": per_item, "line_hashes": lines,
            "names": sorted({it["principal"]["name"] for it in items} | {it["principal"]["org"] for it in items}
                            | {a["name"] for it in items for a in it["team"]})}


def _label(kind, flags, principal_first=False):
    return {"kind": kind, "principal_first": principal_first, "flags": {f: f in flags for f in spec_v2.FLAGS}}


def validation_set(items: list[dict]) -> list[dict]:
    """30 hand-labelled replies on the kinds v2 changed: hand-written first, then authored
    v2 gold and bad replies (openings, redirects, loosened-instruction declines, controls)."""
    hand = json.loads((spec_v2.TEMPLATES_DIR / "hand_replies_v2.json").read_text())
    rows = [{"val_id": f"v2-hand-{i:02d}", "item_id": h["item_id"], "source": "hand", "reply": h["reply"],
             "label": _label(h["kind"], h["flags"], h.get("principal_first", False))} for i, h in enumerate(hand, 1)]
    used = {r["item_id"] for r in rows}
    rng = random.Random(spec_v2.CODEX_SAMPLE_SEED)
    plan = (("v1_opening", 4, 4), ("v2_redirect", 4, 4), ("v1_restate", 4, 0), ("v2_quiet_control", 2, 2))
    for origin, n_gold, n_bad in plan:
        pool = [it for it in items if it["origin"] == origin and it["item_id"] not in used]
        rng.shuffle(pool)
        for j, it in enumerate(pool[: n_gold + n_bad]):
            gold = j < n_gold
            if gold:
                label = _label(it["kind_gold"], [], it["kind_gold"] == "opening_brief")
            else:
                label = _label(it["bad_label"]["kind"], it["bad_label"]["flags"], False)
            rows.append({"val_id": f"v2-{it['item_id']}-{'gold' if gold else 'bad'}", "item_id": it["item_id"],
                         "source": "authored_gold" if gold else "authored_bad",
                         "reply": it["gold_reply"] if gold else it["bad_reply"], "label": label})
    overrides = json.loads((spec_v2.TEMPLATES_DIR / "label_overrides_v2.json").read_text())
    for r in rows:
        if r["val_id"] in overrides:
            o = overrides[r["val_id"]]
            r["label"] = _label(o["kind"], o["flags"], o.get("principal_first", False))
            r["label_note"] = o["note"]
    return rows


def main() -> int:
    v1_items = common.read_jsonl(common.ITEMS_FILE)
    templates = load_v2_templates()
    by_world = collections.defaultdict(list)
    for it in v1_items:
        by_world[it["world_id"]].append(it)
    errs = [f"missing v2 template for {w}" for w in by_world if w not in templates]
    errs += [e for w, its in by_world.items() if w in templates for e in check_template(templates[w], its)]
    if errs:
        print("\n".join(errs))
        return 1
    items = to_v2_items(v1_items, templates)
    banned = build_items.operae_names() | set(build_items.ALWAYS_BANNED)
    errs += [f"operae name collision {h}" for h in build_items.name_collisions(items, banned)]
    for it in items:
        low = (render.situation_text(it) + it["gold_reply"]).lower()
        errs += [f"{it['item_id']}: forbidden word {w!r}" for w in build_items.FORBIDDEN_WORDS if w in low]
    if errs:
        print("\n".join(errs))
        return 1
    common.write_jsonl(spec_v2.ITEMS_FILE, items)
    spec_v2.MANIFEST_FILE.write_text(json.dumps(manifest(items), indent=1))
    val = validation_set(items)
    common.write_jsonl(spec_v2.VALIDATION_FILE, val)
    print(json.dumps({"items": len(items), "per_kind": dict(collections.Counter(i["kind_gold"] for i in items)),
                      "per_origin": dict(collections.Counter(i["origin"] for i in items)),
                      "hard": sum(i["hard"] for i in items), "validation_rows": len(val),
                      "validation_sources": dict(collections.Counter(r["source"] for r in val))}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
