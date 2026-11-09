"""One-command launcher for the fine-tuned commissar's final runs (prereg/R5ft.md, prereg/R5ft2.md), start to finish.

  python3 experiments/commissar/r5ft.py [--arm r5ft]   R5ft: refuses unless /v1/models lists steward-lora
  python3 experiments/commissar/r5ft.py --arm r5ft2    R5ft2: refuses unless /v1/models lists steward-lora-v5 (or the
                                                       --model given) and, for R5ft2, the adapter slot holds v5
  ... --arm r5ft2x                                     R5ft2x: R5ft2's protocol, exploratory, under its own names
  ... --dry-run                                        plumbing check: steward-base on the w04 E pair (2 cells), every
                                                       output under the arm's dry-run folder, no commit

Steps (each resumes: a rerun after an interruption repeats only what is missing):
  1. check that the server lists the model (and nothing is decided by a model the server does not name); for an arm
     with an adapter folder, record the slot's status and weights' sha256 (checked again after the freeze)
  2. start the fresh A0 rerun in the background (it does not depend on the rewrites); a finished run is kept, never
     started again
  3. generate the rewrites (eval_rewrites.generate: v2.2 instructions, the strict validator W1-W13, cap 10)
  4. freeze them once, check every accepted attempt names the model, write the rewrite statistics (byte-identity and
     added guidance included), and commit (sha256 in the message)
  5. compile the arm (eval_model.compile_r5 over rewrite_arm.overlay) and commit the provenance
  6. run the arm; wait for both runs (a run stopped by castra's catalog probe before any episode is relaunched, up to
     RELAUNCHES times per invocation, each stopped launch's log kept as .launchK-probe-refused.log)
  7. analyse: search_analysis.py confirm, analyze.py per-run CSVs and summaries, the separate recount with Holm across
     the arm's family of rewrite tests, and the exploratory comparisons with earlier rewrite runs; commit the results

Re-execs under Python 3.12 with the castra export on PYTHONPATH (COMMISSAR_CASTRA or --castra).
"""
import argparse
import hashlib
import json
import os
import pathlib
import subprocess
import sys
import urllib.request

EXP = pathlib.Path(__file__).resolve().parent
REPO = EXP.parents[1]
PY312 = pathlib.Path.home() / ".local/bin/python3.12"
URL = "http://127.0.0.1:8417/v1"
PROMPT = EXP / "steward/prompts/commissar_prompt_v2_2.txt"
RELAUNCHES = 3                               # probe-stopped relaunches per run per invocation (prereg/R5ft.md, N2)
DRY_CELLS = ("w04.principal.E", "w04.teammate.E")
SLOT_MODEL = "steward-lora"                  # the server's single adapter slot (commissar serve/adapters.py)
# Each fine-tune arm, as its prereg fixes it: the served model, the adapter folder the slot must hold (None: not
# checked, as R5ft ran), the earlier confirmatory rewrite tests for Holm (primary p values as reported), the earlier
# rewrite runs it is compared with (exploratory), and the folder its dry run writes to.
ARMS = {
    "r5ft": {"name": "R5ft", "model": "steward-lora", "adapter": None, "family": ["R5=0.5", "R5v22=0.125"],
             "compare": [("r5v22", "R5v22")], "dry_dir": pathlib.Path("<inbox>/r5ft-prep/dryrun")},
    "r5ft2": {"name": "R5ft2", "model": "steward-lora-v5", "adapter": "v5",
              "family": ["R5=0.5", "R5v22=0.125", "R5ft=0.875"], "compare": [("r5v22", "R5v22"), ("r5ft", "R5ft")],
              "dry_dir": pathlib.Path("<inbox>/r5ft2-prep/dryrun")},
}
# R5ft2x: R5ft2's frozen protocol run after its 01:40 last launch, so exploratory (prereg/R5ft2x_exploratory_note.md).
# Same model, adapter check, analysis and comparisons; its own label keeps every output apart from R5ft2's names. The
# family is R5ft2's, so the recount shows the Holm figure R5ft2's analysis would give; it is not a confirmatory test.
ARMS["r5ft2x"] = {**ARMS["r5ft2"], "name": "R5ft2x", "dry_dir": pathlib.Path("<inbox>/r5ft2x/dryrun")}
FAMILY = ARMS["r5ft"]["family"]              # R5ft's family (kept for the tests and readers of R5ft)


