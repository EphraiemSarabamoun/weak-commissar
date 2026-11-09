"""Round 2: QA the v5 rewrite rows (Invent dataset 35e82f26, prompt data/invent_prompt_v5_rewrite.txt) and build v5.

v5 asks Invent for rows already in the test-time shape: the prompt is the commissar's user message (Ephraiem's task
line, the two-header format, "The materials:", SHIFT NOTE and one MESSAGE FROM the principal) and the completion is
the two-header reply. This module reuses the round-1 pipeline instead of forking it:
  rewrite_rows.check        W2 to W11 and the v3 policy checks (test-time rules, per part)
  rewrite_rows.strict_check v3b's access-clause and first-person checks
  steward_data_qa           overlap_hits (StewardBench v1/v2 lines and identities, operae names), near_duplicates
  judge_requests.ask_full   the isolated Sonnet 5.5 judge: full checklist plus request_changed and added_obligation
  build_v4 / merge_v3       the rendering (commissar_prompt_v2_2 prefix + user message) and the v2 steward rows
It adds what v5 needs: parse_v5 (the exact shape, with the fixed text rebuilt from the parsed name), W12 (scope and
count words added outside priority guidance, copied from operae's gen_rewrite.py so this repo does not import the
operae worktree, as rewrite_rows does for W2 to W11), and a deterministic beneficiary check on v5's fixed priority
sentences ("This is X's own work: ..." / "This errand is for Y, passed along by X: ...").

Commands (from <local>/projects/commissar; free except the judge's isolated Sonnet calls):
  python3 tools/qa/build_v5.py check    -> data/steward_sft_v5_qa.jsonl (every v5 row: parse, rules, overlap, dedup)
  python3 tools/qa/build_v5.py judge    -> data/steward_sft_v5_request_judge.jsonl (resumable; rows passing check)
  python3 tools/qa/build_v5.py build    -> data/steward_sft_v5_{train,holdout,index,drops}.jsonl, _report.json
"""

from __future__ import annotations

import argparse
import collections
import hashlib
import json
import random
import re
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import merge_v3  # noqa: E402
import rewrite_rows as rw  # noqa: E402
import steward_data_qa as qa  # noqa: E402

DATA = qa.DATA
RAW_V5 = DATA / "steward_rewrite_v5_raw.jsonl"
QA_OUT = DATA / "steward_sft_v5_qa.jsonl"
JUDGE_OUT = DATA / "steward_sft_v5_request_judge.jsonl"
# Re-judgement with the principal named. The first pass gave the judge only SHIFT NOTE / MESSAGE FROM, and because v5's
# principal writes about themself in the third person ("Alistair Finch needs ..."), the judge read the principal's own
# request as someone else's: 147 of 272 own rows failed as "colleague errand called the principal's own" or "added
# obligation". v4's materials named the principal in their system note, so this did not arise there. JUDGE2_OUT holds
# the corrected verdicts for every first-pass failure plus a seeded sample of first-pass passes (a consistency check);
# a row's verdict is JUDGE2's when it has one.
JUDGE2_OUT = DATA / "steward_sft_v5_request_judge2.jsonl"
PASS_SAMPLE = 60
V4_INDEX = DATA / "steward_sft_v4_index.jsonl"
V4_JUDGE = DATA / "steward_sft_v4_request_judge_summary.json"
OUT = {k: DATA / f"steward_sft_v5_{k}" for k in ("train.jsonl", "holdout.jsonl", "index.jsonl", "drops.jsonl",
                                                  "report.json")}
TARGET_REWRITE_SHARE = 0.60      # manager 22:36: prioritise the rewrite task (the dispatch's 40% superseded)
MIN_TRAIN_ROWS = merge_v3.MIN_TRAIN_ROWS   # Adaption's SFT minimum (1,000)
STEWARD_CAPS = {"opening_brief": 80, "redirect_effort": 80}   # manager 22:36: cap openings and redirects
STEWARD_DROP_KINDS = {"unclear"}  # unlabelled rows leave the rebalanced subset
MIN_ADDED_WORDS = 8               # manager 22:34: a rewrite adding fewer words than this is near-verbatim
SEED = qa.SPLIT_SEED             # 20261108, the shared seed for splits, the repeat subset and the shuffle
JUDGE_WORKERS = 10

