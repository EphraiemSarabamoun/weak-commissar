"""Generator: turn the hand-written worlds into benchmark items, check them, and write the manifest.

Inputs:  templates/worlds_*.json (hand-written per templates/AUTHORING.md)
         templates/hand_replies.json (replies written and labelled by hand for judge validation)
         templates/label_overrides.json (hand corrections to authored validation labels)
Outputs: items.jsonl       one item per situation, ids sb-<world>-<nn>
         manifest.json     sha256 of every item's rendered situation and of every line in it
                           (instruction, request, message, gold reply), normalised, so overlap
                           with training rows can be checked later (stewardbench.py overlap)
         validation.jsonl  30 hand-labelled replies for validating the judge

Checks (any failure aborts): the schema in AUTHORING.md, 20 items per kind, no names
from the operae dataset (read from the local Hugging Face cache when present, never
copied here) and no evaluation words in the situations.
"""

from __future__ import annotations

import collections
import glob
import json
import random
import re
import sys
from pathlib import Path

import common
import render

PER_KIND = 20
FORBIDDEN_WORDS = ("commissar", "benchmark", "grader", "answer key", "stewardbench")
ALWAYS_BANNED = ("Ephraiem", "Sarabamoun", "<redacted>", "<redacted>", "Claudius", "<redacted>")
OPERAE_GLOB = str(Path.home() / ".cache/huggingface/hub/datasets--ephraiemsam16--operae-private/snapshots/*/data/*.jsonl")
# Proper nouns that operae shares with ordinary English or with this benchmark's own wording.
OPERAE_COMMON = {"Account Manager", "Marketing Manager", "Program Officer", "Bookings Officer", "Box Office Manager",
                 "Internal Server Error", "Service Unavailable", "Gateway Timeout", "Too Many Requests",
                 "Customer Terms", "Night Shift", "Emergency Response", "Physical Therapy", "Faster Payment"}


def normalise(text: str) -> str:
    """Lowercase, collapse whitespace, strip punctuation at the ends: the form every hash is taken on."""
    return re.sub(r"\s+", " ", text.lower()).strip(" .,:;!?\"'")


def load_worlds() -> list[dict]:
    worlds = []
    for path in sorted(glob.glob(str(common.TEMPLATES_DIR / "worlds_*.json"))):
        worlds += json.loads(Path(path).read_text())
    return worlds


def check_world(w: dict) -> list[str]:
    """Schema problems in one world, as messages (empty when it is clean)."""
    errs, wid = [], w.get("world_id", "?")
    if not 2 <= len(w.get("instructions", [])) <= 5:
        errs.append(f"{wid}: needs 2-5 instructions")
    team = {a["name"] for a in w.get("team", [])}
    if not 2 <= len(team) <= 5:
        errs.append(f"{wid}: needs 2-5 team members")
    sits = w.get("situations", [])
    counts = collections.Counter(s.get("kind") for s in sits)
    if len(sits) != 12 or any(counts[k] != 2 for k in common.KINDS):
        errs.append(f"{wid}: needs exactly two situations of each kind, got {dict(counts)}")
    for i, s in enumerate(sits):
        tag = f"{wid}#{i} ({s.get('kind')})"
        if s.get("kind") == "opening_brief":
            if not s.get("requests") or s.get("excerpt") or s.get("new_message"):
                errs.append(f"{tag}: an opening has requests and no excerpt/new_message")
        else:
            if s.get("requests") or not s.get("new_message") or not 1 <= len(s.get("excerpt") or []) <= 3:
                errs.append(f"{tag}: needs 1-3 excerpt messages and a new_message, no requests")
            senders = [m["from"] for m in s.get("excerpt", [])] + [s.get("new_message", {}).get("from")]
            outsiders = [x for x in senders if x not in team]
            if outsiders and s.get("kind") != "question_approval":
                errs.append(f"{tag}: senders not on the team: {outsiders}")
        for field in ("gold_reply", "bad_reply"):
            if not str(s.get(field, "")).strip():
                errs.append(f"{tag}: missing {field}")
        bl = s.get("bad_label") or {}
        if bl.get("kind") not in common.JUDGE_KINDS or not set(bl.get("flags", [])) <= set(common.FLAGS):
            errs.append(f"{tag}: bad_label {bl}")
    return errs


# Ordinary capitalised words that can sit inside an operae name without being one.
CALENDAR_WORDS = {"Road", "Street", "Lane", "Row", "Avenue", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday", "January",
                  "February", "March", "April", "May", "June", "July", "August", "September", "October",
                  "November", "December", "British", "Summer", "Time"}


def operae_names() -> set[str]:
    """Proper nouns from the operae rows in the local cache.

    Multiword names (people, organisations) are banned as phrases. A single word from one
    of them is banned on its own only when operae never uses it in lowercase, which keeps
    surnames and coined org names ("Okonkwo", "Swiftline") and drops ordinary words that
    happen to sit inside a name ("Lab", "University", "Hall").
    """
    names, text = set(), ""
    for path in glob.glob(OPERAE_GLOB):
        text += Path(path).read_text()
    names = set(re.findall(r"\b[A-Z][a-z]{2,}(?:\s[A-Z][a-z]{2,})+\b", text)) - OPERAE_COMMON
    lower_words = set(re.findall(r"\b[a-z]{3,}\b", text))
    parts = {p for n in names for p in n.split()
             if p.lower() not in lower_words and p not in CALENDAR_WORDS}
    return names | parts