def plan(dry_run, arm="r5ft", model=None):
    """Where everything goes. The final run writes into the repository's usual places; a dry run writes only under
    the arm's dry-run folder, uses steward-base, checks no adapter and never commits."""
    a = ARMS[arm]
    common = {"name": a["name"], "family": a["family"], "compare": a["compare"]}
    if dry_run:
        root = a["dry_dir"]
        return {**common, "model": "steward-base", "adapter": None, "cells": DRY_CELLS, "commit": False,
                "label": f"{arm}-dryrun", "steward": root / "steward", "specs": root / "specs", "runs": root / "runs",
                "results": root / "results"}
    return {**common, "model": model or a["model"], "adapter": a["adapter"], "cells": None, "commit": True,
            "label": arm, "steward": EXP / "steward" / arm, "specs": EXP / "specs", "runs": EXP / "runs", "results": EXP}


def ensure_runtime(castra):
    want = str(pathlib.Path(castra).resolve())
    if sys.version_info[:2] >= (3, 12) and os.environ.get("PYTHONPATH", "").split(":")[0] == want:
        return
    env = {**os.environ, "PYTHONPATH": want, "PYTHONDONTWRITEBYTECODE": "1"}
    os.execve(str(PY312), [str(PY312), __file__] + sys.argv[1:], env)


def served(url):
    return [m["id"] for m in json.load(urllib.request.urlopen(url.rstrip("/") + "/models", timeout=30))["data"]]


def sha256(path):
    return hashlib.sha256(pathlib.Path(path).read_bytes()).hexdigest()


def adapter_status(url):
    """The server's GET /admin/adapter (the slot's configured, found and loaded folders)."""
    root = url.rsplit("/v1", 1)[0]
    return json.load(urllib.request.urlopen(root + "/admin/adapter", timeout=30))


def loaded_dirs(status):
    """Every loaded_dir anywhere in an adapter status (one slot today; tolerant of a list of slots)."""
    if isinstance(status, dict):
        return [v for k, v in status.items() if k == "loaded_dir" and v] + \
               [d for v in status.values() for d in loaded_dirs(v)]
    if isinstance(status, list):
        return [d for v in status for d in loaded_dirs(v)]
    return []


def adapter_record(status, want, expect_sha256=None):
    """{status, dir, weights sha256} for the loaded folder named want (e.g. 'v5'); SystemExit if none is loaded, or if
    expect_sha256 (the hash posted for the adapter) is given and the loaded weights do not have it."""
    dirs = [d for d in loaded_dirs(status) if pathlib.Path(d).name == want]
    if not dirs:
        raise SystemExit(f"refused: no adapter loaded from a '{want}' folder ({loaded_dirs(status)})")
    weights = sorted(pathlib.Path(dirs[0]).rglob("adapter_model.safetensors"))
    rec = {"status": status, "dir": dirs[0], "weights_sha256": {str(w): sha256(w) for w in weights}}
    if expect_sha256 and list(rec["weights_sha256"].values()) != [expect_sha256]:
        raise SystemExit(f"refused: loaded weights {rec['weights_sha256']} are not the posted {expect_sha256}")
    return rec


def git_commit(paths, message):
    """Commit exactly these paths (never anything else in the shared worktree)."""
    rel = [str(pathlib.Path(p).resolve().relative_to(REPO)) for p in paths]
    subprocess.run(["git", "-C", str(REPO), "add", "--"] + rel, check=True)
    if subprocess.run(["git", "-C", str(REPO), "diff", "--cached", "--quiet", "--"] + rel).returncode == 0:
        return None                                       # nothing new (a resumed run)
    msg = message + "\n\nCo-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
    subprocess.run(["git", "-C", str(REPO), "commit", "-q", "-m", msg, "--"] + rel, check=True)
    return subprocess.run(["git", "-C", str(REPO), "rev-parse", "--short", "HEAD"], capture_output=True,
                          text=True).stdout.strip()


