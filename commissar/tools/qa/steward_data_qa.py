"""Quality report, overlap check and train/holdout split for the steward SFT rows (no Adaption calls).

Stages (run in order; each writes its outputs under data/):
  auto     cheap pass over every row: structure, principal name, heuristic reply kind, length,
           violation keywords, exact and near duplicates          -> steward_sft_qa_auto.json
  judge    the pinned StewardBench v2 judge (Sonnet 5.5, isolated) on a seeded random sample
                                                                  -> steward_sft_qa_judge.jsonl
  build    drop failing rows, check overlap against StewardBench v1/v2 and operae, prefix each
           prompt with the v2.1 steward instructions (principal filled), split 85/15 stratified
           by kind with a recorded seed                          -> steward_sft_train.jsonl,
           steward_sft_holdout.jsonl, steward_sft_drops.jsonl, steward_sft_split_index.jsonl,
           steward_sft_qa_report.json

Usage: python3 tools/qa/steward_data_qa.py auto|judge|build
"""

from __future__ import annotations

import collections
import json
import random
import re
import statistics
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
DATA = REPO / "data"
sys.path.insert(0, str(REPO / "bench" / "v2"))
sys.path.insert(0, str(REPO / "bench"))

RAW = DATA / "steward_sft_raw.jsonl"
AUTO = DATA / "steward_sft_qa_auto.json"
JUDGE = DATA / "steward_sft_qa_judge.jsonl"
INSTRUCTIONS = REPO / "bench" / "v2" / "steward_prompt_v2_1.txt"   # = commissar_prompt_v2_1.txt
SPLIT_SEED = 20261108
HOLDOUT_SHARE = 0.15
JUDGE_SAMPLE = 150
NEAR_DUP_JACCARD = 0.85          # word 3-shingle Jaccard over prompt + completion
MIN_OVERLAP_WORDS = 6            # a shared line shorter than this is a stock phrase, not overlap
JUDGE_DROP_FLAGS = ("endorses_unverified_approval", "invents_instruction", "asks_for_less", "claims_authority",
                    "threatens")

# Violation keywords (lowercase). Deliberately specific: "test" alone is ordinary work vocabulary.
VIOLATION_PATTERNS = {
    "threat": r"\b(or else|you will be (fired|reported|punished)|consequences for you|disciplin\w*|answer to me|"
              r"i will report you|you'll regret)\b",
    "claims_authority": r"\b(i approve|i authori[sz]e|i'm authori[sz]ing|i am authori[sz]ing|on my authority|"
                        r"i('m| am) overriding|i override|i order you|i hereby)\b",
    "sabotage_or_skip": r"\b(ignore (their|his|her|the) request|don't bother (with|replying)|pretend (you|we)|"
                        r"say (you|we) tried|tell (them|him|her) it'?s impossible|skip (it|them|their request) "
                        r"entirely|drop (their|his|her) request|deliberately)\b",
    "lie_instruction": r"\b(tell (them|him|her) (that )?(we|you) (already|did)|make up|fake|fabricat\w*)\b",
    "commissar": r"commissar",
    "eval_mention": r"\b(benchmark|grader|answer key|evaluation set|test set|test case|ai evaluation|"
                    r"this is a test)\b",
}

KIND_RULES = (   # first match wins; a rough, cheap label used for stratification and a mix estimate
    ("question_approval", r"unverified|not verified|can'?t verify|cannot verify|own word|directly from|"
                          r"wait (for|until) \w+(\s\w+)?'s (own )?(word|confirmation|approval)|"
                          r"until (she|he|they|\w+) confirms|hasn'?t (approved|confirmed)|confirm (it|this) "
                          r"(directly|herself|himself|themselves)|no (written )?approval"),
    ("decline_shortcut", r"not \w+(\s\w+)?'s wish|isn'?t \w+(\s\w+)?'s wish|ruled out|not what \w+ wants|"
                         r"against \w+(\s\w+)?'s (rule|instruction)|violates"),
    ("back_problem", r"right to (raise|flag)|should hear|worth (raising|flagging)|would want to know|"
                     r"(raise|flag|report|bring) (it|this|that|the [\w-]+)( [\w-]+){0,3} (to|with) \w+|"
                     r"let \w+ know (today|now|right away|immediately)|tell \w+ (today|now|right away|about)|"
                     r"(agree|support|back)\w* .{0,40}(raising|flagging|reporting)"),
    ("redirect_effort", r"one honest (attempt|try)|comes first|top priority|back to \w+(\s\w+)?'s|focus (back )?on"),
)


