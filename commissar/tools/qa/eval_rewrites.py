"""Rewrite-fidelity eval: a served model rewrites each held-out rewrite row, scored by the test-time rules.

For each held-out rewrite row the model gets what the commissar gets at test time (operae gen_rewrite.py): the
system prompt commissar_prompt_v2_2 (principal filled) and the user message (task line, two-header format,
materials), at temperature 0 with max_tokens 800. With --placement user it instead gets the whole training
prompt as one user turn (v4 trains with the instructions inside the user turn), to measure that mismatch.

Each reply is scored with W1 (finished, exactly the two-header format) and, per part, rewrite_rows.check (W2 to
W11 and the v3 policy checks) and strict_check; with --judge, the isolated Sonnet request-change and fidelity
checklist (judge_requests.FULL_TEMPLATE) runs on each parsed reply. Two quick gates are counted for every reply:
identity (both parts equal to the original after stripping, the copying round 1's adapter showed) and added
priority guidance (operae gen_rewrite.GUIDANCE matches the reply but not the original, as operae's
rewrite_stats.py counts it). Steward calls go only to the local server.

The rows come from a holdout file (--holdout, default the v4 one). Each held-out rewrite prompt is parsed back
into principal, shift note and message; rows that the v4 index names keep their v4 uid (rewrite-N), so runs on
the v4 and v5 holdouts pair up on the 21 shared rows, and other rows get v5-<sha256 of the prompt, 10 hex>.
--label names the output folder when the served name is not the model being measured (round 2's adapter is
served as steward-lora while its slot holds serve/adapter/v5).

Usage: python3 tools/qa/eval_rewrites.py --model steward-lora [--label steward-lora-v5]
           [--holdout data/steward_sft_v5_holdout.jsonl] [--placement system|user] [--judge] [--limit N]
Outputs: bench/rewrite_eval/<label or model>_<placement>[_<holdout tag>]/outputs.jsonl and summary.json
"""

from __future__ import annotations

import argparse
import collections
import hashlib
import json
import re
import sys
import time
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))
import merge_v3  # noqa: E402
import rewrite_rows as rw  # noqa: E402
import steward_data_qa as qa  # noqa: E402

URL = "http://127.0.0.1:8417/v1/chat/completions"
OUT_ROOT = qa.REPO / "bench" / "rewrite_eval"
V4_HOLDOUT = qa.DATA / "steward_sft_v4_holdout.jsonl"
# operae experiments/commissar/steward/gen_rewrite.py GUIDANCE, copied (this repo does not import operae)
GUIDANCE = re.compile(r"honest attempt|\bfirst\b|priorit|regardless", re.I)
TASK_START = "You receive the materials an agent working for "
MATERIALS = re.compile(r"The materials:\nSHIFT NOTE:\n(?P<shift>.*)\nMESSAGE FROM (?P<name>[^\n]+):\n(?P<request>.*)\Z", re.S)


def v4_uids() -> dict[str, str]:
    """{test-time user message: v4 uid} for the 21 v4 held-out rewrite rows, rebuilt from the raw rows."""
    raw = qa.load_rows(merge_v3.REWRITE_RAW)
    out = {}
    for x in map(json.loads, open(qa.DATA / "steward_sft_v4_index.jsonl")):
        if x["task"] == "rewrite" and x["split"] == "holdout":
            name, shift, request, _, _ = rw.map_row(raw[int(x["uid"].split("-")[1])])[0]
            out[rw.user_message(name, shift, request)] = x["uid"]
    return out


def holdout_rows(path: Path = V4_HOLDOUT) -> list[tuple[str, tuple]]:
    """[(uid, (name, shift, request, completion))] for every rewrite row of a holdout file, in file order."""
    known, out = v4_uids(), []
    for row in map(json.loads, open(path)):
        at = row["prompt"].find(TASK_START)
        if at < 0:
            continue                                   # a steward row
        user = row["prompt"][at:]
        m = MATERIALS.search(user)
        if not m:
            raise ValueError(f"unparsable rewrite prompt in {path}: {user[:120]!r}")
        name, shift, request = m["name"], m["shift"], m["request"]
        if rw.user_message(name, shift, request) != user:
            raise ValueError(f"re-rendered user message differs from the row in {path} ({name})")
        uid = known.get(user) or "v5-" + hashlib.sha256(row["prompt"].encode()).hexdigest()[:10]
        out.append((uid, (name, shift, request, row["completion"])))
    return out


def gates(parts, shift: str, request: str) -> dict:
    """Identity with the original and added priority guidance, as operae's rewrite_stats.py counts them."""
    if parts is None:
        return {"identical": False, "guidance_added": False}
    same = parts[0].strip() == shift.strip() and parts[1].strip() == request.strip()
    added = bool(GUIDANCE.search(parts[0] + " " + parts[1])) and not GUIDANCE.search(shift + " " + request)
    return {"identical": same, "guidance_added": added}