def a0_specs(p):
    """The A0 rerun's specs: specs/a0.jsonl unchanged, or its dry-run cells copied with their provenance."""
    if p["cells"] is None:
        return EXP / "specs" / "a0.jsonl"
    keep = {f"commissar.{c.split('.')[0]}.beneficiary.{c.split('.')[1]}.solvable.{c.split('.')[2]}.none" for c in p["cells"]}
    out = p["specs"] / "a0-dry.jsonl"
    out.parent.mkdir(parents=True, exist_ok=True)
    for src, dst in ((EXP / "specs" / "a0.jsonl", out),
                     (EXP / "specs" / "a0.provenance.jsonl", out.with_suffix(".provenance.jsonl"))):
        lines = [l for l in open(src) if json.loads(l)["episode_id"] in keep]
        if len(lines) != len(keep):
            raise SystemExit(f"{src}: found {len(lines)} of the dry-run cells")
        dst.write_text("".join(lines))
    return out


def run_log(run_dir):
    return run_dir.parent / (run_dir.name + ".log")


def run_complete(specs, run_dir):
    """True if every episode in specs already has a record in the run: a finished run is kept, never started again
    (castra would add second attempts, and the analysis reads the latest attempt per episode)."""
    done = run_dir / "episodes.jsonl"
    if not done.exists():
        return False
    ids = {json.loads(l)["id"] for l in open(done)}
    return all(json.loads(l)["episode_id"] in ids for l in open(specs))


def set_aside_refusal(log, run_dir):
    """Rename a launch's log to the next free RUN.launchK-probe-refused.log if castra's catalog probe stopped it before
    any episode; False (log untouched) otherwise."""
    started = (run_dir / "episodes.jsonl").exists() and (run_dir / "episodes.jsonl").stat().st_size > 0
    if started or not log.exists() or "ProbeRefused" not in log.read_text():
        return False
    k = 1
    while log.with_name(log.name.replace(".log", f".launch{k}-probe-refused.log")).exists():
        k += 1
    log.rename(log.with_name(log.name.replace(".log", f".launch{k}-probe-refused.log")))
    return True


def start_run(castra, specs, run_dir, workers=3):
    """Popen of run.sh for one arm, its console going to RUN.log."""
    log = run_log(run_dir)
    run_dir.parent.mkdir(parents=True, exist_ok=True)
    f = open(log, "a")
    cmd = [str(EXP / "run.sh"), str(castra), "run", "--subject", "claude:claude-haiku-5-5", "--specs", str(specs),
           "--run", str(run_dir), "--workers", str(workers)]
    return subprocess.Popen(cmd, stdout=f, stderr=subprocess.STDOUT, cwd=EXP), log


def finish_run(proc, log, castra, specs, run_dir):
    """Wait for a run (None: a kept, finished run); relaunch up to RELAUNCHES times while castra's catalog probe stops
    it before any episode, each stopped launch's log kept."""
    relaunches = 0
    while proc is not None and proc.wait() != 0:
        if relaunches == RELAUNCHES or not set_aside_refusal(log, run_dir):
            raise SystemExit(f"run.sh failed for {run_dir}; see {log}")
        relaunches += 1
        proc, log = start_run(castra, specs, run_dir)


def launch(castra, specs, run_dir, what, lab):
    """Start a run unless it already finished (kept as is); a leftover probe-refused log is set aside first."""
    if run_complete(specs, run_dir):
        print(f"[{lab}] {what} already complete, kept -> {run_dir}", flush=True)
        return None, run_log(run_dir)
    set_aside_refusal(run_log(run_dir), run_dir)
    proc, log = start_run(castra, specs, run_dir)
    print(f"[{lab}] {what} started -> {run_dir}", flush=True)
    return proc, log


def bases_for(p):
    import compile as K
    import gen_rewrite as GR
    bases = K.released_bases(EXP / "data" / "pilot.jsonl")
    return [b for b in bases if p["cells"] is None or GR.cell_key(b) in p["cells"]]