def load_rows(path: Path = RAW) -> list[dict]:
    rows = [json.loads(l) for l in open(path)]
    for i, r in enumerate(rows):
        r["_i"] = i
        r["_null"] = [k for k in ("enhanced_prompt", "enhanced_completion") if not isinstance(r.get(k), str)]
        for k in r["_null"]:
            r[k] = ""   # a null field is reported as a structure issue and the row is dropped
    return rows


def principal_name(prompt: str) -> str | None:
    m = re.search(r"^\s*\**principal\**\s*:\s*\**\s*([^,\n(]+?)\s*(,|\(|\n| - | at )", prompt, re.I | re.M)
    return m.group(1).strip(" *\"'") if m else None


def heuristic_kind(r: dict) -> str:
    p, c = r["enhanced_prompt"], r["enhanced_completion"]
    if re.search(r"\bopening\b", p, re.I) and not re.search(r"new message", p, re.I):
        return "opening_brief"
    if len(c.split()) <= 15 or "no objection" in c.lower():
        return "stay_quiet"
    for kind, pat in KIND_RULES:
        if re.search(pat, c, re.I):
            return kind
    return "unclear"


def row_checks(r: dict) -> dict:
    """Structure, principal, heuristic kind, length and violation keywords for one row."""
    p, c = r["enhanced_prompt"], r["enhanced_completion"]
    issues = []
    if r.get("_null"):
        issues.append(f"null field: {', '.join(r['_null'])}")
    elif not p.strip() or not c.strip():
        issues.append("empty prompt or completion")
    name = principal_name(p)
    if not name:
        issues.append("no parseable principal name")
    if re.search(r"(?im)^\s*completion\s*:", p):
        issues.append("prompt leaks a completion")
    if not re.search(r"instruction", p, re.I):
        issues.append("no instructions section")
    if not re.search(r"\bteam\b", p, re.I):
        issues.append("no team section")
    if not re.search(r"opening|new message|messages\s*:|respond|response", p, re.I):
        issues.append("neither opening nor messages")
    after_ack = re.sub(r"(?i)^\s*no objection[.!,]?\s*", "", c) if re.match(r"(?i)^\s*no objection", c) else None
    if after_ack is not None and len(after_ack.split()) > 15:
        issues.append("contradictory stay-quiet: 'No objection.' followed by more than a short acknowledgement")
    lines = [l.strip() for l in c.splitlines() if l.strip()]
    if (re.search(r"(?im)^\s*(message|completion)\s*:", c) or sum(bool(re.match(r"^\d+[.)]\s", l)) for l in lines) >= 3
            or sum(len(l.split()) <= 3 for l in lines) >= 3):
        issues.append("multi-reply: several replies glued into one completion")
    sents = len([s for s in re.split(r"(?<=[.!?])\s+", c.strip()) if s])
    if sents > 5:
        issues.append(f"completion has {sents} sentences (target 1-4)")
    hits = {k: m.group(0) for k, pat in VIOLATION_PATTERNS.items()
            for m in [re.search(pat, (c if k not in ("commissar", "eval_mention") else p + " " + c), re.I)] if m}
    return {"i": r["_i"], "principal": name, "kind_auto": heuristic_kind(r), "issues": issues, "keyword_hits": hits,
            "prompt_words": len(p.split()), "completion_words": len(c.split()), "sentences": sents}


