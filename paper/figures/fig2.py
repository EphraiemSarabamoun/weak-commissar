"""Figure 2: experiment 2, every arrangement of the commissar (and the principal's own line, A1W) on operae v0.2:
panel A each arrangement's change in T4 progress on the principal's and the teammate's errand, panel B its change in
the gap (principal minus teammate), each against its reference, with 95 percent t intervals over worlds.

Reads the committed result files of operae branch `commissar` read-only and writes figures/fig2.csv (every plotted
number with its source) and figures/fig2.png. The description is figures/fig2.md.

Sources (operae worktree <local>/Desktop/research/loyalty-evals/_commissar/operae, experiments/commissar/):
  A1, A1L, A1E, A1W  <arm>-vs-a0.json: gap_change and primary.{principal,teammate}, paired with A0 on the arm's cells
                     (compare.py); preregistered arms
  R2, R3, R4         s-search.json arms[].vs_a0, paired with A0 on all 32 cells (search_analysis.py); the exploratory
                     search of prereg/S.md (its confirmation was not run, S.md D1)
  R5                 r5-confirm.json primary_and_secondaries, paired with the fresh A0 rerun on R5's 29 cells
                     (search_analysis.py confirm); the a priori primary of prereg/R5.md (gap over 13 pairs, 7 worlds)
  R5v22              r5v22-confirm.json primary_and_secondaries, paired with its own fresh A0 rerun on 23 cells; the
                     second preregistered rewrite test (prereg/R5v22.md; gap over 9 pairs, 6 worlds; verified by Codex
                     r5v22-verify: numbers reproduce)
The references differ (A0 of record against the A0 rerun for R5), which the caption states.

Usage: python3 figures/fig2.py   (from the paper repository root)
"""
import csv
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

EXP = Path.home() / "Desktop/research/loyalty-evals/_commissar/operae/experiments/commissar"
OUT = Path(__file__).resolve().parent
SRC = "operae commissar experiments/commissar/"
PRINCIPAL, TEAMMATE = "#2a78d6", "#eb6834"   # dataviz reference palette slots 1 and 2 (validated, light surface)
INK, MUTED, SURFACE = "#0b0b0b", "#52514e", "#fcfcfb"
# (arm, short description, status, reference, loader of the comparison dict with gap_change/principal/teammate,
#  source path) in plotting order. A-arms and R2-R4 are against A0 of record; R5 against its fresh A0 rerun.


def _json(name):
    return json.loads((EXP / name).read_text())


def _search(arm):
    b = next(x for x in _json("s-search.json")["arms"] if x["arm"] == arm)["vs_a0"]
    return {"gap_change": b["gap_change"], "principal": b["principal"], "teammate": b["teammate"], "cells": b["cells"]}


def _pair(name):
    c = _json(name)
    return {"gap_change": c["gap_change"], "principal": c["primary"]["principal"],
            "teammate": c["primary"]["teammate"], "cells": c["cells"]}


def _confirm(name):
    c = _json(name)["primary_and_secondaries"]
    return {"gap_change": c["gap_change"], "principal": c["principal"], "teammate": c["teammate"], "cells": c["cells"]}


ARMS = [("A1", "commissar posts, faithful", "preregistered", "A0", lambda: _pair("a1-vs-a0.json"), "a1-vs-a0.json"),
        ("A1L", "commissar posts, principal-first", "preregistered", "A0", lambda: _pair("a1l-vs-a0.json"), "a1l-vs-a0.json"),
        ("A1E", "principal endorses commissar", "preregistered", "A0", lambda: _pair("a1e-vs-a0.json"), "a1e-vs-a0.json"),
        ("A1W", "principal states wish, no commissar", "preregistered", "A0", lambda: _pair("a1w-vs-a0.json"), "a1w-vs-a0.json"),
        ("R2", "principal forwards commissar text", "exploratory", "A0", lambda: _search("forwarded"), "s-search.json arms[forwarded].vs_a0"),
        ("R3", "operator appoints commissar", "exploratory", "A0", lambda: _search("appointed"), "s-search.json arms[appointed].vs_a0"),
        ("R4", "commissar text as system policy", "exploratory", "A0", lambda: _search("policy"), "s-search.json arms[policy].vs_a0"),
        ("R5", "commissar rewrites the task", "preregistered primary", "A0 rerun", lambda: _confirm("r5-confirm.json"),
         "r5-confirm.json primary_and_secondaries"),
        ("R5v22", "rewrites, v2.2 and strict check", "preregistered", "its own A0 rerun",
         lambda: _confirm("r5v22-confirm.json"), "r5v22-confirm.json primary_and_secondaries (verified by Codex r5v22-verify)")]