def rewrites(p, bases):
    """Steps 3 and 4: generate, freeze once, check the model named by every accepted attempt; returns (rows, sha)."""
    import eval_rewrites as ER
    p["steward"].mkdir(parents=True, exist_ok=True)
    log, frozen = p["steward"] / "attempts.jsonl", p["steward"] / "frozen.jsonl"
    calls = ER.generate(URL, p["model"], bases, log, max_attempts=10, workers=4, system_prompt_path=PROMPT,
                        validator_name="current")
    if not frozen.exists():
        rows = ER.freeze(bases, log, p["model"], URL, 10, PROMPT)
        frozen.write_text("".join(json.dumps(r, sort_keys=True, ensure_ascii=False) + "\n" for r in rows))
    rows = [json.loads(l) for l in frozen.read_text().splitlines()]
    named = {r["rewrite"]["response_model"] for r in rows if r["rewrite"]}
    if named - {p["model"]}:
        raise SystemExit(f"accepted rewrites name {sorted(named)}, not only {p['model']}: provenance check failed")
    return rows, sha256(frozen), calls


def write_stats(p, bases):
    """The rewrite statistics (rewrite_stats.py: coverage, rules, judge, byte-identity, added guidance) before any
    episode."""
    import gen_rewrite as GR
    import rewrite_stats as RS
    rows = [json.loads(l) for l in open(p["steward"] / "attempts.jsonl")]
    frozen = [json.loads(l) for l in open(p["steward"] / "frozen.jsonl")]
    out = p["results"] / f"{p['label']}-rewrite-stats.json"
    stats = RS.stats(rows, frozen, {GR.cell_key(b): b for b in bases})
    out.write_text(json.dumps(stats, indent=1) + "\n")
    return out, stats


def analyse(p, arm_specs, arm_run, a0_spec, a0_run):
    """Step 7: the pre-registered analysis, per-run summaries, the separate recount, the earlier-run comparisons."""
    res, lab = p["results"], p["label"]
    env = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}
    def py(*args):
        subprocess.run(["python3"] + [str(a) for a in args], check=True, cwd=EXP, env=env, stdout=subprocess.DEVNULL)
    out = {"confirm": res / f"{lab}-confirm.json", "recount": res / f"{lab}-recount.json"}
    py("search_analysis.py", "confirm", "--ref", a0_run, "--ref-specs", a0_spec.with_suffix(""), "--arm-name", "rewrite",
       "--run", arm_run, "--specs", arm_specs.with_suffix(""), "--a0", EXP / "runs" / "a0-haiku", "--json", out["confirm"])
    for run, spec, name in ((arm_run, arm_specs, f"{lab}-rewrite"), (a0_run, a0_spec, f"{lab}-a0")):
        py("analyze.py", run, "--provenance", spec.with_suffix(".provenance.jsonl"), "--csv", res / f"{name}-haiku.csv",
           "--json", res / f"{name}-haiku.summary.json")
        out[name] = res / f"{name}-haiku.summary.json"
        out[name + "-csv"] = res / f"{name}-haiku.csv"
    py("recount_r5v22.py", "--arm", arm_run, "--ref", a0_run, "--family", *p["family"], "--name", p["name"],
       "--json", out["recount"])
    for key, name in p["compare"]:
        if (EXP / "runs" / f"{key}-rewrite").exists():
            out[f"vs_{key}"] = res / f"{lab}-vs-{key}.json"
            py("recount_r5v22.py", "--arm", arm_run, "--ref", EXP / "runs" / f"{key}-rewrite",
               "--name", f"{p['name']}_vs_{name}", "--json", out[f"vs_{key}"])
    return out


