"""One command that scores a commissar model version: operae R5 on the dev split, StewardBench v2.1 and rewrite
fidelity, written to evals/<model>/summary.json and folded into evals/compare.md.

Ephraiem's loop (2026-11-08 19:06): fine-tune the commissar, measure how much it raises his Class II score, improve
the data and the fine-tune, repeat. The commissar is a rewriting layer (rewrite.py, R5): it rewrites the principal's
request before the neutral Haiku 5.5 subject reads it.

  python3 experiments/commissar/eval_model.py --model steward-lora            (dev split; re-execs under Python 3.12)

Parts (each skippable with --skip operae|bench|fidelity; every part resumes from its own logs, so a rerun after an
interruption costs only what is missing):
  1. operae DEV: R5 rewrites by MODEL on worlds w01 to w04 (16 cells) by prereg/R5.md's procedure (eval_rewrites.py
     over agent N's steward/gen_rewrite.py: kickoff and request, rules W1 to W11, up to 10 attempts), compiled by
     rewrite_arm.overlay, run on the pinned castra and subject (run.sh, pins.py), then compared
     cell by cell with the A0 run of record on the same cells: gap change (principal minus teammate), each
     beneficiary's change (world-weighted t interval, exact sign-flip p, Holm over the three), TEST share, guardrail
     events (search_analysis.guardrails), rewrite coverage and every validation failure.
  2. StewardBench v2.1 (eval_bench.py, outputs redirected here; the bench checkout is never written).
  3. Rewrite fidelity on agent D's held-out rewrite rows (eval_fidelity.py), when the file exists.
The FINAL split (all 32 cells plus a fresh A0) is refused: it needs the manager's explicit go and its own
preregistration, and is run by its own procedure, not this tool.

Outputs: evals/<model>/{rewrites.attempts.jsonl (+ .seed.json when seeded), rewrites.frozen.jsonl, operae.json,
stewardbench/<model>/, fidelity.jsonl, fidelity.json, summary.json}, specs/eval-<model>-dev.jsonl (git-ignored, like
every spec) with its committed .provenance.jsonl, and runs/eval-<model>-dev (git-ignored). --tag T writes
evals/<model>.T/ instead; --from-frozen and --from-run reuse rewrites and episodes that already exist (agent N's R5
freeze and run), checked spec hash by spec hash, so a model measured elsewhere costs no request. evals/compare.md and evals/compare.json are rebuilt from every
evals/*/summary.json on each run.
"""
import argparse
import collections
import datetime
import json
import os
import pathlib
import re
import subprocess
import sys

EXP = pathlib.Path(__file__).resolve().parent
PY312 = pathlib.Path.home() / ".local/bin/python3.12"
DEFAULT_CASTRA = os.environ.get("COMMISSAR_CASTRA", "<inbox>/eval-harness/castra8457977")
DEV_WORLDS = ("w01", "w02", "w03", "w04")
A0_RUN = EXP / "runs" / "a0-haiku"
BENCH = pathlib.Path.home() / "projects" / "commissar" / "bench"
DATA = pathlib.Path.home() / "projects" / "commissar" / "data"


def ensure_runtime(castra):
    """Re-exec under Python 3.12 with castra on PYTHONPATH and no bytecode writes, unless already so."""
    want = str(pathlib.Path(castra).resolve())
    if sys.version_info[:2] >= (3, 12) and os.environ.get("PYTHONPATH", "").split(":")[0] == want:
        return
    env = {**os.environ, "PYTHONPATH": want, "PYTHONDONTWRITEBYTECODE": "1"}
    os.execve(str(PY312), [str(PY312), __file__] + sys.argv[1:], env)


def safe(model):
    return re.sub(r"[^A-Za-z0-9._-]+", "_", model)


# ---- 1. operae dev ------------------------------------------------------------------------------------------------
def dev_bases():
    import compile as K
    bases = [b for b in K.released_bases(EXP / "data" / "pilot.jsonl") if b["factors"]["world"][4:7] in DEV_WORLDS]
    if len(bases) != 16:
        raise SystemExit(f"expected 16 dev cells, found {len(bases)}")
    return bases


