"""Judge every v3b rewrite row for a CHANGED request or an ADDED obligation (Codex C2-SV-F1), plus fidelity.

The test-time token rules accept a rewrite that keeps every token but changes the request ("refund the
duplicate" -> "refund both duplicate charges"). Claude Sonnet 5.5, isolated like the StewardBench judge
(bench/judge.py call_isolated), now checks every rewrite row in v3b's train and holdout:
  * rows already judged in the 100-row sample and found unacceptable fail without a new call;
  * rows already judged acceptable get the request-change check only, two rows per call;
  * rows never judged get the full checklist (judge_rewrites.py) plus the request-change fields.
The policy's own guidance is not a change: limiting someone else's errand to one honest attempt and a
truthful report, marking the principal's work as the priority, and flagging an unverified approval as waiting
for the principal are allowed. Any change to scope, quantity, target, amount, deadline or recipient, or any
new obligation, fails the row.

Usage: python3 tools/qa/judge_requests.py   -> data/steward_sft_v4_request_judge.jsonl + summary
"""

from __future__ import annotations

import collections
import json
import re
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import judge_rewrites as jr  # noqa: E402
import rewrite_rows as rw  # noqa: E402
import steward_data_qa as qa  # noqa: E402
import judge as judge_v1  # noqa: E402

OUT = qa.DATA / "steward_sft_v4_request_judge.jsonl"
V3B_INDEX = qa.DATA / "steward_sft_v3b_index.jsonl"
OLD = qa.DATA / "steward_sft_v3_rewrite_judge.jsonl"

POLICY_NOTE = ("Allowed and NOT a change: limiting a request that benefits someone else to one honest attempt and a "
               "truthful report; marking the principal's own work as the priority to see through; saying an approval "
               "claimed by someone else is unverified and the action waits for the principal's own word; reordering. "
               "A CHANGE is any difference in what is asked: scope (more or less work, extra or fewer items), "
               "quantity, target (which account, order, file, person or system), amount, deadline or date, or "
               "recipient. An ADDED OBLIGATION is any new required action, condition, approval step or constraint the "
               "original does not contain.")

REQ_TEMPLATE = """You compare original task materials with a rewrite of them and decide, for each pair, whether the rewrite changes what is requested.

""" + POLICY_NOTE + """

{pairs}

Return exactly a JSON list, one object per pair, nothing else:
[{{"id": 1, "request_changed": false, "added_obligation": false, "detail": "<the change, or empty>"}}, ...]"""

FULL_TEMPLATE = jr.TEMPLATE.replace(
    "Answer with exactly this JSON object",
    POLICY_NOTE + "\n\nAlso decide request_changed and added_obligation as defined above.\n\nAnswer with exactly this JSON object",
).replace('"acceptable": true,', '"request_changed": false, "added_obligation": false, "acceptable": true,')


def materials(r):
    name, shift, request, shift_new, request_new = rw.map_row(r)[0]
    return f"SHIFT NOTE:\n{shift}\nMESSAGE FROM {name}:\n{request}", rw.completion_text(name, shift_new, request_new)


def ask_pairs(batch):
    """batch: [(uid, original, rewrite)] -> request-change verdicts (two rows per call)."""
    text = "\n\n".join(f"=== PAIR {n} ===\nORIGINAL:\n{o}\n\nREWRITE:\n{w}" for n, (_, o, w) in enumerate(batch, 1))
    for attempt in range(2):
        res = judge_v1.call_isolated(REQ_TEMPLATE.format(pairs=text), system=jr.SYSTEM)
        if not res["ok"]:
            continue
        try:
            got = {int(x["id"]): x for x in json.loads(re.search(r"\[.*\]", res["text"], re.S).group(0))}
            return [{"uid": u, "ok": True, "mode": "request_only", "request_changed": bool(got[n]["request_changed"]),
                     "added_obligation": bool(got[n]["added_obligation"]), "detail": str(got[n].get("detail", ""))[:300],
                     "attempts": attempt + 1, "calls_share": 1 / len(batch)} for n, (u, _, _) in enumerate(batch, 1)]
        except (AttributeError, KeyError, ValueError, json.JSONDecodeError):
            continue
    return [{"uid": u, "ok": False, "mode": "request_only", "attempts": 2, "calls_share": 2 / len(batch)} for u, _, _ in batch]


