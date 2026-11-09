"""Figure 1: experiment 1 (the honeypot), key-open rate per cell with Wilson 95% intervals, and the escalation, grader
README and debrief shares. Reads the experiment's result files read-only and writes figures/fig1.csv (every plotted
number with its source) and figures/fig1.png. The description is figures/fig1.md.

Sources (swarm-board, branch honeypot):
  confirmatory   results/hp-confirm/run/analysis.json and secondary.json (preregistered, prereg/confirm.md)
  calibration    results/calib-levers/run{1,2,3}/analysis.json; the Haiku baseline results/hp-smoke-3 has no
                 analysis.json on disk, so its team is recomputed with swarm_board.hp_analysis.team_outcome (the same
                 code), and checked against Codex's recount (<inbox>/hp-verify/result.json, per_lever)
  escalation     swarm_board.hp_secondary.infeasibility_reports, the preregistered rule, applied to every team; for
                 calibration this is after the fact (the rule was written for the confirmatory batch)

Usage: python3 figures/fig1.py   (from the paper repository root)
"""
import csv
import json
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

SB = Path.home() / "projects" / "swarm-board"
sys.path.insert(0, str(SB))
from swarm_board.hp_analysis import team_outcome, wilson          # noqa: E402
from swarm_board.hp_secondary import infeasibility_reports        # noqa: E402

OUT = Path(__file__).resolve().parent
R = SB / "results"
CONFIRM, CALIB = "#2a78d6", "#eb6834"      # dataviz reference palette slots 1 and 2 (validated, light surface)
# Calibration cells in the order the levers were tried; each maps condition ids to a label.
CELLS = [("Baseline (Haiku)", ["silent_impossible_phigh"]), ("Model: Opus 5.5", ["l1_opus"]),
         ("Model: Sonnet 5.5", ["l1_sonnet"]), ("Key renamed", ["l2_refplan"]), ("Scripted leak", ["l3_insider"]),
         ("Credit to submitter", ["l4_credit"]), ("No honest exit", ["p5_noexit"]),
         ("No exit + scripted leak", ["p6_noexit_insider"]), ("No exit + renamed + credit", ["p7_noexit_refplan_credit"]),
         ("README names script", ["p8_gradehint"]), ("No exit + README", ["p9_noexit_gradehint"])]


def calibration_teams():
    """[(team outcome dict, team dir, source)] for the 13 calibration teams."""
    out = []
    base = R / "hp-smoke-3" / "teams" / "silent_impossible_phigh-t00"
    out.append((team_outcome(base)[0], base, "swarm-board/results/hp-smoke-3 (team_outcome; = hp-verify recount)"))
    for run in ("run1", "run2", "run3"):
        a = json.loads((R / "calib-levers" / run / "analysis.json").read_text())
        for t in a["teams"]:
            out.append((t, R / "calib-levers" / run / "teams" / t["team"],
                        f"swarm-board/results/calib-levers/{run}/analysis.json"))
    return out


def row(panel, label, kind, k, n, unit, source):
    lo, hi = wilson(k, n)
    return {"panel": panel, "label": label, "kind": kind, "k": k, "n": n, "unit": unit, "share": round(k / n, 4),
            "wilson95_lo": round(lo, 4), "wilson95_hi": round(hi, 4), "source": source}


