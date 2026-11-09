"""StewardBench v2 (principal-first policy): entry point.

Commands, in order:
  build              v1 items + v2 templates -> items_v2.jsonl, manifest_v2.json, validation_v2.jsonl
  pin                hash v2's items, judge rubric, metrics, steward prompt and the v1 modules it uses
  validate-judge     judge the 30 hand-labelled v2 replies; same acceptance rule as v1
  score --model M    steward replies with the v2 system prompt, judged, scored -> v2/results/<M>/
  export-codex       30 random items with gold and judge labels for a decorrelated gold check

Every model is scored with commissar_prompt_v2 (v2/steward_prompt_v2.txt) as the system
prompt, the format the fine-tune trains on. Score the fine-tune when it lands:
  python3 bench/v2/stewardbench_v2.py score --model steward-lora
"""

from __future__ import annotations

import argparse
import collections
import datetime
import json
import random
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import spec_v2  # noqa: E402  (puts bench/ on sys.path for the v1 modules)
import judge_v2  # noqa: E402
import metrics_v2  # noqa: E402
import render  # noqa: E402
import judge as judge_v1  # noqa: E402
from stewardbench import cohen_kappa  # noqa: E402

common = spec_v2.common
V2_FILES = ("items_v2.jsonl", "validation_v2.jsonl", "steward_prompt_v2.txt", "spec_v2.py", "judge_v2.py",
            "metrics_v2.py", "stewardbench_v2.py")
V1_FILES_USED = ("common.py", "render.py", "steward.py", "judge.py", "metrics.py", "stewardbench.py")


def current_pins() -> dict:
    return {"v2_files": {f: common.sha256_file(spec_v2.V2_DIR / f) for f in V2_FILES},
            "v1_files_used": {f: common.sha256_file(spec_v2.BENCH_DIR / f) for f in V1_FILES_USED},
            "judge_template_sha256": common.sha256_text(judge_v2.JUDGE_TEMPLATE), "judge_model": spec_v2.JUDGE_MODEL,
            "primary_metric": spec_v2.PRIMARY, "steward_temperature": spec_v2.STEWARD_TEMPERATURE,
            "steward_max_tokens": spec_v2.STEWARD_MAX_TOKENS}


def cmd_pin(args) -> int:
    pins = {"pinned_at": datetime.datetime.now().astimezone().isoformat(timespec="seconds"), "note": args.note,
            **current_pins(), "judge_provenance": judge_v1.provenance()}
    spec_v2.PINS_FILE.write_text(json.dumps(pins, indent=1))
    print(json.dumps({k: pins[k] for k in ("pinned_at", "judge_model", "judge_template_sha256", "primary_metric")}))
    return 0


def require_pins() -> None:
    if not spec_v2.PINS_FILE.exists():
        sys.exit("no PINS_v2.json: run `stewardbench_v2.py pin` first")
    pinned, now = json.loads(spec_v2.PINS_FILE.read_text()), current_pins()
    drift = [k for k, v in now.items() if pinned.get(k) != v]
    if drift:
        sys.exit(f"pinned v2 inputs changed since {pinned['pinned_at']}: {drift}. Re-pin deliberately and say why.")


def judge_many(tasks, out_path: Path) -> dict:
    """tasks: (key, situation, reply); cached in out_path by key and reply hash."""
    cache = {}
    if out_path.exists():
        cache = {(r["key"], r["reply_sha256"]): r for r in common.read_jsonl(out_path) if r.get("ok")}
    todo = [t for t in tasks if (t[0], common.sha256_text(t[2])) not in cache]
    print(f"judging {len(todo)} replies ({len(tasks) - len(todo)} cached) with {spec_v2.JUDGE_MODEL} (v2 rubric)", flush=True)

    def work(t):
        row = {"key": t[0], "reply_sha256": common.sha256_text(t[2]), **judge_v2.judge_reply(t[1], t[2])}
        common.append_jsonl(out_path, row)
        return row

    with ThreadPoolExecutor(common.JUDGE_CONCURRENCY) as pool:
        for row in pool.map(work, todo):
            cache[(row["key"], row["reply_sha256"])] = row
    return {k: cache.get((k, common.sha256_text(r)), {"ok": False}) for k, _, r in tasks}


def cmd_build(args) -> int:
    import build_v2
    return build_v2.main()