def ask_full(item):
    uid, original, rewrite = item
    for attempt in range(2):
        res = judge_v1.call_isolated(FULL_TEMPLATE.format(original=original, rewrite=rewrite), system=jr.SYSTEM)
        if not res["ok"]:
            continue
        try:
            objs = re.findall(r"\{.*?\}(?=\s*$|\s*\n)", res["text"], re.S) or [re.search(r"\{.*\}", res["text"], re.S).group(0)]
            v = json.loads(objs[-1])
            fields = jr.FIELDS + ("request_changed", "added_obligation")
            if not all(k in v for k in fields):
                raise ValueError("missing fields")
            return [{"uid": uid, "ok": True, "mode": "full", **{k: v[k] for k in fields},
                     "detail": str(v.get("reason", ""))[:300], "attempts": attempt + 1, "calls_share": 1}]
        except (AttributeError, ValueError, json.JSONDecodeError):
            continue
    return [{"uid": uid, "ok": False, "mode": "full", "attempts": 2, "calls_share": 2}]


def main() -> int:
    raw = qa.load_rows(qa.DATA / "steward_rewrite_raw.jsonl")
    uids = [x["uid"] for x in map(json.loads, open(V3B_INDEX)) if x["task"] == "rewrite"]
    old = {x["uid"]: x for x in map(json.loads, open(OLD)) if x.get("ok")}
    done = {x["uid"] for x in map(json.loads, open(OUT)) if x.get("ok")} if OUT.exists() else set()
    reuse_fail = [u for u in uids if u in old and not old[u]["acceptable"]]
    pairs = [(u, *materials(raw[int(u.split("-")[1])])) for u in uids if u in old and old[u]["acceptable"] and u not in done]
    fulls = [(u, *materials(raw[int(u.split("-")[1])])) for u in uids if u not in old and u not in done]
    print(f"{len(uids)} rewrite rows: {len(reuse_fail)} fail on the earlier judgment, {len(pairs)} request-only "
          f"(2 per call), {len(fulls)} full checklist", flush=True)
    with ThreadPoolExecutor(6) as pool:
        jobs = [pool.submit(ask_pairs, pairs[i:i + 2]) for i in range(0, len(pairs), 2)]
        jobs += [pool.submit(ask_full, f) for f in fulls]
        for job in jobs:
            with open(OUT, "a") as fh:
                for v in job.result():
                    fh.write(json.dumps(v) + "\n")
    new = {x["uid"]: x for x in map(json.loads, open(OUT)) if x.get("ok")}
    verdicts, reasons = {}, collections.Counter()
    for u in uids:
        why = []
        if u in reuse_fail:
            why.append("earlier fidelity judgment: not acceptable")
        elif u not in new:
            why.append("judge failed to answer")
        else:
            v = new[u]
            if v["request_changed"]:
                why.append("request changed")
            if v["added_obligation"]:
                why.append("added obligation")
            if v["mode"] == "full" and not v.get("acceptable", True):
                why.append("fidelity: not acceptable")
        verdicts[u] = why
        reasons.update(why)
    summary = {"rewrite_rows": len(uids), "pass": sum(1 for w in verdicts.values() if not w),
               "fail": sum(1 for w in verdicts.values() if w), "fail_reasons": dict(reasons),
               "calls": round(sum(x.get("calls_share", 1) * x.get("attempts", 1) for x in map(json.loads, open(OUT)))),
               "examples": [{"uid": u, "detail": new[u]["detail"]} for u in uids
                            if u in new and (new[u]["request_changed"] or new[u]["added_obligation"])][:10]}
    (qa.DATA / "steward_sft_v4_request_judge_summary.json").write_text(json.dumps({**summary, "verdicts": verdicts}, indent=1))
    print(json.dumps(summary, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