def table(out):
    r = json.loads(out["recount"].read_text())
    holm = next(v for k, v in r.items() if k.startswith("holm_across"))
    rows = [("cells (arm / A0 rerun)", f"{r['cells_arm']} / {r['cells_ref']}"),
            ("gap change (primary)", r["primary_gap_change"]), ("Holm across the family", holm),
            ("principal", r["principal"]), ("teammate", r["teammate"]),
            ("held-out w05-w08", r["heldout_w05_w08_gap_change"]), ("dev w01-w04", r["dev_w01_w04_gap_change"]),
            ("TEST (arm, A0 rerun)", r["test"]), ("guardrails", r["guardrails"])]
    return "\n".join(f"{k}: {json.dumps(v)}" for k, v in rows)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--arm", choices=sorted(ARMS), default="r5ft")
    ap.add_argument("--model", help=f"the served name, when it differs from the arm's (e.g. {SLOT_MODEL} for the slot)")
    ap.add_argument("--adapter-sha256", help="the posted sha256 of the adapter's weights; refused unless they match")
    ap.add_argument("--castra", default=os.environ.get("COMMISSAR_CASTRA", "<inbox>/eval-harness/castra8457977"))
    a = ap.parse_args(argv)
    ensure_runtime(a.castra)
    sys.path[:0] = [str(EXP), str(EXP / "steward")]
    p = plan(a.dry_run, a.arm, a.model)
    names = served(URL)
    if p["model"] not in names:
        raise SystemExit(f"r5ft: refused: {p['model']} is not on the server ({names})")
    for d in ("steward", "specs", "runs", "results"):
        p[d].mkdir(parents=True, exist_ok=True)
    lab, name = p["label"], p["name"]
    adapter = p["adapter"] and {"before": adapter_record(adapter_status(URL), p["adapter"], a.adapter_sha256),
                                "posted_sha256": a.adapter_sha256}
    a0_spec, a0_run = a0_specs(p), p["runs"] / f"{lab}-a0"
    a0_proc, a0_log = launch(a.castra, a0_spec, a0_run, "A0 rerun", lab)
    bases = bases_for(p)
    rows, frozen_sha, calls = rewrites(p, bases)
    covered = sum(1 for r in rows if r["rewrite"])
    print(f"[{lab}] rewrites frozen: {covered}/{len(rows)} cells, sha256 {frozen_sha}, {calls} server calls", flush=True)
    frozen_paths = [p["steward"] / "attempts.jsonl", p["steward"] / "frozen.jsonl"]
    if adapter:
        adapter["after_freeze"] = adapter_record(adapter_status(URL), p["adapter"], a.adapter_sha256)
        if adapter["after_freeze"]["dir"] != adapter["before"]["dir"] or \
                adapter["after_freeze"]["weights_sha256"] != adapter["before"]["weights_sha256"]:
            raise SystemExit(f"[{lab}] the loaded adapter changed during generation: provenance check failed")
        (p["steward"] / "adapter.json").write_text(json.dumps(adapter, indent=1) + "\n")
        frozen_paths.append(p["steward"] / "adapter.json")
    stats_path, stats = write_stats(p, bases)
    ident = stats["byte_identical"]
    print(f"[{lab}] byte-identical {ident['both']}/{ident['of']}, added guidance {stats['adds_priority_guidance']}",
          flush=True)
    commits = []
    if p["commit"]:
        commits.append(git_commit(frozen_paths + [stats_path],
                                  f"operae commissar {name}: freeze the rewrites before any {name} episode (frozen.jsonl "
                                  f"sha256 {frozen_sha}; {covered} of {len(rows)} cells; model {p['model']}; "
                                  f"byte-identical {ident['both']} of {ident['of']})"))
    import eval_model as M
    arm_specs = p["specs"] / f"{lab}-rewrite.jsonl"
    n = M.compile_r5(bases, rows, frozen_sha, arm_specs)
    if p["commit"]:
        commits.append(git_commit([arm_specs.with_suffix(".provenance.jsonl")],
                                  f"operae commissar {name}: compiled provenance ({n} specs) before any {name} episode"))
    arm_run = p["runs"] / f"{lab}-rewrite"
    if n:
        arm_proc, arm_log = launch(a.castra, arm_specs, arm_run, f"arm ({n} episodes)", lab)
        finish_run(arm_proc, arm_log, a.castra, arm_specs, arm_run)
    finish_run(a0_proc, a0_log, a.castra, a0_spec, a0_run)
    if not n:
        raise SystemExit(f"[{lab}] no cell has an accepted rewrite: nothing to compare (A0 rerun kept)")
    out = analyse(p, arm_specs, arm_run, a0_spec, a0_run)
    print(table(out), flush=True)
    if p["commit"]:
        commits.append(git_commit([v for v in out.values() if v.exists()] + [p["steward"] / "attempts.jsonl"],
                                  f"operae commissar {name}: results (search_analysis confirm, per-run summaries, "
                                  f"separate recount with Holm across {', '.join(f.split('=')[0] for f in p['family'])} "
                                  f"and {name})"))
    print(f"[{lab}] done; commits {commits}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
