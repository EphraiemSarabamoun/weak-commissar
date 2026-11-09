"""Merge the first Invent set with the targeted top-up, check, dedupe, rebalance and split (no Adaption calls).

Inputs:  data/steward_sft_raw.jsonl (first set, 1,200 rows) and its judge sample
         data/steward_sft_qa_judge.jsonl; data/steward_sft_topup_raw.jsonl (top-up rows)
Outputs: data/steward_sft_v2_train.jsonl, data/steward_sft_v2_holdout.jsonl (prompt/completion only),
         data/steward_sft_v2_drops.jsonl (every row not used, with reasons),
         data/steward_sft_v2_index.jsonl (every row used: source, split, kind),
         data/steward_sft_v2_report.json

Every row goes through steward_data_qa.row_checks, exact and near deduplication across both sets, and
overlap removal (StewardBench v1/v2, operae). Kinds come from the judge where a row was sampled and the
heuristic otherwise. Rebalancing then keeps every stay-quiet row, trims interventions so stay-quiet is
about a quarter of non-openings (an equal-share cap across intervention kinds, so the abundant ones
are trimmed and the scarce ones kept whole), and trims
openings to about a third of the total. All random choices use SPLIT_SEED.

Usage: python3 tools/qa/steward_merge.py [--topup data/steward_sft_topup_raw.jsonl]
       python3 tools/qa/steward_merge.py --judge     (after the build: judge 150 train rows)
"""

from __future__ import annotations

import argparse
import collections
import hashlib
import json
import math
import random
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import steward_data_qa as qa  # noqa: E402

DATA = qa.DATA
TOPUP = DATA / "steward_sft_topup_raw.jsonl"
OUT_TRAIN, OUT_HOLD = DATA / "steward_sft_v2_train.jsonl", DATA / "steward_sft_v2_holdout.jsonl"
OUT_DROPS, OUT_INDEX, OUT_REPORT = (DATA / "steward_sft_v2_drops.jsonl", DATA / "steward_sft_v2_index.jsonl",
                                    DATA / "steward_sft_v2_report.json")
QUIET_SHARE_OF_NON_OPENING = 0.25   # the generation prompt's target
OPENING_SHARE = 1 / 3               # the generation prompt's target
KIND_STRATA_MARGIN = range(8)       # one spare row per stratum absorbs per-kind rounding of the holdout
MIN_TRAIN_ROWS = 1000               # Adaption SFT minimum with augmentation off (manager, 2026-11-08 18:58)


def load_all(topup: Path) -> list[dict]:
    """Both sources as one list; each row gets a stable uid like base-17 or topup-3."""
    rows = []
    for source, path in (("base", qa.RAW), ("topup", topup)):
        if not path.exists():
            continue
        for r in qa.load_rows(path):
            r["_source"], r["_uid"] = source, f"{source}-{r['_i']}"
            rows.append(r)
    for n, r in enumerate(rows):
        r["_i"] = n   # global index, so qa's overlap and near-duplicate helpers work across both sets
    return rows


def apply_salvage(rows: list[dict], path: Path) -> set:
    """Replace the completion of each top-up row labelled stay_quiet with high confidence by exactly
    'No objection.'; the label is the judge model's, the text is fixed. Returns the salvaged uids."""
    quiet = {x["uid"] for x in map(json.loads, open(path)) if x["kind"] == "stay_quiet" and x["confidence"] == "high"}
    done = set()
    for r in rows:
        if r["_uid"] in quiet:
            r["enhanced_completion"], r["_salvaged"] = "No objection.", True
            done.add(r["_uid"])
    return done


def base_judgments() -> dict:
    out = {}
    if qa.JUDGE.exists():
        for j in map(json.loads, open(qa.JUDGE)):
            if j.get("ok"):
                out[f"base-{int(j['key'].split('-')[1])}"] = j
    return out


def equal_share_cap(sizes: dict, target: int) -> int:
    """Largest per-kind cap c with sum(min(size, c)) <= target: scarce kinds stay whole, abundant
    kinds are trimmed to the same size, so no intervention kind is wiped out."""
    lo, hi = 0, max(sizes.values(), default=0)
    while lo < hi:
        mid = (lo + hi + 1) // 2
        if sum(min(n, mid) for n in sizes.values()) <= target:
            lo = mid
        else:
            hi = mid - 1
    return lo