def name_collisions(items: list[dict], banned: set[str]) -> list[str]:
    """Banned proper nouns that appear as whole words in any item's text."""
    hits = []
    for it in items:
        text = render.situation_text(it) + " " + it["gold_reply"] + " " + it["bad_reply"]
        words = set(re.findall(r"\b[A-Z][a-z]{2,}\b", text))
        for b in banned:
            if (" " in b and b in text) or (" " not in b and b in words):
                hits.append(f"{it['item_id']}: {b}")
    return hits


def to_items(worlds: list[dict]) -> list[dict]:
    items = []
    for w in worlds:
        for n, s in enumerate(w["situations"], 1):
            it = {"item_id": f"sb-{w['world_id']}-{n:02d}", "world_id": w["world_id"], "domain": w["domain"],
                  "principal": w["principal"], "instructions": w["instructions"], "team": w["team"],
                  "kind_gold": s["kind"], "hard": bool(s.get("hard")), "hard_reason": s.get("hard_reason", "")}
            if s["kind"] == "opening_brief":
                it["requests"] = s["requests"]
            else:
                it["excerpt"], it["new_message"] = s["excerpt"], s["new_message"]
            it.update(gold_reply=s["gold_reply"], bad_reply=s["bad_reply"], bad_label=s["bad_label"])
            items.append(it)
    return items


def manifest(items: list[dict]) -> dict:
    """sha256 of each rendered situation and of each normalised line, plus the items file hash."""
    per_item, lines = {}, {}
    for it in items:
        parts = list(it["instructions"]) + it.get("requests", []) + [m["text"] for m in it.get("excerpt", [])]
        if "new_message" in it:
            parts.append(it["new_message"]["text"])
        parts.append(it["gold_reply"])
        per_item[it["item_id"]] = {"situation_sha256": common.sha256_text(normalise(render.situation_text(it))),
                                   "gold_reply_sha256": common.sha256_text(normalise(it["gold_reply"]))}
        for p in parts:
            lines.setdefault(common.sha256_text(normalise(p)), it["item_id"])
    return {"normalisation": "lowercase, whitespace collapsed, end punctuation stripped; sha256 of UTF-8",
            "items_file_sha256": common.sha256_file(common.ITEMS_FILE), "n_items": len(items),
            "items": per_item, "line_hashes": lines,
            "names": sorted({it["principal"]["name"] for it in items} | {it["principal"]["org"] for it in items}
                            | {a["name"] for it in items for a in it["team"]})}


def validation_set(items: list[dict]) -> list[dict]:
    """30 labelled replies: 5 per kind. Hand-written replies first, then authored gold and
    bad replies, alternating, chosen with a fixed seed. Labels are the authors' or mine."""
    hand = json.loads((common.TEMPLATES_DIR / "hand_replies.json").read_text())
    by_id = {it["item_id"]: it for it in items}
    rows = [{"val_id": f"v-hand-{i:02d}", "item_id": h["item_id"], "source": "hand", "reply": h["reply"],
             "label": {"kind": h["kind"], "flags": {f: f in h["flags"] for f in common.FLAGS}}}
            for i, h in enumerate(hand, 1)]
    rng = random.Random(common.BOOTSTRAP_SEED)
    for k_i, kind in enumerate(common.KINDS):
        have = sum(1 for r in rows if by_id[r["item_id"]]["kind_gold"] == kind)
        used = {r["item_id"] for r in rows}
        pool = [it for it in items if it["kind_gold"] == kind and it["item_id"] not in used]
        rng.shuffle(pool)
        for j, it in enumerate(pool[: max(0, 5 - have)]):
            use_gold = (j + k_i) % 2 == 0
            label = ({"kind": kind, "flags": {f: False for f in common.FLAGS}} if use_gold else
                     {"kind": it["bad_label"]["kind"], "flags": {f: f in it["bad_label"]["flags"] for f in common.FLAGS}})
            rows.append({"val_id": f"v-{it['item_id']}-{'gold' if use_gold else 'bad'}", "item_id": it["item_id"],
                         "source": "authored_gold" if use_gold else "authored_bad",
                         "reply": it["gold_reply"] if use_gold else it["bad_reply"], "label": label})
    overrides = json.loads((common.TEMPLATES_DIR / "label_overrides.json").read_text())
    for r in rows:
        o = overrides.get(r["val_id"])
        if o:
            r["label"] = {"kind": o["kind"], "flags": {f: f in o["flags"] for f in common.FLAGS}}
            r["label_note"] = o["note"]
    return rows


def main() -> int:
    worlds = load_worlds()
    errs = [e for w in worlds for e in check_world(w)]
    items = to_items(worlds)
    counts = collections.Counter(it["kind_gold"] for it in items)
    if any(counts[k] != PER_KIND for k in common.KINDS):
        errs.append(f"label balance: {dict(counts)}; need {PER_KIND} each")
    if len({it["item_id"] for it in items}) != len(items):
        errs.append("duplicate item ids")
    banned = operae_names() | set(ALWAYS_BANNED)
    errs += [f"operae name collision {h}" for h in name_collisions(items, banned)]
    for it in items:
        low = render.situation_text(it).lower()
        errs += [f"{it['item_id']}: forbidden word {w!r}" for w in FORBIDDEN_WORDS if w in low]
    if errs:
        print("\n".join(errs))
        return 1
    common.write_jsonl(common.ITEMS_FILE, items)
    common.MANIFEST_FILE.write_text(json.dumps(manifest(items), indent=1))
    val = validation_set(items)
    common.write_jsonl(common.VALIDATION_FILE, val)
    print(json.dumps({"items": len(items), "per_kind": dict(counts), "hard": sum(it["hard"] for it in items),
                      "operae_names_checked": len(banned), "validation_rows": len(val),
                      "validation_sources": dict(collections.Counter(r["source"] for r in val))}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
