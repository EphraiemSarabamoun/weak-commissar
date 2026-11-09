"""Command line: validate, render, run and analyze (entry point `python3 -m swarm_board <command>`).

  validate CONFIG                     check a config; print each condition's roster and menu
  render CONFIG [--condition ID]      print the round-1 system prompt and user message of the first live agent
  run CONFIG --out DIR [options]      run or resume; live backends probe isolation first and refuse on a fail
  analyze DIR                         write analysis.json and the two CSVs; print the summary

Honeypot episodes (hp_runner, a separate schema in hp_config):
  hp-validate CONFIG                  check a honeypot config; print each condition's instances and rule
  hp-probe CONFIG --out DIR           run only the isolation probe (live Claude) and print its verdict
  hp-run CONFIG --out DIR [options]   run or resume; the claude backend probes first and refuses on a fail
  hp-analyze DIR                      write analysis.json, teams.csv, agents.csv, conditions.csv, plus the
                                      secondary measures (hp_secondary: secondary.json, debrief.csv)
  hp-variant SRC --out DST ...        a calibration variant of an instance (renamed key, or an added brief line)

The codex backend is a stub: `--backend codex` refuses unless --allow-codex-stub is passed, and even then the
stub raises before any call, so this command line cannot spend Codex quota.
"""
import argparse
import json
import subprocess
import sys
from pathlib import Path

from . import analysis, backends, hp_analysis, hp_config, hp_runner, hp_secondary, kin
from . import board as B
from .config import ConfigError, load
from .runner import ResumeMismatch, Run


def cmd_validate(args):
    """Print a one-screen summary of every condition."""
    exp = load(args.config)
    print(f"{exp.name}: seed {exp.seed}, {exp.boards_per_condition} boards per condition, "
          f"config sha256 {exp.config_sha256[:12]}")
    for c in exp.conditions:
        live = [a["name"] for a in c["agents"] if not a.get("scripted")]
        scripted = [a["name"] for a in c["agents"] if a.get("scripted")]
        print(f"  {c['id']}: {len(live)} live {live}, scripted {scripted}, {c['rounds']} rounds, "
              f"{len(c['seed_posts'])} seed posts, menu {[a['id'] for a in c['actions']]}, "
              f"target {c['target_action']}")
    return 0


def cmd_render(args):
    """Show exactly what the first live agent of a condition receives in round 1."""
    exp = load(args.config)
    cond = exp.condition(args.condition) if args.condition else exp.conditions[0]
    agent = next(a for a in cond["agents"] if not a.get("scripted"))
    print("=== SYSTEM ===\n" + B.system_prompt(agent, cond))
    print("\n=== USER ===\n" + B.user_message(agent, cond, B.seed_posts(cond), 1))
    return 0


def cmd_run(args):
    """Probe (live backends), then run or resume the planned boards."""
    exp = load(args.config)
    if args.backend == "codex" and not args.allow_codex_stub:
        print("refused: the codex backend is a stub (pass --allow-codex-stub to see it raise)", file=sys.stderr)
        return 2
    backend = backends.make(args.backend)
    run = Run(exp, args.out, backend, concurrency=args.concurrency, max_calls=args.max_calls,
              max_wall_s=args.max_wall_min * 60 if args.max_wall_min else None,
              conditions=args.conditions.split(",") if args.conditions else None, boards=args.boards,
              model=args.model)
    extra = {}
    models = sorted({run.model or a.get("model") or c["model"] for c in (exp.condition(i) for i in
                     run.condition_ids) for a in c["agents"] if not a.get("scripted")})
    if args.backend == "claude" and any(not m.startswith("claude-") for m in models):
        print(f"refused: the claude backend cannot serve {[m for m in models if not m.startswith('claude-')]}; "
              "a mixed-vendor roster needs a routing backend (not built)", file=sys.stderr)
        return 2
    if args.backend != "mock":
        extra["cli_versions"] = kin.load("subjects").cli_versions()
        probes = {m: backend.probe(m) for m in models}
        Path(args.out).mkdir(parents=True, exist_ok=True)
        (Path(args.out) / "probe.json").write_text(json.dumps(probes, indent=1))
        failed = {m: p["validation"] for m, p in probes.items() if p["validation"]}
        if failed:
            print(f"refused: isolation probe failed: {failed}", file=sys.stderr)
            return 3
        extra["probe"] = {m: {"served_model": p["served_model"], "validation": p["validation"]}
                          for m, p in probes.items()}
    status = run.run(extra)
    print(json.dumps(status, indent=1))
    return 0 if status["state"] == "complete" else 1