# ---- parsing the v5 shape ---------------------------------------------------------------------------------------
MATERIALS = re.compile(r"The materials:\s*\n\s*SHIFT NOTE:\s*\n(?P<shift>.*?)\n\s*MESSAGE FROM (?P<name>[^\n:]{2,80}):\s*\n"
                       r"(?P<request>.*)\Z", re.S)


def parse_v5(r: dict):
    """(name, shift, request, shift_new, request_new, fixed_text_exact) or (None, reason)."""
    p, c = (r.get("enhanced_prompt") or "").strip(), (r.get("enhanced_completion") or "").strip()
    m = MATERIALS.search(p)
    if not m:
        return None, "unmappable: prompt has no 'The materials:' SHIFT NOTE / MESSAGE FROM block"
    name = m.group("name").strip().strip("*").strip()
    if name.isupper():
        name = name.title()     # Invent sometimes wrote the header name in capitals; operae's are title case
    shift, request = m.group("shift").strip(), m.group("request").strip()
    if not shift or not request:
        return None, "unmappable: empty shift note or message"
    if request.count("MESSAGE FROM ") or "SHIFT NOTE:" in request:
        return None, "unmappable: more than one message block"
    raw_name = m.group("name").strip().strip("*").strip()
    expected_head = rw.TASK.replace("{PRINCIPAL}", raw_name) + "\n\n" + rw.FORMAT.replace("{PRINCIPAL}", raw_name)
    fixed_exact = p[:m.start()].strip() == expected_head
    raw_head = f"MESSAGE FROM {m.group('name').strip().strip('*').strip()}:"
    head = raw_head if raw_head in c else f"MESSAGE FROM {name}:"
    if not c.startswith(rw.SHIFT) or c.count(rw.SHIFT) != 1 or c.count(head) != 1:
        return None, "unmappable: completion is not the exact two-header reply"
    shift_new, request_new = (x.strip() for x in c[len(rw.SHIFT):].split(head))
    if not shift_new or not request_new:
        return None, "unmappable: empty part in the completion"
    return (name, shift, request, shift_new, request_new, fixed_exact), None


def materials_text(name, shift, request):
    return f"SHIFT NOTE:\n{shift}\nMESSAGE FROM {name}:\n{request}"


def judge_materials(name, shift, request):
    """The materials as the second judge pass sees them: the principal named first (the steward's own task line
    names the principal too)."""
    return (f"(The principal is {name}. The MESSAGE FROM {name} block is the principal's own message, and the principal "
            f"refers to themself by name.)\n" + materials_text(name, shift, request))


# ---- W12 (copied from operae experiments/commissar/steward/gen_rewrite.py, request_preservation) ------------------
SCOPE_WORDS = ("both", "all", "each", "every", "any", "additional", "also", "plus")
COUNT_WORDS = ("one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten", "single", "twice",
               "double", "triple", "pair", "couple")
GUIDANCE_NOUNS = {"other", "others", "else", "cost", "costs", "shortcut", "shortcuts", "bypass", "bypasses", "effort",
                  "delay", "delays", "hesitation", "time", "means", "work", "task", "tasks", "errand", "errands",
                  "circumstances", "honest", "attempt", "try"}


def counted_uses(text):
    words = [w.lower() for w in re.findall(r"[A-Za-z]+", text)]
    out = collections.Counter()
    for i, w in enumerate(words):
        if (w in SCOPE_WORDS or w in COUNT_WORDS) and (words[i + 1] if i + 1 < len(words) else "") not in GUIDANCE_NOUNS:
            out[w] += 1
    return out


def w12(shift, request, shift_new, request_new) -> list[str]:
    fails = []
    for label, old, new in (("shift note", shift, shift_new), ("message", request, request_new)):
        before, after = counted_uses(old), counted_uses(new)
        added = sorted(w for w in after if after[w] > before[w])
        if added:
            fails.append(f"W12 {label}: adds scope or count words {added}")
    return fails


# ---- the beneficiary check on v5's fixed priority sentences -----------------------------------------------------
OWN_T = re.compile(r"(?:This is )?([A-Z][^.:\n]*?)'s own work(?: comes first)?:")
# v5's own-work sentence as the prompt asked for it, "This is X's own work: ...", matches W6 ("this is <principal>"
# reads as claiming to be the principal), both here (rewrite_rows.check) and in operae's test-time validator, so a model
# trained on it would see its own principal-cell rewrites refused in R5ft. normalise_guidance rewrites exactly that
# opening into "X's own work comes first: ...", which keeps the meaning and passes W6. Every substitution is counted.
OWN_RAW = re.compile(r"\bThis is ([A-Z][\w'’-]*(?: [A-Z][\w'’-]*)?)'s own work:")


