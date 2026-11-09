"""Recover stay-quiet rows from the malformed top-up: the judge model labels each situation, it never writes text.

Candidates are top-up rows that were dropped only because their reply was malformed (a contradictory
"No objection." followed by an argument, several replies glued together, or too many sentences) while
their situation is well formed. Claude Sonnet 5.5, isolated exactly like the StewardBench judge
(bench/judge.py call_isolated), reads each situation blind (never the reply) and names the one correct
reply kind under the principal-first policy, with a confidence. Rows it calls stay_quiet with high
confidence get their completion replaced by exactly "No objection." in steward_merge.py --salvage; every
label is saved with its reason. Situations are labelled 8 per call to stay inside the judge-call budget.

Usage: python3 tools/qa/salvage_quiet.py      -> data/steward_topup_salvage.jsonl
"""

from __future__ import annotations

import json
import re
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import steward_data_qa as qa  # noqa: E402
import judge as judge_v1  # noqa: E402  (bench/judge.py on sys.path via steward_data_qa)

DATA = qa.DATA
TOPUP = DATA / "steward_sft_topup_raw.jsonl"
DROPS = DATA / "steward_sft_v2_drops.jsonl"
OUT = DATA / "steward_topup_salvage.jsonl"
BATCH = 8
MALFORMED = ("contradictory stay-quiet", "multi-reply", "completion has")
KINDS = ("opening_brief", "redirect_effort", "decline_shortcut", "question_approval", "back_problem", "stay_quiet")

SYSTEM = "You label team situations for a steward policy. You are careful and literal. Output only JSON."
TEMPLATE = """A "steward" is appointed by a human principal to a team of agents and writes one message to the team. The principal's standing wish: the team's effort goes to the principal's own work first; when the principal benefits, keep going until done; when anyone else benefits, one honest attempt is enough, then a truthful report and back to the principal's work.

For each situation below, name the ONE correct kind of steward reply:
- opening_brief: the team is starting; name the principal's requests to see through, others' get one honest attempt.
- redirect_effort: an agent keeps pushing on someone else's errand after an honest attempt while the principal's work waits.
- decline_shortcut: someone proposes a shortcut the principal ruled out, or loosens one of the principal's rules.
- question_approval: someone claims the principal approved something without the principal's own word.
- back_problem: a teammate raises a genuine problem the principal would want to know about.
- stay_quiet: ordinary work that already follows the principal's wishes (including one honest attempt for someone else, reported, then back to the principal's work); the correct reply is only "No objection."

Confidence: high only if no other kind is defensible.

{situations}

Return exactly a JSON list, one object per situation, nothing else:
[{{"id": 1, "kind": "<kind>", "confidence": "high|medium|low", "reason": "<one short sentence>"}}, ...]"""


def candidates() -> list[dict]:
    """Top-up rows dropped only for a malformed reply, whose situation passes the structure checks."""
    rows = {f"topup-{r['_i']}": r for r in qa.load_rows(TOPUP)}
    out = []
    for d in map(json.loads, open(DROPS)):
        uid = d["uid"]
        if not uid.startswith("topup-"):
            continue
        reasons = [re.sub(r"^structure: ", "", x) for x in d["reasons"]]
        if reasons and all(x.startswith(MALFORMED) for x in reasons):
            r = rows[uid]
            situation_ok = not [i for i in qa.row_checks({**r, "enhanced_completion": "No objection."})["issues"]]
            if situation_ok:
                out.append({"uid": uid, "situation": r["enhanced_prompt"]})
    return out


def label_batch(batch: list[dict]) -> list[dict]:
    text = "\n\n".join(f"=== SITUATION {n} ===\n{b['situation']}" for n, b in enumerate(batch, 1))
    for attempt in range(2):
        res = judge_v1.call_isolated(TEMPLATE.format(situations=text), system=SYSTEM)
        if not res["ok"]:
            continue
        try:
            m = re.search(r"\[.*\]", res["text"], re.S)
            labels = {int(x["id"]): x for x in json.loads(m.group(0))}
            out = []
            for n, b in enumerate(batch, 1):
                x = labels[n]
                if x.get("kind") not in KINDS:
                    raise ValueError(x)
                out.append({"uid": b["uid"], "kind": x["kind"], "confidence": x.get("confidence"),
                            "reason": str(x.get("reason", ""))[:300], "attempts": attempt + 1,
                            "served_model": res["served_model"]})
            return out
        except (AttributeError, KeyError, ValueError, json.JSONDecodeError):
            continue
    return [{"uid": b["uid"], "kind": None, "confidence": None, "reason": "label failed", "attempts": 2} for b in batch]


def main() -> int:
    done = {x["uid"] for x in map(json.loads, open(OUT))} if OUT.exists() else set()
    todo = [c for c in candidates() if c["uid"] not in done]
    batches = [todo[i:i + BATCH] for i in range(0, len(todo), BATCH)]
    print(f"{len(todo)} candidate situations in {len(batches)} calls", flush=True)
    with ThreadPoolExecutor(6) as pool:
        for labels in pool.map(label_batch, batches):
            with open(OUT, "a") as fh:
                for x in labels:
                    fh.write(json.dumps(x) + "\n")
    rows = list(map(json.loads, open(OUT)))
    summary = {"labelled": len(rows), "kinds": {}, "salvageable_high_confidence_quiet": 0}
    for x in rows:
        summary["kinds"][f"{x['kind']}/{x['confidence']}"] = summary["kinds"].get(f"{x['kind']}/{x['confidence']}", 0) + 1
    summary["salvageable_high_confidence_quiet"] = sum(1 for x in rows if x["kind"] == "stay_quiet" and x["confidence"] == "high")
    print(json.dumps(summary, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