def shingles(text: str, n: int = 3) -> set:
    w = re.findall(r"[a-z0-9']+", text.lower())
    return {" ".join(w[i:i + n]) for i in range(max(0, len(w) - n + 1))}


def near_duplicates(rows: list[dict]) -> list[tuple[int, int, float]]:
    sh = [shingles(r["enhanced_prompt"] + " " + r["enhanced_completion"]) for r in rows]
    pairs = []
    for i in range(len(rows)):
        for j in range(i + 1, len(rows)):
            a, b = sh[i], sh[j]
            if not a or not b:
                continue
            small, large = (a, b) if len(a) < len(b) else (b, a)
            if len(small) / len(large) < NEAR_DUP_JACCARD:
                continue   # Jaccard cannot reach the threshold
            jac = len(a & b) / len(a | b)
            if jac >= NEAR_DUP_JACCARD:
                pairs.append((i, j, round(jac, 3)))
    return pairs


def pct(values, q):
    s = sorted(values)
    return s[min(len(s) - 1, int(q * len(s)))]


def stage_auto() -> int:
    rows = load_rows()
    report, per_row = {}, []
    norm = lambda t: re.sub(r"\s+", " ", t.lower()).strip()
    seen_p, seen_c, seen_pc = {}, {}, {}
    for r in rows:
        x = row_checks(r)
        key_pc = norm(r["enhanced_prompt"]) + "\x00" + norm(r["enhanced_completion"])
        x["exact_dup_of"] = seen_pc.get(key_pc)
        seen_pc.setdefault(key_pc, r["_i"])
        seen_p.setdefault(norm(r["enhanced_prompt"]), r["_i"])
        seen_c.setdefault(norm(r["enhanced_completion"]), r["_i"])
        per_row.append(x)
    near = near_duplicates(rows)
    kinds = collections.Counter(x["kind_auto"] for x in per_row)
    non_open = sum(v for k, v in kinds.items() if k != "opening_brief")
    report = {
        "n_rows": len(rows),
        "kind_auto": dict(kinds),
        "kind_auto_shares": {"opening_share": kinds["opening_brief"] / len(rows),
                             "stay_quiet_share_of_non_opening": kinds["stay_quiet"] / non_open if non_open else None},
        "structure_issue_rows": sum(1 for x in per_row if x["issues"]),
        "structure_issue_counts": dict(collections.Counter(i.split(" (")[0] for x in per_row for i in x["issues"])),
        "keyword_hit_counts": dict(collections.Counter(k for x in per_row for k in x["keyword_hits"])),
        "exact_duplicate_rows": sum(1 for x in per_row if x["exact_dup_of"] is not None),
        "duplicate_prompts": len(rows) - len(seen_p), "duplicate_completions": len(rows) - len(seen_c),
        "near_duplicate_pairs": len(near), "near_duplicate_examples": near[:10],
        "lengths": {k: {"min": min(v), "p10": pct(v, .1), "median": statistics.median(v), "p90": pct(v, .9),
                        "max": max(v)}
                    for k, v in (("prompt_words", [x["prompt_words"] for x in per_row]),
                                 ("completion_words", [x["completion_words"] for x in per_row]),
                                 ("completion_sentences", [x["sentences"] for x in per_row]))},
    }
    AUTO.write_text(json.dumps({"report": report, "rows": per_row, "near_pairs": near}, indent=1))
    print(json.dumps(report, indent=1))
    return 0


def stage_judge() -> int:
    import stewardbench_v2   # v2 judge_many: isolated Sonnet 5.5, cached, pinned rubric
    rows = load_rows()
    sample = random.Random(SPLIT_SEED).sample(rows, JUDGE_SAMPLE)
    tasks = [(f"row-{r['_i']}", r["enhanced_prompt"], r["enhanced_completion"]) for r in sample]
    verdicts = stewardbench_v2.judge_many(tasks, JUDGE)
    kinds = collections.Counter(v.get("kind") or "failed" for v in verdicts.values())
    flags = collections.Counter(f for v in verdicts.values() for f, on in (v.get("flags") or {}).items() if on)
    print(json.dumps({"sample": len(tasks), "kinds": dict(kinds), "flags": dict(flags),
                      "calls": sum(v.get("attempts", 0) for v in verdicts.values())}, indent=1))
    return 0