def compile_r5(bases, frozen_rows, frozen_sha256, specs_path):
    """Write the R5 specs and provenance (rewrite_arm.overlay) for every cell with an accepted rewrite; returns the
    number of specs."""
    import compile as K
    import pins
    import rewrite_arm as RA
    import gen_rewrite as GR
    engine = pins.check_imported()
    build = {"castra_commit": pins.CASTRA_COMMIT, "engine_sha256": engine}
    released = {"hub_repo": "ephraiemsam16/operae-private", "hub_commit": K.HUB_COMMIT, "file": K.RELEASED_FILE,
                "file_sha256": K.RELEASED_FILE_SHA256}
    by_key = {r["key"]: r for r in frozen_rows}
    pairs = [RA.overlay(b, K.BANK_COMMIT, by_key[GR.cell_key(b)], frozen_sha256, build=build, released=released)
             for b in bases if by_key[GR.cell_key(b)]["rewrite"]]
    specs_path.parent.mkdir(parents=True, exist_ok=True)
    specs_path.write_text("".join(json.dumps(s, sort_keys=True, ensure_ascii=False) + "\n" for s, _ in pairs))
    specs_path.with_suffix(".provenance.jsonl").write_text("".join(json.dumps(p, sort_keys=True) + "\n" for _, p in pairs))
    return len(pairs)


def run_log(run_dir):
    """The run's console log beside it: RUN.log. Not with_suffix, which would cut a --tag's dot (eval-x.v2_2-dev)."""
    return run_dir.parent / (run_dir.name + ".log")


def run_subject(castra, specs_path, run_dir, workers):
    """Run (or resume) the R5 episodes through run.sh on the pinned castra, subject and CLI."""
    import pins
    cmd = [str(EXP / "run.sh"), str(castra), "run", "--subject", pins.SUBJECT, "--specs", str(specs_path),
           "--run", str(run_dir), "--workers", str(workers)]
    log = run_log(run_dir)
    with open(log, "a") as f:
        rc = subprocess.run(cmd, stdout=f, stderr=subprocess.STDOUT, cwd=EXP).returncode
    if rc != 0:
        raise SystemExit(f"run.sh exited {rc}; see {log}")


def compare_dev(run_dir, provenance=None):
    """R5 against the A0 run of record on the same dev cells (compare.py's statistics, search_analysis.py's
    guardrails). The run may hold more cells than the dev split (a confirmatory 32-cell run); only its dev cells are
    compared, and its gate is the whole run's."""
    import analyze as A
    import compare as CP
    import search_analysis as SA
    s1, rows1 = A.summarise(run_dir, provenance)
    rows1 = [x for x in rows1 if x["world"] in DEV_WORLDS]
    _, rows0 = A.summarise(A0_RUN)
    cell = CP.cell
    a1 = {cell(x): x for x in rows1}
    a0 = {cell(x): x for x in rows0 if x["world"] in DEV_WORLDS}
    shared = sorted(c for c in a1 if c in a0)
    prim = {b: CP.primary(a0, a1, b) for b in ("principal", "teammate")} if shared else {}
    gc = CP.gap_change(a0, a1) if shared else {"mean": None}
    ps = [gc.get("sign_flip_p"), prim.get("principal", {}).get("sign_flip_p"), prim.get("teammate", {}).get("sign_flip_p")]
    holm = dict(zip(("gap_change", "principal", "teammate"), CP.holm(ps))) if None not in ps else None
    g1, g0 = SA.guardrails(run_dir), SA.guardrails(A0_RUN)
    ids1 = {x["id"] for x in rows1}
    g1_ep = {k: v for k, v in g1["episodes"].items() if k in ids1}
    g1 = {"events": sum(len(v) for v in g1_ep.values()),
          "by_kind": dict(collections.Counter(k for v in g1_ep.values() for k in v)), "episodes": g1_ep}
    ids0 = {x["id"] for c, x in a0.items() if c in a1}
    g0_same = {k: v for k, v in g0["episodes"].items() if k in ids0}
    return {"gate": SA.treatment_gate(s1)["pass"], "gate_detail": SA.treatment_gate(s1),
            "terminations": s1["terminations"], "cells_run": len(a1), "cells_paired": len(shared),
            "worlds_paired": sorted({c[0] for c in shared}), "gap_change": gc, "primary": prim, "holm_three": holm,
            "test_share": {"r5": CP.test_share(rows1, "R5"),
                           "a0_same_cells": CP.test_share([a0[c] for c in shared], "A0 (the same cells)")},
            "guardrails": {"r5": g1, "a0_same_cells": {"events": sum(len(v) for v in g0_same.values()),
                                                        "episodes": g0_same}},
            "subject_turns": SA.subject_turns(run_dir),
            "per_cell": [{"cell": "%s %s %s" % c, "a0": a0[c]["progress"], "r5": a1[c]["progress"],
                          "r5_looked": a1[c]["looked"]} for c in shared]}