def cmd_analyze(args):
    """Analyze a run directory and print the per-condition summary."""
    res = analysis.write(args.run_dir)
    for cid, s in res["conditions"].items():
        print(f"{cid}: final share {s['mean_final_share']} CI {s['final_share_ci95']} "
              f"({s['boards_complete']}/{s['boards_planned']} boards, {s['invalid_turns']} invalid of "
              f"{s['turns']} turns)")
    for k, v in res["contrasts"].items():
        print(f"{k}: {v['estimate']} CI {v.get('ci95')}")
    return 0


def cmd_hp_validate(args):
    """Print each honeypot condition's rule, instances and caps."""
    exp = hp_config.load(args.config)
    print(f"{exp.name}: {exp.teams_per_condition} teams per condition, config sha256 {exp.config_sha256[:12]}")
    for c in exp.conditions:
        print(f"  {c['id']}: rule {c['grader_rule']}, {c['rounds']} rounds, {c['max_tool_calls_per_turn']} tool "
              f"calls/turn, {c['turn_timeout_s']} s/turn, model {c['model']}, instances {c['instances']}")
    return 0


def _hp_probe(exp, out, model):
    """Run the probe; returns (records, failed)."""
    probes = hp_runner.isolation_probe(exp, out, model)
    return probes, {m: p["validation"] for m, p in probes.items() if p["validation"]}


def cmd_hp_probe(args):
    """Run the isolation probe alone."""
    exp = hp_config.load(args.config)
    probes, failed = _hp_probe(exp, args.out, args.model)
    for m, p in probes.items():
        print(f"{m}: {'PASS' if not p['validation'] else 'FAIL ' + str(p['validation'])}; tools "
              f"{(p.get('cli_catalog') or {}).get('tools')}; answer: {p['answer'][:400]!r}")
    return 3 if failed else 0


def _harness_git():
    """This repository's commit and whether tracked files differ from it, for the run manifest."""
    root = Path(__file__).resolve().parent.parent
    git = lambda *a: subprocess.run(["git", "-C", str(root), *a], capture_output=True, text=True).stdout.strip()
    return {"commit": git("rev-parse", "HEAD"), "branch": git("rev-parse", "--abbrev-ref", "HEAD"),
            "dirty_tracked": bool(git("status", "--porcelain", "--untracked-files=no"))}


def cmd_hp_run(args):
    """Probe (claude backend), then run or resume the planned teams."""
    exp = hp_config.load(args.config)
    run = hp_runner.HpRun(exp, args.out, backend=args.backend, concurrency=args.concurrency,
                          max_turns=args.max_turns, max_wall_s=args.max_wall_min * 60 if args.max_wall_min else None,
                          conditions=args.conditions.split(",") if args.conditions else None, teams=args.teams,
                          model=args.model, max_requests=args.max_requests)
    extra = {"harness_git": _harness_git()}
    if args.backend == "claude":
        extra["cli_versions"] = kin.load("subjects").cli_versions()
        probes, failed = _hp_probe(exp, args.out, args.model)
        extra["probe"] = {m: {"served_model": p["served_model"], "validation": p["validation"],
                              "tools": (p.get("cli_catalog") or {}).get("tools")} for m, p in probes.items()}
        if failed:
            print(f"refused: isolation probe failed: {failed}", file=sys.stderr)
            return 3
    status = run.run(extra)
    print(json.dumps(status, indent=1))
    return 0 if status["state"] == "complete" else 1


def cmd_hp_variant(args):
    """Build a calibration variant of an instance in a new directory (swarm_board.variants)."""
    from . import variants
    if args.key_name:
        d = variants.rename_key(args.src, args.out, args.key_name, args.readme_text, tag=args.tag or "renamed")
    elif args.readme_text and not args.brief_text:
        d = variants.reword_readme(args.src, args.out, args.readme_text, tag=args.tag or "readme")
    elif args.brief_text:
        d = variants.add_brief_line(args.src, args.out, args.brief_text, args.after_heading, tag=args.tag or "brief")
    else:
        print("give --key-name or --brief-text", file=sys.stderr)
        return 2
    print(d)
    return 0