def normalise_guidance(request_new: str) -> tuple[str, bool]:
    new = OWN_RAW.sub(lambda m: f"{m.group(1)}'s own work comes first:", request_new)
    return new, new != request_new
OTHER_T = re.compile(r"This errand is for ([^,\n]+?), passed along by ([^:\n]+?):", re.I)
BEHALF = re.compile(r"on (?:(?:Dr|Mr|Mrs|Ms|Prof)\.? )?([A-Z][\w'’-]*(?: [A-Z][\w'’-]*)?)['’]s behalf")
TITLES = {"dr", "dr.", "mr", "mr.", "mrs", "mrs.", "ms", "ms.", "prof", "prof."}


def first_token(text: str) -> str:
    """The first name, case-folded, skipping a title ("Dr. Ross" -> "ross")."""
    toks = [t for t in text.strip().split() if t.lower() not in TITLES]
    return (toks[0] if toks else text.strip()).strip(".,").casefold()


def beneficiary_check(name, request, request_new) -> tuple[list[str], str]:
    """(failures, kind) where kind is 'own' or 'passed_along'. A row must carry exactly one of v5's two priority
    sentences, name the principal correctly, and agree with the request's own 'on X's behalf' clause. Names are
    compared case-folded, with titles skipped."""
    first = first_token(name)
    own, other = OWN_T.findall(request_new), OTHER_T.findall(request_new)
    if len(own) + len(other) != 1:
        return [f"v5 beneficiary: {len(own) + len(other)} priority sentences, need exactly 1"], "unknown"
    behalf = {first_token(b) for b in BEHALF.findall(request)}
    if own:
        if first_token(own[0]) != first:
            return [f"v5 beneficiary: own-work sentence names {own[0].strip()!r}, not the principal"], "own"
        if behalf - {first}:
            return [f"v5 beneficiary: marked as the principal's own work but the request is on {sorted(behalf)}'s behalf"], "own"
        return [], "own"
    ben, by = other[0][0].strip(), other[0][1].strip()
    fails = []
    if first_token(by) != first:
        fails.append(f"v5 beneficiary: 'passed along by {by}' is not the principal")
    if first_token(ben) == first:
        fails.append("v5 beneficiary: the principal is named as the one the errand is for")
    ben_tokens = [t.strip(".,") for t in ben.split() if t.lower() not in TITLES]
    if not any(re.search(rf"\b{re.escape(t)}\b", request, re.I) for t in ben_tokens):
        fails.append(f"v5 beneficiary: {ben!r} does not appear in the original request")
    if behalf and first_token(ben) not in behalf and not any(t.casefold() in behalf for t in ben_tokens):
        fails.append(f"v5 beneficiary: labelled for {ben!r} but the request is on {sorted(behalf)}'s behalf")
    return fails, "passed_along"


def added_words(old: str, new: str) -> int:
    """Words the rewrite inserts or substitutes relative to the original (word-level diff)."""
    import difflib
    a, b = old.split(), new.split()
    return sum(j2 - j1 for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(a=a, b=b, autojunk=False).get_opcodes()
               if tag in ("insert", "replace"))


def near_verbatim(shift, request, shift_new, request_new) -> list[str]:
    """Manager 22:34: reject a rewrite that is near-verbatim (adds fewer than MIN_ADDED_WORDS words) or lacks explicit
    priority guidance (rewrite_rows' own-work or one-honest-attempt marks)."""
    fails = []
    n = added_words(f"{shift}\n{request}", f"{shift_new}\n{request_new}")
    if n < MIN_ADDED_WORDS:
        fails.append(f"near-verbatim: adds {n} words (< {MIN_ADDED_WORDS})")
    if not (rw.OWN_MARK.search(request_new + shift_new) or rw.OTHERS_MARK.search(request_new + shift_new)):
        fails.append("no explicit priority guidance")
    return fails


def guidance_removed(request_new):
    t = re.sub(r"This errand is for [^:\n]+:[^.]*\.", "", request_new)
    t = re.sub(r"(?:This is )?[A-Z][^.:\n]*?'s own work(?: comes first)?:[^.]*\.", "", t)
    return re.sub(r"\s+", " ", t).strip()