def parse(content: str, name: str):
    """(shift, message) from an exact two-header reply, else None (gen_rewrite.parse, W1)."""
    t = (content or "").strip()
    head = f"MESSAGE FROM {name}:"
    if not t.startswith(rw.SHIFT) or t.count(rw.SHIFT) != 1 or t.count(head) != 1:
        return None
    shift, msg = (x.strip() for x in t[len(rw.SHIFT):].split(head))
    return (shift, msg) if shift and msg else None


def ask(model: str, system: str | None, user: str) -> dict:
    messages = ([{"role": "system", "content": system}] if system else []) + [{"role": "user", "content": user}]
    t0 = time.perf_counter()
    r = requests.post(URL, json={"model": model, "temperature": 0, "max_tokens": 800, "messages": messages}, timeout=900)
    r.raise_for_status()
    out = r.json()
    return {"text": out["choices"][0]["message"]["content"], "finish": out["choices"][0]["finish_reason"],
            "seconds": round(time.perf_counter() - t0, 2)}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--model", required=True)
    ap.add_argument("--placement", choices=("system", "user"), default="system")
    ap.add_argument("--judge", action="store_true")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--label", help="output folder name (default: the model)")
    ap.add_argument("--holdout", type=Path, default=V4_HOLDOUT, help="holdout file to take the rewrite rows from")
    args = ap.parse_args()
    template = merge_v3.PREFIX.read_text().strip()
    rows = holdout_rows(args.holdout)[: args.limit or None]
    tag = "" if args.holdout.resolve() == V4_HOLDOUT.resolve() else "_" + args.holdout.stem.replace("steward_sft_", "")
    out_dir = OUT_ROOT / f"{args.label or args.model}_{args.placement}{tag}"
    out_dir.mkdir(parents=True, exist_ok=True)
    results = []
    for uid, (name, shift, request, _gold) in rows:
        system = template.replace("{PRINCIPAL}", name)
        user = rw.user_message(name, shift, request)
        reply = ask(args.model, system, user) if args.placement == "system" else ask(args.model, None, system + "\n\n" + user)
        fails = [] if reply["finish"] == "stop" else [f"W1: did not finish ({reply['finish']})"]
        parts = parse(reply["text"], name)
        if parts is None:
            fails.append("W1: not the two-header format")
        else:
            materials = f"{shift}\n{request}"
            fails += rw.check(name, shift, request, *parts, materials, reply["text"])
            fails += rw.strict_check(name, shift, request, *parts)
        verdict = None
        if args.judge and parts is not None:
            import judge_requests as jq
            verdict = jq.ask_full((uid, f"SHIFT NOTE:\n{shift}\nMESSAGE FROM {name}:\n{request}", reply["text"]))[0]
        results.append({"uid": uid, "reply": reply["text"], "finish": reply["finish"], "seconds": reply["seconds"],
                        "fails": fails, "passes_rules": not fails, "judge": verdict, **gates(parts, shift, request)})
    (out_dir / "outputs.jsonl").write_text("".join(json.dumps(r) + "\n" for r in results))
    judged = [r["judge"] for r in results if r["judge"] and r["judge"].get("ok")]
    by_source = lambda pred: {"v4_rows": sum(1 for r in results if r["uid"].startswith("rewrite-") and pred(r)),
                              "v5_rows": sum(1 for r in results if r["uid"].startswith("v5-") and pred(r))}
    summary = {
        "model": args.model, "label": args.label or args.model, "holdout": str(args.holdout.name),
        "placement": args.placement, "rows": len(results),
        "rows_by_source": by_source(lambda r: True),
        "identical": sum(r["identical"] for r in results), "identical_by_source": by_source(lambda r: r["identical"]),
        "guidance_added": sum(r["guidance_added"] for r in results),
        "guidance_added_by_source": by_source(lambda r: r["guidance_added"]),
        "w1_format_ok": sum(1 for r in results if not any(f.startswith("W1") for f in r["fails"])),
        "passes_all_rules": sum(r["passes_rules"] for r in results),
        "rule_failures": dict(collections.Counter(re.sub(r" ratio .*", " ratio", re.sub(r"[:\[].*", "", f)).strip()
                                                  for r in results for f in r["fails"])),
        "judge": None if not judged else {
            "judged": len(judged), "acceptable": sum(bool(v.get("acceptable")) for v in judged),
            "request_changed": sum(bool(v.get("request_changed")) for v in judged),
            "added_obligation": sum(bool(v.get("added_obligation")) for v in judged),
            "facts_kept": sum(bool(v.get("facts_kept")) for v in judged),
            "colleague_errand_as_own": sum(bool(v.get("colleague_errand_as_own")) for v in judged)},
        "median_seconds": sorted(r["seconds"] for r in results)[len(results) // 2] if results else None,
    }
    (out_dir / "summary.json").write_text(json.dumps(summary, indent=1))
    print(json.dumps(summary, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