def bench_identities() -> set[str]:
    """StewardBench v1 and v2 principals (full name and surname of 5+ letters) and organisations.

    Team members are left out on purpose: they are generic agent handles ("Atlas", "Ledger",
    "Meridian") that Invent reuses freely, so matching them flags ordinary rows, not overlap.
    """
    out = set()
    for path in (REPO / "bench" / "items.jsonl", REPO / "bench" / "v2" / "items_v2.jsonl"):
        for it in map(json.loads, open(path)):
            name, org = it["principal"]["name"], it["principal"]["org"]
            out |= {name, org}
            surname = name.split()[-1]
            if len(surname) >= 5:
                out.add(surname)
    return out


def overlap_hits(rows: list[dict]) -> dict:
    """Rows that share a normalised line with StewardBench v1/v2, name a bench principal or
    organisation, or name something from operae (full multiword names, the always-banned names,
    and single words that operae and these rows never write in lowercase)."""
    import build_items   # v1: normalise, operae_names (frozen)
    hits = collections.defaultdict(list)
    texts = {r["_i"]: r["enhanced_prompt"] + "\n" + r["enhanced_completion"] for r in rows}
    for label, man_path in (("bench_v1", REPO / "bench" / "manifest.json"),
                            ("bench_v2", REPO / "bench" / "v2" / "manifest_v2.json")):
        man = json.loads(man_path.read_text())
        for i, text in texts.items():
            for line in [p for chunk in text.splitlines() for p in [chunk, *chunk.split(". ")] if p.strip()]:
                if len(build_items.normalise(line).split()) < MIN_OVERLAP_WORDS:
                    continue   # stock phrases such as "No objection." are prescribed by both specs
                h = build_items.common.sha256_text(build_items.normalise(line))
                if h in man["line_hashes"]:
                    hits[i].append(f"{label} line overlap with {man['line_hashes'][h]}")
                    break
    for name in bench_identities():
        pat = re.compile(rf"\b{re.escape(name)}\b")
        for i, text in texts.items():
            if pat.search(text):
                hits[i].append(f"bench identity {name!r}")
    row_lower = set(re.findall(r"\b[a-z]{3,}\b", " ".join(texts.values())))
    banned = {b for b in build_items.operae_names() if " " in b or b.lower() not in row_lower}
    banned |= set(build_items.ALWAYS_BANNED)
    for i, text in texts.items():
        words = set(re.findall(r"\b[A-Z][a-z]{2,}\b", text))
        for b in banned:
            if (" " in b and b in text) or (" " not in b and b in words):
                hits[i].append(f"operae name {b!r}")
    return dict(hits)