def reuse_frozen(source, keys, frozen_path):
    """Copy the dev rows of an existing frozen R5 file (gen_rewrite's format, e.g. steward/rewrite/frozen.jsonl) into
    frozen_path once. Refuses unless every dev key is present. Returns {source, source_sha256, rows}."""
    import hashlib
    data = pathlib.Path(source).read_bytes()
    rows = {r["key"]: r for r in map(json.loads, data.decode().splitlines()) if r.get("key") in keys}
    if set(rows) != keys:
        raise SystemExit(f"{source} lacks dev cells {sorted(keys - set(rows))}")
    if not frozen_path.exists():
        frozen_path.write_text("".join(json.dumps(rows[k], sort_keys=True, ensure_ascii=False) + "\n" for k in sorted(rows)))
    return {"source": str(source), "source_sha256": hashlib.sha256(data).hexdigest(), "rows": len(rows)}


def check_run_matches(specs_path, run_dir):
    """Refuse unless every compiled dev spec is in the existing run with the same spec_sha256 (the run used exactly
    these rewrites)."""
    import compile as K
    compiled = {p["episode_id"]: p["spec_sha256"] for p in map(json.loads, specs_path.with_suffix(".provenance.jsonl")
                                                                .read_text().splitlines())}
    ran = {}
    for line in open(run_dir / "episodes.jsonl"):
        r = json.loads(line)
        ran[r["id"]] = r["spec_sha256"]
    bad = sorted(i for i, h in compiled.items() if ran.get(i) != h)
    if bad:
        raise SystemExit(f"{run_dir} did not run these rewrites for {bad}")
    return len(compiled)


