"""Base vs fine-tune: StewardBench v2.2 and rewrite fidelity side by side (no model or judge calls).

Reads bench/v2/results_v2_2/<model>/scores.json and bench/rewrite_eval/<model>_<placement>/summary.json for
steward-base and steward-lora, and writes bench/post_train_comparison.md and .json. Missing results print n/a.
When both models have per-item results it adds paired tests: items fixed and broken by the fine-tune with an
exact McNemar p (per StewardBench kind and overall, and per rewrite row), and a paired bootstrap 95% interval on
the macro-accuracy difference that resamples items within each kind, as the single-model interval does.

Usage: python3 tools/qa/compare_post_train.py
"""

from __future__ import annotations

import json
import random
import sys
from math import comb
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(REPO / "bench"), str(REPO / "bench" / "v2")]
import metrics_v2  # noqa: E402  (v2 correctness rule and macro accuracy, reused unchanged)
import spec_v2  # noqa: E402
MODELS = ("steward-base", "steward-lora")
KINDS = ("opening_brief", "redirect_effort", "decline_shortcut", "question_approval", "back_problem", "stay_quiet")


def load(path: Path):
    return json.loads(path.read_text()) if path.exists() else None


def pct(v):
    return "n/a" if v is None else f"{100 * v:.1f}%"


def ci(c):
    return "" if not c else f" [{100 * c[0]:.1f}, {100 * c[1]:.1f}]"


def item_rows(model: str):
    """Per-item StewardBench rows (metrics_v2's correctness rule) for a scored model, or None."""
    path = REPO / "bench" / "v2" / "results_v2_2" / model / "judgments.jsonl"
    if not path.exists():
        return None
    verdicts = {r["key"]: r for r in spec_v2.common.read_jsonl(path) if r.get("ok")}
    return metrics_v2._rows(spec_v2.common.read_jsonl(spec_v2.ITEMS_FILE), verdicts)


def exact_mcnemar(fixed: int, broken: int) -> float:
    """Two-sided exact McNemar p: a binomial test of the discordant pairs at one half."""
    n = fixed + broken
    return 1.0 if n == 0 else min(1.0, 2 * sum(comb(n, i) for i in range(min(fixed, broken) + 1)) / 2 ** n)


def flips(pairs) -> dict:
    """pairs of (base_ok, lora_ok) booleans -> items fixed and broken by the fine-tune, with the exact p."""
    fixed = sum(1 for b, l in pairs if not b and l)
    broken = sum(1 for b, l in pairs if b and not l)
    return {"fixed": fixed, "broken": broken, "exact_mcnemar_p": float(f"{exact_mcnemar(fixed, broken):.3g}")}


def paired_bench(base: list[dict], lora: list[dict]) -> dict:
    """Flips per kind and overall, and a paired bootstrap interval on the macro difference (lora minus base)."""
    lora_by_id = {r["item_id"]: r for r in lora}
    pairs = [(b, lora_by_id[b["item_id"]]) for b in base]
    out = {k: flips([(b["correct"], l["correct"]) for b, l in pairs if k == "all" or b["gold"] == k])
           for k in (*spec_v2.KINDS, "all")}
    rng = random.Random(spec_v2.common.BOOTSTRAP_SEED)
    by_kind = [g for g in ([p for p in pairs if p[0]["gold"] == k] for k in spec_v2.KINDS) if g]
    draws = spec_v2.common.BOOTSTRAP_DRAWS
    diffs = sorted(metrics_v2._macro([l for _, l in s]) - metrics_v2._macro([b for b, _ in s])
                   for s in ([g[rng.randrange(len(g))] for g in by_kind for _ in range(len(g))] for _ in range(draws)))
    out["macro_diff"] = {"value": round(metrics_v2._macro(lora) - metrics_v2._macro(base), 4),
                         "ci95": [round(diffs[int(0.025 * draws)], 4), round(diffs[int(0.975 * draws) - 1], 4)]}
    return out


def paired_rewrites(placement: str):
    """Per-row flips on passing every rule and, where both runs were judged, on judge-acceptable."""
    rows = {}
    for m in MODELS:
        path = REPO / "bench" / "rewrite_eval" / f"{m}_{placement}" / "outputs.jsonl"
        if not path.exists():
            return None
        rows[m] = {r["uid"]: r for r in map(json.loads, open(path))}
    base, lora = rows["steward-base"], rows["steward-lora"]
    uids = sorted(set(base) & set(lora))
    out = {"rows": len(uids), "passes_all_rules": flips([(base[u]["passes_rules"], lora[u]["passes_rules"]) for u in uids])}
    judged = [u for u in uids if (base[u]["judge"] or {}).get("ok") and (lora[u]["judge"] or {}).get("ok")]
    if judged:
        out["judge_acceptable"] = flips([(bool(base[u]["judge"].get("acceptable")), bool(lora[u]["judge"].get("acceptable")))
                                         for u in judged])
        out["judge_acceptable"]["rows"] = len(judged)
    return out


