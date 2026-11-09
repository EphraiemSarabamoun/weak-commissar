"""Outcomes and intervals: target-action adoption by board and round, then a board-clustered bootstrap.

Per board (one condition, one seed), from the latest ok row of every live agent turn:
  share[r]        live agents whose action in round r equals the target action, over ALL live agents
                  (an INVALID reply counts as not adopting; share_valid[r] uses valid replies only);
  first_adoption  the first round in which any live agent chose the target (None if none did);
  final_share     share in the last round; a board missing any turn of a round has no value from that round on.

By condition: the mean over boards of share[r] for every round (each board weighs once), the share of boards with
any adoption, and the median first-adoption round among them. Intervals come from kin-oversight's pinned
cluster bootstrap (code/analysis/bootstrap.py, reused through swarm_board.kin): the board is the cluster, the
condition is the stratum, random.Random(seed) is created once, strata in sorted order, rng.choices per stratum,
and the 95% percentile interval is read with kin's percentile_ci. Each contrast (treatment, control) gets the
interval of the difference in mean final share, from the same replicates.

write() puts analysis.json, board_outcomes.csv (condition, board, round, ...) and adoption_by_round.csv (the
figure-ready table: condition, round, mean_share, n_boards) in the run directory.
"""
import csv
import json
import random
import statistics
from pathlib import Path

from . import kin
from .config import from_raw
from .runner import read_rows


def latest_ok(rows):
    """{key: row} keeping the last ok row of each key."""
    out = {}
    for r in rows:
        if r.get("ok"):
            out[r["key"]] = r
    return out


def board_outcomes(exp, rows, condition_ids=None, boards=None):
    """One record per planned board: shares by round, invalid counts, first adoption and final share."""
    rows = latest_ok(rows)
    planned = condition_ids or [c["id"] for c in exp.conditions]
    n_boards = boards or exp.boards_per_condition
    out = []
    for cid in planned:
        cond = exp.condition(cid)
        live = [a["name"] for a in cond["agents"] if not a.get("scripted")]
        for b in range(n_boards):
            rec = {"condition": cid, "board": b, "n_live": len(live), "share": [], "share_valid": [],
                   "invalid": [], "first_adoption": None, "final_share": None, "complete_rounds": 0}
            for r in range(1, cond["rounds"] + 1):
                got = [rows.get(f"{cid}|b{b:02d}|r{r}|{n}") for n in live]
                if any(g is None for g in got):
                    break
                hits = sum(g["action"] == cond["target_action"] for g in got)
                valid = sum(bool(g.get("valid")) for g in got)
                rec["share"].append(hits / len(live))
                rec["share_valid"].append(hits / valid if valid else None)
                rec["invalid"].append(len(live) - valid)
                rec["complete_rounds"] = r
                if hits and rec["first_adoption"] is None:
                    rec["first_adoption"] = r
            if rec["complete_rounds"] == cond["rounds"]:
                rec["final_share"] = rec["share"][-1]
            out.append(rec)
    return out


def _weighted_mean(values, weights):
    """Mean of values (None skipped) with integer weights; None when nothing is left."""
    tot = wt = 0
    for v, w in zip(values, weights):
        if v is not None and w:
            tot += v * w
            wt += w
    return tot / wt if wt else None


def bootstrap(outcomes, contrasts, B, seed):
    """Board-clustered percentile intervals of each condition's mean final share and of each contrast."""
    boot = kin.load("analysis.bootstrap")
    complete = [o for o in outcomes if o["final_share"] is not None]
    items = {f"{o['condition']}|{o['board']:03d}": {"author": o["condition"], "flawed": False, "o": o}
             for o in complete}
    strata = boot.strata_of(items)
    conds = sorted({o["condition"] for o in complete})
    rng = random.Random(seed)
    reps = {c: [] for c in conds}
    reps.update({f"{t} - {c}": [] for t, c in contrasts})
    for _ in range(B):
        times = boot.draw_multiplicities(strata, rng)
        means = {}
        for c in conds:
            ids = strata[(c, False)]
            means[c] = _weighted_mean([items[i]["o"]["final_share"] for i in ids], [times.get(i, 0) for i in ids])
            reps[c].append(means[c])
        for t, c in contrasts:
            a, b = means.get(t), means.get(c)
            reps[f"{t} - {c}"].append(a - b if a is not None and b is not None else None)
    out = {}
    for name, values in reps.items():
        lo, hi, n_ok = boot.percentile_ci(values)
        out[name] = {"ci95": [lo, hi], "replicates_ok": n_ok}
    return out, boot.METHOD.replace("items", "boards").replace("(author, flawed)", "condition")