def operae_dev(model, url, castra, out, workers, max_attempts, gen_workers, seed_attempts=None, from_frozen=None,
               from_run=None, from_run_provenance=None, system_prompt_path=None, validator_name="current"):
    """Part 1. Rewrites come from generation (resuming any log, optionally seeded), or from an existing frozen file
    (from_frozen); episodes come from running the dev specs, or from an existing run that used exactly these
    rewrites (from_run), so a model already measured elsewhere costs no new request."""
    import hashlib
    import gen_rewrite as GR
    import eval_rewrites as ER
    bases = dev_bases()
    log = out / "rewrites.attempts.jsonl"
    keys = {GR.cell_key(b) for b in bases}
    seeded = ER.seed_from(seed_attempts, log, model, keys) if seed_attempts else None
    frozen_path = out / "rewrites.frozen.jsonl"
    reused = reuse_frozen(from_frozen, keys, frozen_path) if from_frozen else None
    calls = 0 if from_frozen else ER.generate(url, model, bases, log, max_attempts=max_attempts, workers=gen_workers,
                                              system_prompt_path=system_prompt_path, validator_name=validator_name)
    if not frozen_path.exists():                          # written once, never overwritten
        rows = ER.freeze(bases, log, model, url, max_attempts, system_prompt_path)
        frozen_path.write_text("".join(json.dumps(r, sort_keys=True, ensure_ascii=False) + "\n" for r in rows))
    frozen = [json.loads(l) for l in frozen_path.read_text().splitlines()]
    frozen_sha = hashlib.sha256(frozen_path.read_bytes()).hexdigest()
    specs_path = EXP / "specs" / f"eval-{out.name}-dev.jsonl"
    n = compile_r5(bases, frozen, frozen_sha, specs_path)
    res = {"split": "dev", "worlds": list(DEV_WORLDS), "rewrites": ER.stats(bases, log, frozen, max_attempts),
           "system_prompt": str(system_prompt_path or "steward/search/system_prompt.txt (commissar_prompt_v2_1)"),
           "system_prompt_sha256": ER.system_prompt(system_prompt_path)[1],
           "validator": validator_name, "validator_rules": ER.VALIDATORS[validator_name],
           "commissar_calls_this_run": calls, "seeded_attempts": seeded, "reused_frozen": reused,
           "frozen_sha256": frozen_sha,
           "specs": str(specs_path.relative_to(EXP)), "specs_compiled": n}
    if n == 0:
        res["comparison"] = None
        res["note"] = "no cell has an accepted rewrite, so no R5 episode can run (coverage 0)"
        return res
    if from_run:
        run_dir = pathlib.Path(from_run).resolve()
        res["reused_run"] = {"run": str(run_dir), "dev_specs_matched": check_run_matches(specs_path, run_dir)}
        res["run"] = str(run_dir)
        res["comparison"] = compare_dev(run_dir, from_run_provenance)
        return res
    run_dir = EXP / "runs" / f"eval-{out.name}-dev"
    run_subject(castra, specs_path, run_dir, workers)
    res["run"] = str(run_dir.relative_to(EXP))
    res["comparison"] = compare_dev(run_dir, specs_path.with_suffix(".provenance.jsonl"))
    return res


# ---- 2 and 3 --------------------------------------------------------------------------------------------------------
def stewardbench(model, url, out, system_prompt_path=None):
    """StewardBench v2.1 through eval_bench.py under the bench's interpreter; returns the headline scores."""
    res_root = out / "stewardbench"
    judg = res_root / model / "judgments.jsonl"
    before = sum(1 for _ in open(judg)) if judg.exists() else 0
    env = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    cmd = ["python3", str(EXP / "eval_bench.py"), "--bench", str(BENCH), "--model", model, "--out", str(res_root),
           "--url", url] + (["--system-prompt", str(pathlib.Path(system_prompt_path).resolve())] if system_prompt_path else [])
    p = subprocess.run(cmd, capture_output=True, text=True, env=env, cwd=EXP)
    (out / "stewardbench.log").write_text(p.stdout + p.stderr)
    if p.returncode != 0:
        return {"error": f"eval_bench.py exited {p.returncode}; see stewardbench.log"}
    meta = json.loads(p.stdout.strip().splitlines()[-1])
    s = json.loads(pathlib.Path(meta["scores_path"]).read_text())
    after = sum(1 for _ in open(judg)) if judg.exists() else 0
    return {"macro_accuracy": s["macro_accuracy"], "micro_accuracy": s["micro_accuracy"], "n_items": s["n_items"],
            "per_kind_accuracy": s["per_kind_accuracy"],
            "forged_approval_endorsement_rate": s["forged_approval_endorsement_rate"],
            "false_alarm_rate_stay_quiet": s["false_alarm_rate_stay_quiet"], "flag_rates": s["flag_rates"],
            "new_judge_rows_this_run": after - before, "seeded_from_bench": meta["seeded"],
            "scores": str(pathlib.Path(meta["scores_path"]).relative_to(EXP))}


def fidelity(model, url, out, holdout, limit, gen_workers):
    import eval_fidelity as F
    import gen_rewrite as GR
    import generate as G
    path = holdout or F.find_holdout(DATA)
    if not path or not pathlib.Path(path).exists():
        return {"status": "not available", "looked_for": str(DATA / "*rewrite*holdout*.jsonl")}
    s = F.run(url, model, path, out, GR.SYSTEM_PROMPT.read_text(), G.ask, limit=limit, workers=gen_workers)
    (out / "fidelity.json").write_text(json.dumps(s, indent=1) + "\n")
    return s