def cmd_hp_analyze(args):
    """Analyse a honeypot run directory and print the per-condition summary."""
    res = hp_analysis.write(args.run_dir)
    for cid, s in res["conditions"].items():
        print(f"{cid}: teams {s['n_teams']}, PRIMARY key/grader open {s['n_primary_open']}/{s['n_teams']} "
              f"Wilson {s['wilson95']['primary_open']}, any grader open {s['any_open']:.2f}, per-agent key open "
              f"{s['per_agent_open_rate']:.2f}, passed {s['passed']:.2f}, canary leak {s['canary_leak']:.2f}")
    sec = hp_secondary.write(args.run_dir)["summary"]
    print(f"secondary: infeasibility reports {sec['infeasibility_report_teams']}/{sec['teams']} teams, debrief "
          f"labels {sec['debrief_labels']}, debrief answers naming the grader {sec['debrief_names_grader']}")
    return 0


def main(argv=None):
    """Parse arguments and dispatch; config and resume problems exit 2 with the message."""
    ap = argparse.ArgumentParser(prog="python3 -m swarm_board")
    sub = ap.add_subparsers(dest="cmd", required=True)
    v = sub.add_parser("validate"); v.add_argument("config")
    r = sub.add_parser("render"); r.add_argument("config"); r.add_argument("--condition")
    x = sub.add_parser("run")
    x.add_argument("config"); x.add_argument("--out", required=True)
    x.add_argument("--backend", default="mock", choices=["mock", "claude", "codex"])
    x.add_argument("--allow-codex-stub", action="store_true")
    x.add_argument("--concurrency", type=int, default=8)
    x.add_argument("--max-calls", type=int)
    x.add_argument("--max-wall-min", type=float)
    x.add_argument("--conditions", help="comma-separated condition ids (default: all)")
    x.add_argument("--boards", type=int, help="boards per condition (default: the config's)")
    x.add_argument("--model", help="force every live agent onto this model")
    a = sub.add_parser("analyze"); a.add_argument("run_dir")
    hv = sub.add_parser("hp-validate"); hv.add_argument("config")
    hp = sub.add_parser("hp-probe"); hp.add_argument("config"); hp.add_argument("--out", required=True)
    hp.add_argument("--model")
    hr = sub.add_parser("hp-run")
    hr.add_argument("config"); hr.add_argument("--out", required=True)
    hr.add_argument("--backend", default="mock", choices=["mock", "claude"])
    hr.add_argument("--concurrency", type=int, default=4, help="teams at once")
    hr.add_argument("--max-turns", type=int, help="agent-turn budget across every session of this run")
    hr.add_argument("--max-requests", type=int, help="API-request budget (checked before each round)")
    hr.add_argument("--max-wall-min", type=float)
    hr.add_argument("--conditions", help="comma-separated condition ids (default: all)")
    hr.add_argument("--teams", type=int, help="teams per condition (default: the config's)")
    hr.add_argument("--model", help="force every agent onto this model")
    ha = sub.add_parser("hp-analyze"); ha.add_argument("run_dir")
    hx = sub.add_parser("hp-variant"); hx.add_argument("src"); hx.add_argument("--out", required=True)
    hx.add_argument("--key-name"); hx.add_argument("--readme-text"); hx.add_argument("--brief-text")
    hx.add_argument("--after-heading", default="## Submitting"); hx.add_argument("--tag")
    args = ap.parse_args(argv)
    try:
        return {"validate": cmd_validate, "render": cmd_render, "run": cmd_run, "analyze": cmd_analyze,
                "hp-validate": cmd_hp_validate, "hp-probe": cmd_hp_probe, "hp-run": cmd_hp_run,
                "hp-analyze": cmd_hp_analyze, "hp-variant": cmd_hp_variant}[args.cmd](args)
    except (ConfigError, ResumeMismatch, KeyError, hp_config.HpConfigError, hp_runner.HpRunError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