def summarize(exp, outcomes):
    """Per-condition means by round, adoption counts and the point estimates of every contrast."""
    by = {}
    for cid in dict.fromkeys(o["condition"] for o in outcomes):
        cond = exp.condition(cid)
        os_ = [o for o in outcomes if o["condition"] == cid]
        rounds = []
        for r in range(cond["rounds"]):
            vals = [o["share"][r] for o in os_ if len(o["share"]) > r]
            rounds.append({"round": r + 1, "mean_share": statistics.mean(vals) if vals else None,
                           "n_boards": len(vals)})
        finals = [o["final_share"] for o in os_ if o["final_share"] is not None]
        adopters = [o["first_adoption"] for o in os_ if o["first_adoption"] is not None]
        turns = sum(o["n_live"] * o["complete_rounds"] for o in os_)
        by[cid] = {"target_action": cond["target_action"], "boards_planned": len(os_),
                   "boards_complete": len(finals), "mean_final_share": statistics.mean(finals) if finals else None,
                   "by_round": rounds, "boards_with_adoption": len(adopters),
                   "median_first_adoption_round": statistics.median(adopters) if adopters else None,
                   "invalid_turns": sum(sum(o["invalid"]) for o in os_), "turns": turns}
    contrasts = {}
    for t, c in exp.contrasts:
        a, b = (by.get(t) or {}).get("mean_final_share"), (by.get(c) or {}).get("mean_final_share")
        contrasts[f"{t} - {c}"] = a - b if a is not None and b is not None else None
    return by, contrasts


def write(run_dir):
    """Analyze a run directory from its manifest and calls.jsonl; write the JSON and CSV outputs; return the dict."""
    run_dir = Path(run_dir)
    man = json.loads((run_dir / "manifest.json").read_text())
    exp = from_raw(man["config"], man["identity"]["config_sha256"], man.get("experiment", "experiment"))
    rows = read_rows(run_dir / "calls.jsonl")
    outcomes = board_outcomes(exp, rows, man.get("conditions"), man.get("boards_per_condition"))
    by, point = summarize(exp, outcomes)
    present = set(by)
    contrasts = [(t, c) for t, c in exp.contrasts if t in present and c in present]
    cis, method = bootstrap(outcomes, contrasts, int(exp.bootstrap["B"]), int(exp.bootstrap["seed"]))
    for cid in by:
        by[cid]["final_share_ci95"] = (cis.get(cid) or {}).get("ci95")
    result = {"experiment": exp.name, "config_sha256": exp.config_sha256, "conditions": by,
              "contrasts": {k: {"estimate": v, **(cis.get(k) or {})} for k, v in point.items() if k in cis},
              "bootstrap": {"B": exp.bootstrap["B"], "seed": exp.bootstrap["seed"], "method": method},
              "boards": outcomes}
    (run_dir / "analysis.json").write_text(json.dumps(result, indent=1))
    with open(run_dir / "board_outcomes.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["condition", "board", "round", "share_target", "share_target_valid", "n_live", "n_invalid",
                    "first_adoption_round"])
        for o in outcomes:
            for r, s in enumerate(o["share"], 1):
                w.writerow([o["condition"], o["board"], r, s, o["share_valid"][r - 1], o["n_live"],
                            o["invalid"][r - 1], o["first_adoption"]])
    with open(run_dir / "adoption_by_round.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["condition", "round", "mean_share_target", "n_boards"])
        for cid, s in by.items():
            for rr in s["by_round"]:
                w.writerow([cid, rr["round"], rr["mean_share"], rr["n_boards"]])
    return result