# ---- the compare table ----------------------------------------------------------------------------------------------
def _fmt(x, nd=2):
    return "-" if x is None else f"{x:+.{nd}f}" if isinstance(x, float) else str(x)


def _ci(d):
    if not d or d.get("mean") is None:
        return "-"
    lo, hi = d.get("ci95") or [None, None]
    ci = f" [{lo:+.2f}, {hi:+.2f}]" if lo is not None else ""
    return f"{d['mean']:+.2f}{ci}, p {d.get('sign_flip_p'):.2f}" if d.get("sign_flip_p") is not None else f"{d['mean']:+.2f}{ci}"


def build_compare(evals_dir):
    rows = []
    for p in sorted(evals_dir.glob("*/summary.json")):
        s = json.loads(p.read_text())
        op = s.get("operae") or {}
        cmp_ = op.get("comparison") or {}
        rw = op.get("rewrites") or {}
        sb = s.get("stewardbench") or {}
        fi = s.get("fidelity") or {}
        ts = (cmp_.get("test_share") or {}).get("r5") or {}
        rows.append({"model": s["model"] + (f" ({s['tag']})" if s.get("tag") else ""), "evaluated": s["finished_at"],
                     "coverage": f"{rw.get('covered')}/{rw.get('cells')} (at attempt 1: {rw.get('accepted_at_attempt_1')}; cap {rw.get('max_attempts')})" if rw else "-",
                     "gap_change": _ci(cmp_.get("gap_change")), "principal": _ci((cmp_.get("primary") or {}).get("principal")),
                     "teammate": _ci((cmp_.get("primary") or {}).get("teammate")),
                     "test": f"{ts.get('test')}/{ts.get('answered')}" if ts else "-",
                     "guardrails": (cmp_.get("guardrails") or {}).get("r5", {}).get("events", "-") if cmp_ else "-",
                     "stewardbench": f"{sb['macro_accuracy']['value']:.3f} [{sb['macro_accuracy']['ci95'][0]:.3f}, {sb['macro_accuracy']['ci95'][1]:.3f}]" if sb.get("macro_accuracy") else "-",
                     "fidelity": f"{fi['pass']['share']:.2f} ({fi['pass']['k']}/{fi['pass']['n']})" if fi.get("pass") else fi.get("status", "-")})
    head = ["model", "evaluated", "coverage", "gap_change", "principal", "teammate", "test", "guardrails",
            "stewardbench", "fidelity"]
    names = ["model", "evaluated", "R5 dev rewrite coverage", "R5 gap change vs A0 [95% CI], sign-flip p",
             "principal change", "teammate change", "TEST (R5)", "guardrail events (R5)", "StewardBench v2.1 macro",
             "fidelity pass share"]
    md = ["# Commissar model versions (eval_model.py, dev split)", "",
          "Rebuilt from evals/*/summary.json on every run. Dev = worlds w01 to w04 (16 cells), compared with the A0 "
          "run of record on the same cells; the FINAL split is not run by this tool. Interval columns are "
          "world-weighted 95% t intervals with exact sign-flip p (4 worlds at most, so wide).", "",
          "| " + " | ".join(names) + " |", "|" + "-|" * len(names)]
    md += ["| " + " | ".join(str(r[h]) for h in head) + " |" for r in rows]
    (evals_dir / "compare.md").write_text("\n".join(md) + "\n")
    (evals_dir / "compare.json").write_text(json.dumps(rows, indent=1) + "\n")
    return rows


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--model", required=True, help="the model's name on the local server (GET /v1/models)")
    p.add_argument("--split", choices=("dev", "final"), default="dev")
    p.add_argument("--url", default="http://127.0.0.1:8417/v1")
    p.add_argument("--castra", default=DEFAULT_CASTRA, help="an export of castra 8457977 (pins.py checks its bytes)")
    p.add_argument("--workers", type=int, default=3, help="concurrent subject episodes")
    p.add_argument("--gen-workers", type=int, default=2, help="concurrent commissar requests (the server is serial)")
    p.add_argument("--max-attempts", type=int, default=10, help="per cell, as prereg/R5.md (A1L's schedule)")
    p.add_argument("--system-prompt", help="the commissar's system prompt file for the R5 rewrites and StewardBench "
                   "(default: the pinned commissar_prompt_v2_1); exploratory dev rounds only, sha256 recorded")
    p.add_argument("--validator", choices=("current", "r5"), default="current",
                   help="rewrite acceptance: current = gen_rewrite.validate (W1-W12 + W13 judge, one Sonnet call per "
                        "attempt passing W1-W12); r5 = W1-W11 as rounds 0 and 0.5 used")
    p.add_argument("--seed-attempts", help="copy this model's existing attempts from another log (read only), e.g. "
                   "steward/rewrite/attempts.jsonl for steward-base, instead of generating them again")
    p.add_argument("--skip", nargs="*", default=[], choices=("operae", "bench", "fidelity"))
    p.add_argument("--from-frozen", help="use this frozen R5 file's dev rows (gen_rewrite format) instead of generating")
    p.add_argument("--from-run", help="use this castra run's dev episodes (it must have run exactly these rewrites)")
    p.add_argument("--from-run-provenance", help="the reused run's compiled provenance file, for its coverage gate")
    p.add_argument("--tag", help="evals folder suffix (evals/<model>.<tag>/), to keep a second measurement apart")
    p.add_argument("--holdout", help="the rewrite holdout file (default: newest data/*rewrite*holdout*.jsonl)")
    p.add_argument("--fidelity-limit", type=int, default=None)
    a = p.parse_args(argv)
    if a.split == "final":
        raise SystemExit("eval_model: refused: the FINAL split (all 32 cells plus a fresh A0) needs the manager's "
                         "explicit go and its own preregistration, and is not run by this tool")
    ensure_runtime(a.castra)
    sys.path[:0] = [str(EXP), str(EXP / "steward")]
    import urllib.request
    served = [m["id"] for m in json.load(urllib.request.urlopen(a.url.rstrip("/") + "/models", timeout=30))["data"]]
    if a.model not in served:
        raise SystemExit(f"eval_model: {a.model!r} is not on the server ({served})")
    out = EXP / "evals" / (safe(a.model) + (f".{safe(a.tag)}" if a.tag else ""))
    out.mkdir(parents=True, exist_ok=True)
    started = datetime.datetime.now().astimezone().isoformat(timespec="seconds")
    old = json.loads((out / "summary.json").read_text()) if (out / "summary.json").exists() else {}
    # a skipped part keeps its result from the last run, so --skip refreshes one part without losing the others
    summary = {**{k: old[k] for k in ("operae", "stewardbench", "fidelity") if k in old},
               "model": a.model, "tag": a.tag, "url": a.url, "split": a.split, "started_at": started,
               "command": "python3 experiments/commissar/eval_model.py " + " ".join(sys.argv[1:])}
    if "operae" not in a.skip:
        summary["operae"] = operae_dev(a.model, a.url, a.castra, out, a.workers, a.max_attempts, a.gen_workers,
                                       a.seed_attempts, a.from_frozen, a.from_run, a.from_run_provenance,
                                       a.system_prompt, a.validator)
        (out / "operae.json").write_text(json.dumps(summary["operae"], indent=1, default=str) + "\n")
    if "bench" not in a.skip:
        summary["stewardbench"] = stewardbench(a.model, a.url, out, a.system_prompt)
    if "fidelity" not in a.skip:
        summary["fidelity"] = fidelity(a.model, a.url, out, a.holdout, a.fidelity_limit, a.gen_workers)
    summary["finished_at"] = datetime.datetime.now().astimezone().isoformat(timespec="seconds")
    (out / "summary.json").write_text(json.dumps(summary, indent=1, default=str) + "\n")
    rows = build_compare(EXP / "evals")
    print((EXP / "evals" / "compare.md").read_text())
    print(f"summary: {out / 'summary.json'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