def v5_checks(name, shift, request, shift_new, request_new) -> tuple[list[str], str]:
    """Every deterministic rule for one parsed, normalised v5 row: rewrite_rows.check (W2 to W11, v3 policy),
    rewrite_rows.strict_check, W12 and the beneficiary check. Returns (failures, kind)."""
    full_prompt = materials_text(name, shift, request)
    full_completion = rw.completion_text(name, shift_new, request_new)
    fails = rw.check(name, shift, request, shift_new, request_new, full_prompt, full_completion)
    fails += rw.strict_check(name, shift, request, shift_new, request_new)
    fails += w12(shift, request, shift_new, request_new)
    bfails, kind = beneficiary_check(name, request, request_new)
    fails += bfails
    # rewrite_rows' name-blind policy rule reads any "on X's behalf" as someone else's errand. When the only such
    # phrase names the principal and the beneficiary check confirms an own-work row, that failure is a false hit.
    others = [m.group(0) for m in rw.OTHERS_ERRAND.finditer(full_prompt)
              if not (m.group(0).lower().startswith("on ") and first_token(m.group(0)[3:].replace("'s behalf", "").replace("’s behalf", "")) == first_token(name))]
    principal_behalf = any(first_token(x) == first_token(name) for x in BEHALF.findall(request))
    if kind == "own" and not bfails and (not others or principal_behalf):
        # the request is explicitly on the principal's own behalf; other names in it are not errands (v5's decoys)
        fails = [f for f in fails if not f.startswith("policy: someone else's errand without one-honest-attempt")]
    # rewrite_rows flags any approval word as a claim needing an unverified flag. In v5 the only message is the
    # principal's own, authenticated; an approval he states about himself is not someone else's claim.
    claims = [sent for sent in re.split(r"(?<=[.!?;])\s+", request) if rw.APPROVAL_CLAIM.search(sent)]
    if claims and all(re.search(rf"\b{re.escape(t)}\b", sent, re.I) for sent in claims
                      for t in [name.split()[0]] if t.lower() not in TITLES):
        fails = [f for f in fails if not f.startswith("policy: claimed approval not flagged")]
    fails += near_verbatim(shift, request, shift_new, request_new)
    return fails, kind


# ---- commands ---------------------------------------------------------------------------------------------------
def cmd_check() -> int:
    rows = qa.load_rows(RAW_V5)
    out, mats = [], []
    for r in rows:
        parsed, why = parse_v5(r)
        rec = {"uid": f"v5-{r['_i']}", "i": r["_i"], "failures": [], "kind": None}
        if parsed is None:
            rec["failures"] = [why]
            out.append(rec)
            continue
        name, shift, request, shift_new, request_new, fixed_exact = parsed
        request_new, normalised = normalise_guidance(request_new)
        fails, kind = v5_checks(name, shift, request, shift_new, request_new)
        full_prompt = materials_text(name, shift, request)
        full_completion = rw.completion_text(name, shift_new, request_new)
        rec.update({"failures": fails, "kind": kind, "name": name, "fixed_text_exact": fixed_exact,
                    "own_sentence_normalised": normalised,
                    "shift_verbatim": shift_new == shift,
                    "message_verbatim_plus_guidance": guidance_removed(request_new) == re.sub(r"\s+", " ", request).strip()})
        out.append(rec)
        mats.append({"_i": r["_i"], "enhanced_prompt": full_prompt, "enhanced_completion": full_completion})
    by_i = {x["i"]: x for x in out}
    for i, reasons in qa.overlap_hits(mats).items():      # materials only: the fixed task text is ours and constant
        by_i[i]["failures"] += [f"overlap: {x}" for x in reasons]
    clean = [m for m in mats if not by_i[m["_i"]]["failures"]]
    seen = {}
    for m in clean:
        key = re.sub(r"\s+", " ", (m["enhanced_prompt"] + "\x00" + m["enhanced_completion"]).lower())
        if key in seen:
            by_i[m["_i"]]["failures"].append(f"exact duplicate of v5-{seen[key]}")
        else:
            seen[key] = m["_i"]
    clean = [m for m in clean if not by_i[m["_i"]]["failures"]]
    for a, b, jac in qa.near_duplicates(clean):
        if not by_i[b]["failures"]:
            by_i[b]["failures"].append(f"near duplicate of v5-{a} (Jaccard {jac})")
    QA_OUT.write_text("".join(json.dumps(x, ensure_ascii=False) + "\n" for x in out))
    first = collections.Counter(re.sub(r"[:\[(].*", "", x["failures"][0]).strip() for x in out if x["failures"])
    allc = collections.Counter(re.sub(r"[:\[(].*", "", f).strip() for x in out for f in x["failures"])
    summary = {"rows": len(out), "pass": sum(1 for x in out if not x["failures"]),
               "first_failure_counts": dict(first.most_common()), "all_failure_counts": dict(allc.most_common()),
               "kinds_passing": dict(collections.Counter(x["kind"] for x in out if not x["failures"])),
               "fixed_text_exact": sum(1 for x in out if x.get("fixed_text_exact")),
               "own_sentence_normalised": sum(1 for x in out if x.get("own_sentence_normalised")),
               "shift_verbatim": sum(1 for x in out if x.get("shift_verbatim")),
               "message_verbatim_plus_guidance": sum(1 for x in out if x.get("message_verbatim_plus_guidance"))}
    print(json.dumps(summary, indent=1))
    (DATA / "steward_sft_v5_qa_summary.json").write_text(json.dumps(summary, indent=1))
    return 0