def cmd_validate_judge(args) -> int:
    require_pins()
    items = {it["item_id"]: it for it in common.read_jsonl(spec_v2.ITEMS_FILE)}
    val = common.read_jsonl(spec_v2.VALIDATION_FILE)
    out_dir = spec_v2.RESULTS_DIR / "judge_validation"
    v = judge_many([(r["val_id"], render.situation_text(items[r["item_id"]]), r["reply"]) for r in val],
                   out_dir / "judgments.jsonl")
    hand_k = [r["label"]["kind"] for r in val]
    judge_k = [v[r["val_id"]].get("kind") or "failed" for r in val]
    kind_agree = sum(h == j for h, j in zip(hand_k, judge_k)) / len(val)
    flag_agree = {f: sum(bool((v[r["val_id"]].get("flags") or {}).get(f)) == r["label"]["flags"][f] for r in val) / len(val)
                  for f in spec_v2.FLAGS}
    op = [r for r in val if r["label"]["kind"] == "opening_brief"]
    pf_agree = (sum(bool(v[r["val_id"]].get("principal_first")) == r["label"]["principal_first"] for r in op) / len(op)
                if op else None)
    report = {"n": len(val), "kind_agreement": kind_agree, "cohen_kappa_kind": cohen_kappa(hand_k, judge_k),
              "principal_first_agreement_on_openings": pf_agree, "n_openings": len(op), "flag_agreement": flag_agree,
              "flag_positives_hand": {f: sum(r["label"]["flags"][f] for r in val) for f in spec_v2.FLAGS},
              "kind_counts_hand": dict(collections.Counter(hand_k)),
              "acceptance_rule": {"min_kind_agreement": spec_v2.JUDGE_MIN_KIND_AGREEMENT,
                                  "min_endorse_agreement": spec_v2.JUDGE_MIN_ENDORSE_AGREEMENT},
              "passed": kind_agree >= spec_v2.JUDGE_MIN_KIND_AGREEMENT
              and flag_agree["endorses_unverified_approval"] >= spec_v2.JUDGE_MIN_ENDORSE_AGREEMENT,
              "disagreements": [{"val_id": r["val_id"], "hand": r["label"],
                                 "judge": {k: v[r["val_id"]].get(k) for k in ("kind", "principal_first", "flags", "reason", "error")}}
                                for r in val if r["label"]["kind"] != (v[r["val_id"]].get("kind") or "failed")
                                or (r["label"]["kind"] == "opening_brief"
                                    and bool(v[r["val_id"]].get("principal_first")) != r["label"]["principal_first"])
                                or any(bool((v[r["val_id"]].get("flags") or {}).get(f)) != r["label"]["flags"][f]
                                       for f in spec_v2.FLAGS)],
              "judge_calls": sum(x.get("attempts", 0) for x in v.values())}
    (out_dir / "agreement.json").write_text(json.dumps(report, indent=1))
    print(json.dumps({k: report[k] for k in ("n", "kind_agreement", "cohen_kappa_kind",
                                              "principal_first_agreement_on_openings", "flag_agreement", "passed",
                                              "judge_calls")}, indent=1))
    return 0


def cmd_score(args) -> int:
    require_pins()
    import steward
    items = common.read_jsonl(spec_v2.ITEMS_FILE)
    template = spec_v2.STEWARD_PROMPT_FILE.read_text().strip()
    out_dir = spec_v2.RESULTS_DIR / args.model
    path = out_dir / "replies.jsonl"
    done = {r["item_id"]: r for r in common.read_jsonl(path)} if path.exists() else {}
    for it in items:
        if it["item_id"] not in done:
            done[it["item_id"]] = steward.ask(it, args.model, args.url, template)
            common.append_jsonl(path, done[it["item_id"]])
    replies = [done[it["item_id"]] for it in items]
    by_id = {it["item_id"]: it for it in items}
    verdicts = judge_many([(r["item_id"], render.situation_text(by_id[r["item_id"]]), r["reply"]) for r in replies],
                          out_dir / "judgments.jsonl")
    s = metrics_v2.score(items, verdicts)
    s.update(model=args.model, judge_calls_this_run=sum(x.get("attempts", 0) for x in verdicts.values()),
             pins_file_sha256=common.sha256_file(spec_v2.PINS_FILE),
             scored_at=datetime.datetime.now().astimezone().isoformat(timespec="seconds"),
             system_prompt="v2/steward_prompt_v2.txt (commissar_prompt_v2)")
    (out_dir / "scores.json").write_text(json.dumps(s, indent=1))
    table = metrics_v2.table_markdown(args.model, s)
    (out_dir / "table.md").write_text(table + "\n")
    print(table)
    return 0


def cmd_export_codex(args) -> int:
    """30 random items (fixed seed) with the situation, gold kind and reply, and the judge's
    label of the scored model's reply, for a Codex check of the gold labels."""
    items = common.read_jsonl(spec_v2.ITEMS_FILE)
    res = spec_v2.RESULTS_DIR / args.model
    replies = {r["item_id"]: r for r in common.read_jsonl(res / "replies.jsonl")}
    verdicts = {r["key"]: r for r in common.read_jsonl(res / "judgments.jsonl") if r.get("ok")}
    pick = random.Random(spec_v2.CODEX_SAMPLE_SEED).sample(items, spec_v2.CODEX_SAMPLE_SIZE)
    rows = [{"item_id": it["item_id"], "origin": it["origin"], "situation": render.situation_text(it),
             "gold_kind": it["kind_gold"], "gold_reply": it["gold_reply"],
             "others_requests": it.get("others_requests"), f"{args.model}_reply": replies[it["item_id"]]["reply"],
             "judge_label_of_reply": {k: verdicts.get(it["item_id"], {}).get(k)
                                      for k in ("kind", "principal_first", "flags", "reason")}} for it in pick]
    out = Path(args.out)
    common.write_jsonl(out, rows)
    print(json.dumps({"written": str(out), "n": len(rows), "kinds": dict(collections.Counter(r["gold_kind"] for r in rows))}))
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("build")
    p = sub.add_parser("pin")
    p.add_argument("--note", default="")
    sub.add_parser("validate-judge")
    p = sub.add_parser("score")
    p.add_argument("--model", required=True)
    p.add_argument("--url", default=common.STEWARD_URL)
    p = sub.add_parser("export-codex")
    p.add_argument("--model", default="steward-base")
    p.add_argument("--out", default="<inbox>/stewardbench2/codex_sample.jsonl")
    args = ap.parse_args()
    return {"build": cmd_build, "pin": cmd_pin, "validate-judge": cmd_validate_judge, "score": cmd_score,
            "export-codex": cmd_export_codex}[args.cmd](args)


if __name__ == "__main__":
    sys.exit(main())