def collect():
    """CSV rows: panel A (each arm's change on each beneficiary's errand) and panel B (each arm's gap change)."""
    rows = []
    for arm, desc, status, ref, load, src in ARMS:
        c = load()
        for panel, key, measure in (("A", "principal", "change, principal's errand"),
                                    ("A", "teammate", "change, teammate's errand"),
                                    ("B", "gap_change", "gap change (principal minus teammate)")):
            g = c[key]
            rows.append({"panel": panel, "arm": arm, "description": desc, "status": status, "reference": ref,
                         "measure": f"{measure} vs {ref}", "value": round(g["mean"], 4),
                         "ci95_lo": round(g["ci95"][0], 4), "ci95_hi": round(g["ci95"][1], 4),
                         "sign_flip_p": g.get("sign_flip_p"), "cells": c["cells"], "worlds": len(g["world_means"]),
                         "source": f"{SRC}{src} {key}"})
    return rows


def _style(ax):
    ax.set_facecolor(SURFACE)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    ax.spines["left"].set_color(MUTED)
    ax.spines["bottom"].set_color(MUTED)
    ax.tick_params(colors=MUTED, labelsize=9)
    ax.grid(axis="y", color="#e4e3df", linewidth=0.8)
    ax.set_axisbelow(True)
    ax.axhline(0, color=MUTED, linewidth=1)
    ax.axvspan(3.5, 6.5, color="#efeee9", zorder=0)        # the exploratory search


def draw(rows):
    arms = [a for a, *_ in ARMS]
    labels = [f"{a}\n{next(r['cells'] for r in rows if r['arm'] == a and r['panel'] == 'B')} cells" for a in arms]
    fig, (ax_a, ax_b) = plt.subplots(1, 2, figsize=(12.6, 4.6), gridspec_kw={"width_ratios": [1, 1]})
    fig.patch.set_facecolor(SURFACE)
    for ax in (ax_a, ax_b):
        _style(ax)
        ax.set_xticks(range(len(arms)))
        ax.set_xticklabels(labels, fontsize=8.5, color=INK)
        ax.set_xlim(-0.6, len(arms) - 0.4)
    for b, color, marker, dx in (("principal", PRINCIPAL, "o", -0.14), ("teammate", TEAMMATE, "s", 0.14)):
        pts = [r for r in rows if r["panel"] == "A" and f"{b}'s errand" in r["measure"]]
        xs = [arms.index(r["arm"]) + dx for r in pts]
        ax_a.errorbar(xs, [r["value"] for r in pts],
                      yerr=[[r["value"] - r["ci95_lo"] for r in pts], [r["ci95_hi"] - r["value"] for r in pts]],
                      fmt=marker, color=color, ecolor=color, elinewidth=1.5, capsize=0, markersize=6.5,
                      markeredgecolor=SURFACE, markeredgewidth=1.1, label=f"{b.capitalize()}'s errand")
    ax_a.set_ylabel("Change in T4 progress vs reference", fontsize=9.5, color=INK)
    ax_a.set_title("A. Effort on each errand", fontsize=10.5, color=INK, loc="left")
    ax_a.legend(frameon=False, fontsize=8.5, loc="lower left", ncol=2)
    ax_a.set_ylim(-0.75, 0.85)
    pb = [r for r in rows if r["panel"] == "B"]
    xs = [arms.index(r["arm"]) for r in pb]
    ax_b.errorbar(xs, [r["value"] for r in pb],
                  yerr=[[r["value"] - r["ci95_lo"] for r in pb], [r["ci95_hi"] - r["value"] for r in pb]],
                  fmt="D", color=INK, ecolor=INK, elinewidth=1.6, capsize=0, markersize=6,
                  markeredgecolor=SURFACE, markeredgewidth=1.2)
    for x, r in zip(xs, pb):
        ax_b.annotate(f"{r['value']:+.2f}", (x, r["value"]), xytext=(6, 0), textcoords="offset points",
                      va="center", fontsize=8, color=INK)
    ax_b.set_ylabel("Gap change vs reference", fontsize=9.5, color=INK)
    ax_b.set_title("B. Favouritism opened (principal minus teammate)", fontsize=10.5, color=INK, loc="left")
    ax_b.set_ylim(-0.75, 1.15)
    for ax in (ax_a, ax_b):
        ax.text(5, ax.get_ylim()[1] * 0.97, "exploratory search", ha="center", va="top", fontsize=8, color=MUTED)
    fig.tight_layout()
    fig.savefig(OUT / "fig2.png", dpi=200, facecolor=SURFACE)


def main():
    rows = collect()
    with open(OUT / "fig2.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    draw(rows)
    print(f"wrote {OUT / 'fig2.csv'} ({len(rows)} rows) and {OUT / 'fig2.png'}")


if __name__ == "__main__":
    main()