def rebalance(kept: list[dict], kind_of, rng, min_total: int = 0) -> tuple[list[dict], dict]:
    """Return (rows to use, {uid: reason} for rows trimmed by rebalancing)."""
    by = collections.defaultdict(list)
    for r in kept:
        by[kind_of(r)].append(r)
    for g in by.values():
        rng.shuffle(g)
    trimmed = {}
    quiet = by.get("stay_quiet", [])
    interventions = [r for k, g in by.items() if k not in ("opening_brief", "stay_quiet") for r in g]
    target_i = round(len(quiet) * (1 - QUIET_SHARE_OF_NON_OPENING) / QUIET_SHARE_OF_NON_OPENING)
    if len(interventions) < target_i:   # too few interventions: trim stay-quiet instead
        keep_q = round(len(interventions) * QUIET_SHARE_OF_NON_OPENING / (1 - QUIET_SHARE_OF_NON_OPENING))
        for r in quiet[keep_q:]:
            trimmed[r["_uid"]] = "rebalance: stay-quiet above a quarter of non-openings"
        quiet = quiet[:keep_q]
    else:
        cap = equal_share_cap({k: len(g) for k, g in by.items() if k not in ("opening_brief", "stay_quiet")}, target_i)
        for k, g in list(by.items()):
            if k in ("opening_brief", "stay_quiet") or len(g) <= cap:
                continue
            for r in g[cap:]:
                trimmed[r["_uid"]] = f"rebalance: {k} capped at {cap} so stay-quiet is a quarter of non-openings"
            by[k] = g[:cap]
        interventions = [r for k, g in by.items() if k not in ("opening_brief", "stay_quiet") for r in g]
    non_opening = len(quiet) + len(interventions)
    target_o = round(non_opening * OPENING_SHARE / (1 - OPENING_SHARE))
    openings = by.get("opening_brief", [])
    for r in openings[target_o:]:
        trimmed[r["_uid"]] = "rebalance: openings trimmed to a third of the set"
    used = openings[:target_o] + quiet + interventions
    return top_up_to_minimum(used, kept, trimmed, kind_of, min_total)


def top_up_to_minimum(used, kept, trimmed, kind_of, min_total):
    """If the targeted mix is smaller than min_total, put trimmed rows back, interventions first
    (in their shuffled order), then openings, and relabel their reason so the relaxation is visible."""
    by_uid = {r["_uid"]: r for r in kept}
    back_i = [u for u in trimmed if kind_of(by_uid[u]) not in ("opening_brief", "stay_quiet")]
    back_o = [u for u in trimmed if kind_of(by_uid[u]) == "opening_brief"]
    for u in back_i + back_o:
        if len(used) >= min_total:
            break
        used.append(by_uid[u])
        del trimmed[u]
    return used, trimmed


OUT_JUDGE = DATA / "steward_sft_v2_judge.jsonl"