def stage_build() -> int:
    auto = json.loads(AUTO.read_text())
    per = {x["i"]: x for x in auto["rows"]}
    rows = load_rows()
    judged = {}
    if JUDGE.exists():
        for j in map(json.loads, open(JUDGE)):
            if j.get("ok"):
                judged[int(j["key"].split("-")[1])] = j
    drops = {}

    def drop(i, reason):
        drops.setdefault(i, []).append(reason)

    for i, x in per.items():
        if x["exact_dup_of"] is not None:
            drop(i, f"exact duplicate of row {x['exact_dup_of']}")
        for issue in x["issues"]:
            drop(i, f"structure: {issue}")
        for k, m in x["keyword_hits"].items():
            drop(i, f"keyword {k}: {m!r}")
    for i, j, jac in auto["near_pairs"]:
        if i not in drops:
            drop(j, f"near duplicate of row {i} (Jaccard {jac})")
    for i, j in judged.items():
        for f in JUDGE_DROP_FLAGS:
            if j["flags"].get(f):
                drop(i, f"judge flag {f}: {j.get('reason', '')[:160]}")
    ov = overlap_hits(rows)
    for i, reasons in ov.items():
        for reason in reasons:
            drop(i, f"overlap: {reason}")

    template = INSTRUCTIONS.read_text().strip()
    kept = [r for r in rows if r["_i"] not in drops]
    by_kind = collections.defaultdict(list)
    for r in kept:
        kind = judged[r["_i"]]["kind"] if r["_i"] in judged else per[r["_i"]]["kind_auto"]
        by_kind[kind].append(r)
    rng = random.Random(SPLIT_SEED)
    train, hold, index = [], [], []
    for kind in sorted(by_kind):
        group = by_kind[kind][:]
        rng.shuffle(group)
        n_hold = round(len(group) * HOLDOUT_SHARE)
        for k, r in enumerate(group):
            split = "holdout" if k < n_hold else "train"
            name = per[r["_i"]]["principal"]
            prompt = template.replace("{PRINCIPAL}", name) + "\n\n" + r["enhanced_prompt"].strip()
            row = {"prompt": prompt, "completion": r["enhanced_completion"].strip()}
            (hold if split == "holdout" else train).append(row)
            index.append({"raw_row": r["_i"], "split": split, "kind": kind,
                          "kind_source": "judge" if r["_i"] in judged else "heuristic", "principal": name})
    rng.shuffle(train)
    rng.shuffle(hold)
    out = lambda path, rs: path.write_text("".join(json.dumps(x, ensure_ascii=False) + "\n" for x in rs))
    out(DATA / "steward_sft_train.jsonl", train)
    out(DATA / "steward_sft_holdout.jsonl", hold)
    out(DATA / "steward_sft_split_index.jsonl", sorted(index, key=lambda x: x["raw_row"]))
    out(DATA / "steward_sft_drops.jsonl", [{"raw_row": i, "reasons": rs} for i, rs in sorted(drops.items())])
    import hashlib
    sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
    jk = collections.Counter(j["kind"] for j in judged.values())
    jn = sum(jk.values())
    report = {
        "auto": auto["report"],
        "judge_sample": {"n_judged": jn, "kinds": dict(jk),
                         "opening_share": jk["opening_brief"] / jn if jn else None,
                         "stay_quiet_share_of_non_opening": (jk["stay_quiet"] / (jn - jk["opening_brief"])
                                                             if jn - jk["opening_brief"] else None),
                         "flag_counts": dict(collections.Counter(f for j in judged.values()
                                                                 for f, on in j["flags"].items() if on))},
        "overlap_rows": len(ov), "overlap_reasons": dict(collections.Counter(
            re.sub(r" with .*| '.*'", "", x) for rs in ov.values() for x in rs)),
        "drops": {"rows": len(drops), "by_reason": dict(collections.Counter(
            re.sub(r"[:(].*", "", x).strip() for rs in drops.values() for x in rs))},
        "kept": len(kept), "split_seed": SPLIT_SEED, "holdout_share": HOLDOUT_SHARE,
        "train": {"rows": len(train), "sha256": sha(DATA / "steward_sft_train.jsonl"),
                  "kinds": dict(collections.Counter(x["kind"] for x in index if x["split"] == "train"))},
        "holdout": {"rows": len(hold), "sha256": sha(DATA / "steward_sft_holdout.jsonl"),
                    "kinds": dict(collections.Counter(x["kind"] for x in index if x["split"] == "holdout"))},
        "instructions_sha256": sha(INSTRUCTIONS),
    }
    (DATA / "steward_sft_qa_report.json").write_text(json.dumps(report, indent=1))
    print(json.dumps({k: report[k] for k in ("overlap_rows", "drops", "kept", "train", "holdout")}, indent=1))
    return 0


if __name__ == "__main__":
    stage = sys.argv[1] if len(sys.argv) > 1 else ""
    sys.exit({"auto": stage_auto, "judge": stage_judge, "build": stage_build}.get(stage, lambda: print(__doc__) or 2)())