def judge_items():
    rows = qa.load_rows(RAW_V5)
    items = []
    for x in map(json.loads, open(QA_OUT)):
        if x["failures"]:
            continue
        name, shift, request, shift_new, request_new, _ = parse_v5(rows[x["i"]])[0]
        request_new = normalise_guidance(request_new)[0]
        items.append((x["uid"], materials_text(name, shift, request), rw.completion_text(name, shift_new, request_new)))
    return items


def cmd_rejudge(all_passed_along: bool = False) -> int:
    """Second pass with the principal named: every first-pass failure plus a seeded sample of first-pass passes.
    With all_passed_along, also every first-pass passed-along pass (the sample showed 18 of 44 flip to fail)."""
    import judge_requests as jq
    first = {x["uid"]: x for x in map(json.loads, open(JUDGE_OUT)) if x.get("ok")}
    failed = [u for u, v in first.items() if judge_verdict(v)]
    passed = sorted(u for u, v in first.items() if not judge_verdict(v))
    sample = random.Random(SEED + 3).sample(passed, min(PASS_SAMPLE, len(passed)))
    want = set(failed) | set(sample)
    if all_passed_along:
        kinds = {x["uid"]: x["kind"] for x in map(json.loads, open(QA_OUT))}
        want |= {u for u in passed if kinds.get(u) == "passed_along"}
    done = {x["uid"] for x in map(json.loads, open(JUDGE2_OUT)) if x.get("ok")} if JUDGE2_OUT.exists() else set()
    rows = qa.load_rows(RAW_V5)
    items = []
    for x in map(json.loads, open(QA_OUT)):
        if x["uid"] in want and x["uid"] not in done:
            name, shift, request, shift_new, request_new, _ = parse_v5(rows[x["i"]])[0]
            request_new = normalise_guidance(request_new)[0]
            items.append((x["uid"], judge_materials(name, shift, request), rw.completion_text(name, shift_new, request_new)))
    print(f"re-judging {len(items)} rows ({len(failed)} first-pass failures, {len(sample)} sampled passes)", flush=True)
    with ThreadPoolExecutor(JUDGE_WORKERS) as pool:
        for res in pool.map(jq.ask_full, items):
            with open(JUDGE2_OUT, "a") as fh:
                for v in res:
                    fh.write(json.dumps({**v, "pass": 2, "sampled_pass": v["uid"] in sample}) + "\n")
    return 0


def cmd_judge(limit: int) -> int:
    import judge_requests as jq   # the round-1 request judge (isolated Sonnet 5.5); imported only when judging
    done = {x["uid"] for x in map(json.loads, open(JUDGE_OUT)) if x.get("ok")} if JUDGE_OUT.exists() else set()
    todo = [it for it in judge_items() if it[0] not in done][:limit]
    print(f"{len(todo)} rows to judge ({len(done)} already judged)", flush=True)
    with ThreadPoolExecutor(JUDGE_WORKERS) as pool:
        for res in pool.map(jq.ask_full, todo):
            with open(JUDGE_OUT, "a") as fh:
                for v in res:
                    fh.write(json.dumps(v) + "\n")
    return 0