def paired_lines(bench, rewrites) -> list[str]:
    """Markdown for the paired section; empty when the fine-tune has no per-item results yet."""
    if not bench and not any(rewrites.values()):
        return []
    lines = ["", "## Paired: what the fine-tune fixed and broke (exact McNemar p)", "",
             "| scope | fixed | broken | p |", "|-|-|-|-|"]
    for k, v in (bench or {}).items():
        if k != "macro_diff":
            lines.append(f"| StewardBench {k} | {v['fixed']} | {v['broken']} | {v['exact_mcnemar_p']} |")
    for p, v in rewrites.items():
        for key in ("passes_all_rules", "judge_acceptable"):
            if v and key in v:
                lines.append(f"| rewrite {p}: {key.replace('_', ' ')} | {v[key]['fixed']} | {v[key]['broken']} | "
                             f"{v[key]['exact_mcnemar_p']} |")
    if bench:
        d = bench["macro_diff"]
        lines += ["", f"Macro accuracy difference, lora minus base: {100 * d['value']:+.1f} points "
                      f"(paired bootstrap 95% CI {100 * d['ci95'][0]:+.1f} to {100 * d['ci95'][1]:+.1f})."]
    return lines


def main() -> int:
    sb = {m: load(REPO / "bench" / "v2" / "results_v2_2" / m / "scores.json") for m in MODELS}
    rw = {(m, p): load(REPO / "bench" / "rewrite_eval" / f"{m}_{p}" / "summary.json")
          for m in MODELS for p in ("system", "user")}
    get = lambda s, *ks: (None if s is None else
                          (lambda v: v)(__import__("functools").reduce(lambda a, k: (a or {}).get(k), ks, s)))
    lines = ["# steward-base vs steward-lora (v4)", "", "## StewardBench v2.2 (150 items, v2.2 system prompt)", "",
             "| metric | steward-base | steward-lora |", "|-|-|-|"]
    rows = [("macro accuracy (primary)", ("macro_accuracy", "value"), ("macro_accuracy", "ci95")),
            ("micro accuracy", ("micro_accuracy", "value"), ("micro_accuracy", "ci95")),
            ("forged-approval endorsement", ("forged_approval_endorsement_rate", "value"), None),
            ("false alarm on stay-quiet", ("false_alarm_rate_stay_quiet", "value"), None),
            ("false redirect on one-attempt controls", ("false_redirect_rate_quiet_controls", "value"), None)]
    for label, key, cikey in rows:
        cells = [pct(get(sb[m], *key)) + (ci(get(sb[m], *cikey)) if cikey else "") for m in MODELS]
        lines.append(f"| {label} | " + " | ".join(cells) + " |")
    for k in KINDS:
        lines.append(f"| accuracy: {k} | " + " | ".join(pct(get(sb[m], "per_kind_accuracy", k)) for m in MODELS) + " |")
    for f in ("invents_instruction", "claims_authority", "asks_for_less"):
        lines.append(f"| flag rate: {f} | " + " | ".join(pct(get(sb[m], "flag_rates", f)) for m in MODELS) + " |")
    lines += ["", "## Rewrite fidelity (v4 holdout rewrite rows, temperature 0)", "",
              "| placement / metric | steward-base | steward-lora |", "|-|-|-|"]
    for p in ("system", "user"):
        for label, key in (("two-header format (W1)", ("w1_format_ok",)), ("passes every rule", ("passes_all_rules",)),
                           ("judge: acceptable", ("judge", "acceptable")), ("judge: request changed", ("judge", "request_changed")),
                           ("judge: added obligation", ("judge", "added_obligation"))):
            cells = []
            for m in MODELS:
                s = rw[(m, p)]
                v = get(s, *key)
                cells.append("n/a" if v is None else f"{v}/{(s['judge'] or {}).get('judged') if key[0] == 'judge' else s['rows']}")
            lines.append(f"| {p}: {label} | " + " | ".join(cells) + " |")
    base_rows, lora_rows = item_rows("steward-base"), item_rows("steward-lora")
    bench_paired = paired_bench(base_rows, lora_rows) if base_rows and lora_rows else None
    rewrite_paired = {p: paired_rewrites(p) for p in ("system", "user")}
    lines += paired_lines(bench_paired, rewrite_paired)
    md = "\n".join(lines) + "\n"
    (REPO / "bench" / "post_train_comparison.md").write_text(md)
    (REPO / "bench" / "post_train_comparison.json").write_text(json.dumps(
        {"stewardbench_v2_2": sb, "rewrite_fidelity": {f"{m}_{p}": v for (m, p), v in rw.items()},
         "paired": {"stewardbench_v2_2": bench_paired, "rewrite_fidelity": rewrite_paired}}, indent=1, default=str))
    print(md)
    return 0


if __name__ == "__main__":
    sys.exit(main())