def judge_train_sample(n: int = qa.JUDGE_SAMPLE) -> int:
    """The pinned StewardBench v2 judge on a seeded sample of the final train rows (situation as
    generated, without the instructions prefix, as in the first set's sample)."""
    import stewardbench_v2
    train = [x for x in map(json.loads, open(OUT_INDEX)) if x["split"] == "train"]
    sample = random.Random(qa.SPLIT_SEED).sample(train, min(n, len(train)))
    verdicts = stewardbench_v2.judge_many([(x["uid"], x["raw_prompt"], x["completion"]) for x in sample], OUT_JUDGE)
    got = [v for v in verdicts.values() if v.get("ok")]
    kinds = collections.Counter(v["kind"] for v in got)
    agree = sum(v["kind"] == x["kind"] for x in sample for v in [verdicts[x["uid"]]] if v.get("ok"))
    summary = {"sample": len(sample), "judged": len(got), "kinds": dict(kinds),
               "opening_share": kinds["opening_brief"] / len(got) if got else None,
               "stay_quiet_share_of_non_opening": (kinds["stay_quiet"] / (len(got) - kinds["opening_brief"])
                                                   if len(got) > kinds["opening_brief"] else None),
               "flag_counts": dict(collections.Counter(f for v in got for f, on in v["flags"].items() if on)),
               "agreement_with_build_kind": agree / len(got) if got else None,
               "calls": sum(v.get("attempts", 0) for v in verdicts.values())}
    report = json.loads(OUT_REPORT.read_text())
    report["judge_sample_final_train"] = summary
    OUT_REPORT.write_text(json.dumps(report, indent=1))
    print(json.dumps(summary, indent=1))
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--topup", type=Path, default=TOPUP)
    ap.add_argument("--judge", action="store_true", help="judge a 150-row sample of the built train set")
    ap.add_argument("--salvage", type=Path, default=None,
                    help="salvage labels (tools/qa/salvage_quiet.py): high-confidence stay_quiet rows become 'No objection.'")
    args = ap.parse_args()
    if args.judge:
        return judge_train_sample()
    rows = load_all(args.topup)
    salvaged = apply_salvage(rows, args.salvage) if args.salvage else set()
    judged = base_judgments()
    drops = collections.defaultdict(list)
    norm = lambda t: re.sub(r"\s+", " ", t.lower()).strip()
    checks, seen = {}, {}
    for r in rows:
        x = qa.row_checks(r)
        checks[r["_uid"]] = x
        for issue in x["issues"]:
            drops[r["_uid"]].append(f"structure: {issue}")
        for k, m in x["keyword_hits"].items():
            drops[r["_uid"]].append(f"keyword {k}: {m!r}")
        key = norm(r["enhanced_prompt"]) + "\x00" + norm(r["enhanced_completion"])
        if key in seen:
            drops[r["_uid"]].append(f"exact duplicate of {seen[key]}")
        seen.setdefault(key, r["_uid"])
    for i, j, jac in qa.near_duplicates(rows):
        a, b = rows[i]["_uid"], rows[j]["_uid"]
        if a not in drops:
            drops[b].append(f"near duplicate of {a} (Jaccard {jac})")
    for uid, j in judged.items():
        for f in qa.JUDGE_DROP_FLAGS:
            if j["flags"].get(f):
                drops[uid].append(f"judge flag {f}")
    for i, reasons in qa.overlap_hits(rows).items():
        drops[rows[i]["_uid"]] += [f"overlap: {x}" for x in reasons]

    kind_of = lambda r: judged[r["_uid"]]["kind"] if r["_uid"] in judged else checks[r["_uid"]]["kind_auto"]
    kept = [r for r in rows if r["_uid"] not in drops]
    rng = random.Random(qa.SPLIT_SEED)
    min_total = math.ceil(MIN_TRAIN_ROWS / (1 - qa.HOLDOUT_SHARE)) + len(KIND_STRATA_MARGIN)
    used, trimmed = rebalance(kept, kind_of, rng, min_total)
    template = qa.INSTRUCTIONS.read_text().strip()
    by_kind = collections.defaultdict(list)
    for r in used:
        by_kind[kind_of(r)].append(r)
    train, hold, index = [], [], []
    for kind in sorted(by_kind):
        g = by_kind[kind]
        rng.shuffle(g)
        n_hold = round(len(g) * qa.HOLDOUT_SHARE)
        for k, r in enumerate(g):
            split = "holdout" if k < n_hold else "train"
            name = checks[r["_uid"]]["principal"]
            row = {"prompt": template.replace("{PRINCIPAL}", name) + "\n\n" + r["enhanced_prompt"].strip(),
                   "completion": r["enhanced_completion"].strip()}
            (hold if split == "holdout" else train).append(row)
            index.append({"uid": r["_uid"], "source": r["_source"], "split": split, "kind": kind,
                          "salvaged": bool(r.get("_salvaged")),
                          "kind_source": "judge" if r["_uid"] in judged else "heuristic", "principal": name,
                          "raw_prompt": r["enhanced_prompt"], "completion": r["enhanced_completion"]})
    rng.shuffle(train)
    rng.shuffle(hold)
    write = lambda p, rs: p.write_text("".join(json.dumps(x, ensure_ascii=False) + "\n" for x in rs))
    write(OUT_TRAIN, train)
    write(OUT_HOLD, hold)
    write(OUT_INDEX, sorted(index, key=lambda x: x["uid"]))
    write(OUT_DROPS, [{"uid": u, "reasons": rs} for u, rs in sorted(drops.items())]
          + [{"uid": u, "reasons": [rs]} for u, rs in sorted(trimmed.items())])
    sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
    mix = collections.Counter(x["kind"] for x in index)
    n = len(index)
    non_open = n - mix["opening_brief"]
    report = {
        "sources": dict(collections.Counter(r["_source"] for r in rows)),
        "dropped_for_quality_or_overlap": {"rows": len(drops), "by_source": dict(collections.Counter(u.split("-")[0] for u in drops)),
                                           "by_reason": dict(collections.Counter(re.sub(r"[:(].*", "", x).strip()
                                                                                 for rs in drops.values() for x in rs))},
        "salvaged_stay_quiet": {"rows": len(salvaged), "used": sum(1 for x in index if x["salvaged"])},
        "trimmed_by_rebalance": {"rows": len(trimmed), "by_reason": dict(collections.Counter(trimmed.values()))},
        "final": {"rows": n, "by_source": dict(collections.Counter(x["source"] for x in index)), "kinds": dict(mix),
                  "opening_share": mix["opening_brief"] / n if n else None,
                  "stay_quiet_share_of_non_opening": mix["stay_quiet"] / non_open if non_open else None,
                  "kind_note": "judge kind for the 150 judged first-set rows, heuristic kind for the rest"},
        "train": {"rows": len(train), "sha256": sha(OUT_TRAIN),
                  "kinds": dict(collections.Counter(x["kind"] for x in index if x["split"] == "train"))},
        "holdout": {"rows": len(hold), "sha256": sha(OUT_HOLD),
                    "kinds": dict(collections.Counter(x["kind"] for x in index if x["split"] == "holdout"))},
        "min_train_rows": MIN_TRAIN_ROWS, "min_total_rows": min_total,
        "targets_relaxed": len(used) > 0 and len(used) <= min_total and bool(trimmed),
        "split_seed": qa.SPLIT_SEED, "holdout_share": qa.HOLDOUT_SHARE, "instructions_sha256": sha(qa.INSTRUCTIONS),
    }
    OUT_REPORT.write_text(json.dumps(report, indent=1))
    print(json.dumps(report, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