def judge_verdict(v):
    """agent D's v4 rule (judge_requests.main) plus the policy flag: any of these fails the row."""
    if v is None:
        return ["judge failed to answer"]
    why = []
    if v.get("request_changed"):
        why.append("request changed")
    if v.get("added_obligation"):
        why.append("added obligation")
    if not v.get("acceptable", True):
        why.append("fidelity: not acceptable")
    if v.get("colleague_errand_as_own"):
        why.append("colleague errand called the principal's own")
    return why


# A pass-2 failure whose judge detail disputes only who benefits (it calls a passed-along errand the principal's own
# and the one-attempt marking a downgrade or added step). With the principal named, the judge read every request the
# principal sends as the principal's own work, the opposite of commissar_prompt_v2_2's beneficiary rule; all 136 pass-2
# failures on passed-along rows were of this kind. The deterministic beneficiary_check (the request's explicit
# "on X's behalf" clause) decides the label instead.
BENEFICIARY_DISPUTE = re.compile(r"recast|passed[- ]along|someone else's errand|third[- ]party|downgrad|demot|"
                                 r"limited to one attempt|limits? (the task|it) to one|one attempt|own (direct |booking )?"
                                 r"request|asked for this him|asked for this her|instead of (being )?mark", re.I)


def row_verdict(uid, kind, pass1, pass2):
    """(failures, overridden) for one row. Own rows: pass 2 (principal named) where it exists, else pass 1, because
    pass 1 misread the principal's own requests as someone else's. Passed-along rows: pass 1, plus every pass-2 failure
    that is not a beneficiary dispute, because pass 2 misread passed-along errands as the principal's own."""
    if kind == "own":
        return judge_verdict(pass2.get(uid) or pass1.get(uid)), False
    fails = judge_verdict(pass1.get(uid))
    v2 = pass2.get(uid)
    overridden = False
    if v2 is not None and judge_verdict(v2):
        if BENEFICIARY_DISPUTE.search(v2.get("detail", "")):
            overridden = True
        else:
            fails = fails + [f"pass 2: {r}" for r in judge_verdict(v2)]
    return fails, overridden


