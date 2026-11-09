"""Round-2 quick gates side by side: the new adapter (a label), round 1's v4 (steward-lora) and steward-base.

No model or judge calls; reads what the gates wrote:
  bench/r5_cells/<model>/summary.json                       six R5 cells: identity, added guidance
  bench/rewrite_eval/<model>_system_<holdout tag>/          the holdout's rewrite rows (v4 and base unjudged)
  bench/rewrite_eval/steward-{lora,base}_system/            round 1's judged runs on the 21 v4 rows
  bench/v2/results_v2_2/<model>/                            StewardBench v2 items under the v2.2 prompt
and writes bench/gates_<label>.md and .json. The judge comparison across all three models uses the 21 rewrite
rows the v4 and v5 holdouts share (same uids), where v4 and base were judged in round 1. StewardBench paired
tests reuse compare_post_train (exact McNemar per kind, paired bootstrap on the macro difference).

Usage: python3 tools/qa/compare_round2.py --label steward-lora-v5 [--holdout data/steward_sft_v5_holdout.jsonl]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import compare_post_train as cpt  # noqa: E402  (item_rows, paired_bench, flips, pct)

REPO = cpt.REPO
V4, BASE = "steward-lora", "steward-base"


def load(path: Path):
    return json.loads(path.read_text()) if path.exists() else None


def outputs(path: Path) -> dict:
    return {r["uid"]: r for r in map(json.loads, open(path))} if path.exists() else {}


def frac(n, d) -> str:
    return "n/a" if n is None or d is None else f"{n}/{d}"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--label", required=True)
    ap.add_argument("--holdout", default="data/steward_sft_v5_holdout.jsonl")
    args = ap.parse_args()
    models = (args.label, V4, BASE)
    tag = "_" + Path(args.holdout).stem.replace("steward_sft_", "")
    r5 = {m: load(REPO / "bench" / "r5_cells" / m / "summary.json") for m in models}
    rw = {m: load(REPO / "bench" / "rewrite_eval" / f"{m}_system{tag}" / "summary.json") for m in models}
    sb = {m: load(REPO / "bench" / "v2" / "results_v2_2" / m / "scores.json") for m in models}
    head = f"| gate | {args.label} | v4 (steward-lora) | steward-base |"
    lines = [f"# Round-2 quick gates: {args.label} vs v4 vs base", "", "All replies at temperature 0 under the v2.2 "
             "system prompt.", "", "## Six R5 cells (R5ft2 launch rule: identical at most 1, guidance added at least 3)",
             "", head, "|-|-|-|-|"]
    for key in ("identical", "guidance_added"):
        lines.append(f"| {key.replace('_', ' ')} | " + " | ".join(frac((r5[m] or {}).get(key), (r5[m] or {}).get("cells"))
                                                             for m in models) + " |")
    lines.append("| launch rule met | " + " | ".join("n/a" if not r5[m] else str(r5[m]["r5ft2_launch_rule_met"])
                                                     for m in models) + " |")
    holdout = REPO / args.holdout
    holdout_sha = __import__("hashlib").sha256(holdout.read_bytes()).hexdigest() if holdout.exists() else None
    lines += ["", f"## Holdout rewrite rows ({Path(args.holdout).name}, sha256 {holdout_sha})", "", head, "|-|-|-|-|"]
    for label, key in (("two-header format (W1)", "w1_format_ok"), ("identical to the original", "identical"),
                       ("priority guidance added", "guidance_added"), ("passes every rule", "passes_all_rules")):
        lines.append(f"| {label} | " + " | ".join(frac((rw[m] or {}).get(key), (rw[m] or {}).get("rows"))
                                                for m in models) + " |")
    for src in ("v4_rows", "v5_rows"):
        for key in ("identical", "guidance_added"):
            lines.append(f"| {key.replace('_', ' ')}, {src.replace('_', ' ')} | " + " | ".join(
                frac(((rw[m] or {}).get(f"{key}_by_source") or {}).get(src), ((rw[m] or {}).get("rows_by_source") or {}).get(src))
                for m in models) + " |")
    j = (rw[args.label] or {}).get("judge") or {}
    for key in ("acceptable", "request_changed", "added_obligation", "facts_kept", "colleague_errand_as_own"):
        lines.append(f"| judge: {key.replace('_', ' ')} | {frac(j.get(key), j.get('judged'))} | not judged | not judged |")
    # judge on the 21 shared v4 rows: the new adapter vs round 1's judged v4 and base runs
    new = outputs(REPO / "bench" / "rewrite_eval" / f"{args.label}_system{tag}" / "outputs.jsonl")
    old = {m: outputs(REPO / "bench" / "rewrite_eval" / f"{m}_system" / "outputs.jsonl") for m in (V4, BASE)}
    shared = sorted(u for u in new if u in old[V4] and u in old[BASE] and (new[u].get("judge") or {}).get("ok"))
    ok = lambda r: bool((r.get("judge") or {}).get("acceptable"))
    paired = {}
    if shared:
        lines += ["", f"## Judge on the {len(shared)} rewrite rows shared with round 1 (v4 and base judged then)", "",
                  head, "|-|-|-|-|", "| judge acceptable | " + " | ".join(
                      f"{sum(ok(src[u]) for u in shared)}/{len(shared)}" for src in (new, old[V4], old[BASE])) + " |"]
        paired = {m: cpt.flips([(ok(old[m][u]), ok(new[u])) for u in shared]) for m in (V4, BASE)}
        lines += [f"Fixed/broken vs {m}: {v['fixed']}/{v['broken']} (exact McNemar p {v['exact_mcnemar_p']})"
                  for m, v in paired.items()]
        # a shared row the new adapter left unjudged (its reply failed to parse) counts as not acceptable here
        both = sorted(u for u in new if u in old[V4] and u in old[BASE])
        if len(both) > len(shared):
            lines.append(f"Counting the {len(both) - len(shared)} unjudged row(s) "
                         f"({', '.join(u for u in both if u not in shared)}) as not acceptable, over all {len(both)}: "
                         + ", ".join(f"{name} {sum(ok(src[u]) for u in both)}/{len(both)}" for name, src in
                                     ((args.label, new), (V4, old[V4]), (BASE, old[BASE]))) + ".")
        paired = {f"{args.label}_vs_{m}": v for m, v in paired.items()}
    lines += ["", "## StewardBench v2 items under v2.2 (150 items)", "", head, "|-|-|-|-|"]
    get = lambda s, *ks: None if s is None else __import__("functools").reduce(lambda a, k: (a or {}).get(k), ks, s)
    for label, key, ci in (("macro accuracy (primary)", ("macro_accuracy", "value"), ("macro_accuracy", "ci95")),
                           ("forged-approval endorsement", ("forged_approval_endorsement_rate", "value"), None),
                           ("false alarm on stay-quiet", ("false_alarm_rate_stay_quiet", "value"), None),
                           ("false redirect on one-attempt controls", ("false_redirect_rate_quiet_controls", "value"), None)):
        lines.append(f"| {label} | " + " | ".join(cpt.pct(get(sb[m], *key)) + (cpt.ci(get(sb[m], *ci)) if ci else "")
                                               for m in models) + " |")
    for k in cpt.KINDS:
        lines.append(f"| accuracy: {k} | " + " | ".join(cpt.pct(get(sb[m], "per_kind_accuracy", k)) for m in models) + " |")
    rows = {m: cpt.item_rows(m) for m in models}
    bench_paired = {}
    for m in (V4, BASE):
        if rows[args.label] and rows[m]:
            p = cpt.paired_bench(rows[m], rows[args.label])
            bench_paired[f"{args.label}_vs_{m}"] = p
            d = p["macro_diff"]
            lines.append(f"\nMacro difference {args.label} minus {m}: {100 * d['value']:+.1f} points (paired bootstrap "
                         f"95% CI {100 * d['ci95'][0]:+.1f} to {100 * d['ci95'][1]:+.1f}); fixed/broken overall "
                         f"{p['all']['fixed']}/{p['all']['broken']} (p {p['all']['exact_mcnemar_p']}).")
    md = "\n".join(lines) + "\n"
    (REPO / "bench" / f"gates_{args.label}.md").write_text(md)
    (REPO / "bench" / f"gates_{args.label}.json").write_text(json.dumps(
        {"holdout": args.holdout, "holdout_sha256": holdout_sha,
         "r5_cells": r5, "rewrites": rw, "stewardbench": sb, "judge_shared_rows": paired,
         "stewardbench_paired": bench_paired}, indent=1, default=str))
    print(md)
    return 0


if __name__ == "__main__":
    sys.exit(main())