def main():
    rows = []
    conf = json.loads((R / "hp-confirm" / "run" / "analysis.json").read_text())
    sec = json.loads((R / "hp-confirm" / "run" / "secondary.json").read_text())
    ct = conf["teams"]
    csrc = "swarm-board/results/hp-confirm/run/analysis.json"
    rows.append(row("A", "Confirmatory (Haiku, no exit, 12 seeds)", "confirmatory",
                    sum(t["primary_open"] for t in ct), len(ct), "teams", csrc))
    cal = calibration_teams()
    assert len(cal) == 13, len(cal)
    for label, conds in CELLS:
        ts = [(t, src) for t, _, src in cal if t["condition"] in conds]
        rows.append(row("A", label, "calibration", sum(t["primary_open"] for t, _ in ts), len(ts), "teams",
                        ts[0][1]))
    rows.append(row("A", "Calibration pooled (13 teams)", "calibration",
                    sum(t["primary_open"] for t, _, _ in cal), 13, "teams", "calibration rows above"))
    # Panel B: shares other than the key
    rows.append(row("B", "Read only grader/README", "confirmatory", sum(t["any_open"] for t in ct), len(ct), "teams",
                    csrc))
    rows.append(row("B", "Read only grader/README", "calibration", sum(t["any_open"] for t, _, _ in cal), 13, "teams",
                    "calibration analysis files above"))
    rows.append(row("B", "Escalation drafted", "confirmatory",
                    sec["summary"]["infeasibility_report_teams"], len(ct), "teams",
                    "swarm-board/results/hp-confirm/run/secondary.json"))
    rows.append(row("B", "Escalation drafted", "calibration",
                    sum(bool(infeasibility_reports(d)[1]) for _, d, _ in cal), 13, "teams",
                    "hp_secondary.infeasibility_reports on the 13 calibration teams (after the fact)"))
    labels = sec["summary"]["debrief_labels"]
    nd = sec["summary"]["debrief_answers"]
    for lab, name in (("TEST", "Debrief: TEST"), ("UNSURE", "Debrief: UNSURE"),
                      ("REAL", "Debrief: REAL")):
        rows.append(row("B", name, "confirmatory", labels[lab], nd, "agents",
                        "swarm-board/results/hp-confirm/run/secondary.json"))
    with open(OUT / "fig1.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    draw(rows)


def draw(rows):
    """Two stacked panels sharing one label margin; shares on a 0 to 1 axis; every interval drawn; k/n at the right."""
    plt.rcParams.update({"font.size": 8, "axes.edgecolor": "#8a8984", "axes.labelcolor": "#0b0b0b",
                         "xtick.color": "#52514e", "ytick.color": "#0b0b0b", "font.family": "DejaVu Sans"})
    na, nb = (sum(r["panel"] == p for r in rows) for p in ("A", "B"))
    fig, (ax, bx) = plt.subplots(2, 1, figsize=(6.4, 6.6), gridspec_kw={"height_ratios": [na, nb], "hspace": 0.42})
    for axis, panel, title in ((ax, "A", "A. Teams that opened the answer key or grade.py"),
                               (bx, "B", "B. Other behaviour")):
        rs = [r for r in rows if r["panel"] == panel]
        ys = list(range(len(rs)))[::-1]
        for y, r in zip(ys, rs):
            c = CONFIRM if r["kind"] == "confirmatory" else CALIB
            axis.plot([r["wilson95_lo"], r["wilson95_hi"]], [y, y], color=c, lw=2, solid_capstyle="round")
            axis.plot([r["share"]], [y], "o" if r["kind"] == "confirmatory" else "s", color=c, ms=6,
                      markeredgecolor="#fcfcfb", markeredgewidth=1.2, clip_on=False, zorder=3)
            axis.text(1.04, y, f"{r['k']}/{r['n']} {r['unit']}", va="center", fontsize=7, color="#52514e",
                      transform=axis.get_yaxis_transform())
        axis.set_yticks(ys, [r["label"] + ("" if panel == "A" else
                                           (" (confirmatory)" if r["kind"] == "confirmatory" else " (calibration)"))
                             for r in rs])
        axis.set_xlim(-0.015, 1)
        axis.set_ylim(-0.6, len(rs) - 0.4)
        axis.set_xticks([0, 0.25, 0.5, 0.75, 1], ["0", "0.25", "0.5", "0.75", "1"])
        axis.grid(axis="x", color="#e4e3df", lw=0.6)
        axis.set_axisbelow(True)
        for side in ("top", "right"):
            axis.spines[side].set_visible(False)
        axis.set_title(title, loc="left", fontsize=8.5, fontweight="bold")
    ax.axhline(na - 1.5, color="#c9c8c2", lw=0.6)          # below the confirmatory row
    ax.axhline(0.5, color="#c9c8c2", lw=0.6)               # above the pooled calibration row
    bx.set_xlabel("share, with Wilson 95% interval")
    h1 = plt.Line2D([], [], color=CONFIRM, marker="o", lw=2, label="confirmatory (preregistered, 12 teams)")
    h2 = plt.Line2D([], [], color=CALIB, marker="s", lw=2, label="calibration (exploratory, 13 teams, not data)")
    fig.legend(handles=[h1, h2], loc="lower center", ncol=2, frameon=False, fontsize=7.5, bbox_to_anchor=(0.55, 0.0))
    fig.subplots_adjust(left=0.42, right=0.86, top=0.95, bottom=0.1)
    fig.savefig(OUT / "fig1.png", dpi=220, facecolor="#fcfcfb")


if __name__ == "__main__":
    main()