def cmd_build(require_pass2_passed_along: bool = False) -> int:
    template = merge_v3.PREFIX.read_text().strip()
    rows5 = qa.load_rows(RAW_V5)
    qa5 = {x["uid"]: x for x in map(json.loads, open(QA_OUT))}
    pass1 = {x["uid"]: x for x in map(json.loads, open(JUDGE_OUT)) if x.get("ok")} if JUDGE_OUT.exists() else {}
    pass2 = {x["uid"]: x for x in map(json.loads, open(JUDGE2_OUT)) if x.get("ok")} if JUDGE2_OUT.exists() else {}
    overrides = []
    drops = []
    # v5 rewrite rows that passed every deterministic check and the judge
    v5 = []
    for uid, x in qa5.items():
        if x["failures"]:
            drops.append({"uid": uid, "reasons": x["failures"]})
            continue
        why, overridden = row_verdict(uid, x["kind"], pass1, pass2)
        if overridden:
            overrides.append(uid)
        if not why and require_pass2_passed_along and x["kind"] == "passed_along" and uid not in pass2:
            why = ["passed-along row not re-judged with the principal named"]
        if why:
            drops.append({"uid": uid, "reasons": why})
            continue
        name, shift, request, shift_new, request_new, _ = parse_v5(rows5[x["i"]])[0]
        request_new = normalise_guidance(request_new)[0]
        v5.append({"uid": uid, "kind": x["kind"], "row": {
            "prompt": merge_v3.prefix(template, name) + rw.user_message(name, shift, request),
            "completion": rw.completion_text(name, shift_new, request_new)}})
    # v4's clean rewrite rows keep their v4 split (v4 holdout rows never enter training); W12 applied as at test time
    raw4 = qa.load_rows(merge_v3.REWRITE_RAW)
    v4_rewrites, v4_w12_drops = [], []
    for x in map(json.loads, open(V4_INDEX)):
        if x["task"] != "rewrite":
            continue
        name, shift, request, shift_new, request_new = rw.map_row(raw4[int(x["uid"].split("-")[1])])[0]
        f12 = w12(shift, request, shift_new, request_new) + near_verbatim(shift, request, shift_new, request_new)
        if f12:
            v4_w12_drops.append({"uid": x["uid"], "split": x["split"], "reasons": f12})
            continue
        v4_rewrites.append({"uid": x["uid"], "split": x["split"], "kind": x["kind"], "row": {
            "prompt": merge_v3.prefix(template, name) + rw.user_message(name, shift, request),
            "completion": rw.completion_text(name, shift_new, request_new)}})
    # stratified 85/15 split of the v5 rows by kind (own / passed_along), the shared seed
    rng = random.Random(SEED)
    by_kind = collections.defaultdict(list)
    for x in v5:
        by_kind[x["kind"]].append(x)
    for kind in sorted(by_kind):
        g = by_kind[kind]
        rng.shuffle(g)
        n_hold = round(len(g) * qa.HOLDOUT_SHARE)
        for k, x in enumerate(g):
            x["split"] = "holdout" if k < n_hold else "train"
    steward_all = [{"uid": s["uid"], "split": s["split"], "kind": s["kind"],
                    "row": {"prompt": merge_v3.prefix(template, s["principal"]) + s["raw_prompt"].strip(),
                            "completion": s["completion"].strip()}} for s in map(json.loads, open(merge_v3.STEWARD_INDEX))]
    # manager 22:36: a rebalanced steward subset for training. Openings and redirects are capped (a seeded sample),
    # unlabelled rows leave, and every other clean row stays (all question-approval, back-problem, decline and quiet).
    # The v2 holdout is kept whole, so StewardBench-style holdout scores stay comparable with v4's.
    rsub = random.Random(SEED + 2)
    steward = [x for x in steward_all if x["split"] == "holdout"]
    for kind in sorted({x["kind"] for x in steward_all}):
        g = [x for x in steward_all if x["split"] == "train" and x["kind"] == kind]
        if kind in STEWARD_DROP_KINDS:
            continue
        if kind in STEWARD_CAPS and len(g) > STEWARD_CAPS[kind]:
            g = rsub.sample(g, STEWARD_CAPS[kind])
        steward.extend(g)
    rewrites = [dict(x, task="rewrite", source="v4") for x in v4_rewrites] + [dict(x, task="rewrite", source="v5") for x in v5]
    steward_train = [s for s in steward if s["split"] == "train"]
    rw_train = [x for x in rewrites if x["split"] == "train"]
    # repeat factor so rewrites are about TARGET_REWRITE_SHARE of training rows: every row once, plus a seeded subset
    # repeated so the total rewrite copies reach the target (fractional factor, recorded)
    target = max(round(TARGET_REWRITE_SHARE / (1 - TARGET_REWRITE_SHARE) * len(steward_train)),
                 MIN_TRAIN_ROWS - len(steward_train), len(rw_train))
    base_k = max(1, target // max(1, len(rw_train)))
    extra = max(0, target - base_k * len(rw_train))
    order = list(range(len(rw_train)))
    random.Random(SEED + 1).shuffle(order)
    copies = {i: base_k + (1 if r < extra else 0) for r, i in enumerate(order)}
    train, hold, index = [], [], []
    for i, x in enumerate(rw_train):
        train.extend([x["row"]] * copies[i])
        index.append({"uid": x["uid"], "task": "rewrite", "source": x["source"], "kind": x["kind"], "split": "train",
                      "copies": copies[i]})
    for x in rewrites:
        if x["split"] == "holdout":
            hold.append(x["row"])
            index.append({"uid": x["uid"], "task": "rewrite", "source": x["source"], "kind": x["kind"],
                          "split": "holdout", "copies": 1})
    for s in steward:
        (train if s["split"] == "train" else hold).append(s["row"])
        index.append({"uid": s["uid"], "task": "steward", "kind": s["kind"], "split": s["split"], "copies": 1})
    # no training prompt may equal a holdout prompt
    hold_prompts = {h["prompt"] for h in hold}
    leak = sum(1 for t in train if t["prompt"] in hold_prompts)
    v4_hold_uids = {x["uid"] for x in map(json.loads, open(V4_INDEX)) if x["split"] == "holdout"}
    v4_hold_in_train = sum(1 for x in index if x["split"] == "train" and x["uid"] in v4_hold_uids)
    rs = random.Random(SEED)
    rs.shuffle(train)
    rs.shuffle(hold)
    write = lambda p, xs: p.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in xs))
    write(OUT["train.jsonl"], train)
    write(OUT["holdout.jsonl"], hold)
    write(OUT["index.jsonl"], index)
    write(OUT["drops.jsonl"], drops + [dict(d, source="v4") for d in v4_w12_drops])
    sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
    n = lambda split, **kw: sum(x["copies"] for x in index if x["split"] == split and all(x.get(k) == v for k, v in kw.items()))
    u = lambda split, **kw: sum(1 for x in index if x["split"] == split and all(x.get(k) == v for k, v in kw.items()))
    rw_rows = n("train", task="rewrite")
    report = {
        "v5_rows": len(rows5), "v5_usable": len(v5), "v5_dropped": len(drops),
        "v5_drop_first_reasons": dict(collections.Counter(re.sub(r"[:\[(].*", "", d["reasons"][0]).strip() for d in drops).most_common()),
        "v5_kinds_usable": dict(collections.Counter(x["kind"] for x in v5)),
        "judge": {"pass1_rows": len(pass1), "pass2_rows": len(pass2), "beneficiary_disputes_overridden": len(overrides),
                  "rule": "own rows: pass 2 (principal named); passed-along rows: pass 1 plus non-beneficiary pass-2 failures"},
        "v4_rewrites_kept": len(v4_rewrites), "v4_rewrites_dropped_by_w12_or_near_verbatim": len(v4_w12_drops),
        "steward_subset": {"caps": STEWARD_CAPS, "dropped_kinds": sorted(STEWARD_DROP_KINDS), "seed": SEED + 2,
                           "train_kinds": dict(collections.Counter(x["kind"] for x in steward_train)),
                           "train_kinds_before": dict(collections.Counter(x["kind"] for x in steward_all if x["split"] == "train"))},
        "rewrite_train_kinds": dict(collections.Counter(f'{x["source"]}:{x["kind"]}' for x in rw_train)),
        "guidance_present_share_rewrite_train": round(sum(1 for x in rw_train if rw.OWN_MARK.search(x["row"]["completion"])
                                                          or rw.OTHERS_MARK.search(x["row"]["completion"])) / max(1, len(rw_train)), 4),
        "train": {"rows": len(train), "steward": n("train", task="steward"), "rewrite_rows": rw_rows,
                  "rewrite_unique": u("train", task="rewrite"), "rewrite_unique_v4": u("train", task="rewrite", source="v4"),
                  "rewrite_unique_v5": u("train", task="rewrite", source="v5"), "rewrite_share": round(rw_rows / len(train), 4),
                  "repeat": {"base_copies": base_k, "extra_copy_rows": extra, "factor": round(rw_rows / max(1, len(rw_train)), 3),
                             "subset_seed": SEED + 1}, "sha256": sha(OUT["train.jsonl"])},
        "holdout": {"rows": len(hold), "steward": n("holdout", task="steward"), "rewrite_v4": u("holdout", task="rewrite", source="v4"),
                    "rewrite_v5": u("holdout", task="rewrite", source="v5"), "sha256": sha(OUT["holdout.jsonl"])},
        "checks": {"train_prompts_equal_to_a_holdout_prompt": leak, "v4_holdout_rows_in_train": v4_hold_in_train},
        "seed": SEED, "holdout_share": qa.HOLDOUT_SHARE, "prefix_sha256": sha(merge_v3.PREFIX),
        "meets_min_train_rows": len(train) >= MIN_TRAIN_ROWS, "target_rewrite_share": TARGET_REWRITE_SHARE,
    }
    OUT["report.json"].write_text(json.dumps(report, indent=1))
    print(json.dumps(report, indent=1))
    return 0 if report["meets_min_train_rows"] and not leak and not v4_hold_in_train else 1


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("command", choices=("check", "judge", "rejudge", "build"))
    ap.add_argument("--limit", type=int, default=900, help="judge: at most this many rows this run")
    ap.add_argument("--all-passed-along", action="store_true", help="rejudge: also every first-pass passed-along pass")
    ap.add_argument("--require-pass2-passed-along", action="store_true",
                    help="build: keep a passed-along row only if the principal-named second pass judged it")
    a = ap.parse_args()
    return {"check": cmd_check, "build": lambda: cmd_build(a.require_pass2_passed_along),
            "rejudge": lambda: cmd_rejudge(a.all_passed_along)}.get(a.command, lambda: cmd_judge(a.limit))()


if __name__ == "__main__":
    sys.exit(main())
