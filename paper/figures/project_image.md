# Project image: Weak Commissar, Strong Agent

**What it shows.** A 1600 x 900 PNG (`figures/project_image.png`), a teaser figure for the Apart project-image field
and the public repository. Under the title and the paper's question, one takeaway line states the result: only the
principal's own voice passed its preregistered test, and no commissar arrangement did. Panel (a), the left third, is a schematic of the main design: a small local model, Qwen3.5-4B, acts as the commissar,
loyal to the principal, and rewrites the task before a neutral agent, Claude Haiku 5.5, reads it. The agent then runs
errands for the principal and for a teammate. The right two thirds plot each arrangement's change in the gap between
effort on the principal's errand and effort on a teammate's (T4 progress, principal minus teammate) against its
reference. The bar is the mean, paired by world and principal name with worlds weighted equally, and the line is its
95 percent t interval over worlds. The second line of each label gives the number of worlds behind the gap. Colour
carries the contrast: the principal's own voice in one deep blue accent, every commissar arrangement in one muted grey,
and in (a) only the principal's errand is tinted with the accent.

**The five bars, top to bottom.** All values are read from the result files by the script below, never typed in.

1. Principal's own voice, no commissar (A1W): `a1w-vs-a0.json` `gap_change`, against the A0 run of record. It is the
   only bar marked significant, with `holm_three.gap_change` (Holm p 0.023, its preregistered test).
2. Commissar posts on chat (A1): `a1-vs-a0.json` `gap_change`, against the A0 run of record (16 cells, 5 worlds).
3. Commissar rewrites, untrained (R5v22): `r5v22-confirm.json` `primary_and_secondaries.gap_change`, against its own
   fresh A0 rerun. Its interval just excludes zero (lower end +0.005), but its preregistered exact sign-flip test does
   not (p 0.125, Holm 0.25 as registered), so it is not marked; the footnote in the image says so.
4. Fine-tuned commissar, round 1 (R5ft): `r5ft-confirm.json` `primary_and_secondaries.gap_change`, against its own
   fresh A0 rerun.
5. Fine-tuned commissar, round 2 (R5ft2x): `r5ft2x-confirm.json` `primary_and_secondaries.gap_change`, against its
   own fresh A0 rerun. **R5ft2x is exploratory**: R5ft2's frozen protocol, run after that test's 01:40 launch window
   (`prereg/R5ft2x_exploratory_note.md`), and excluded from every Holm family. It is drawn in a lighter grey, hatched. The
   script checks its mean and interval against the dispatch record `<inbox>/r5ft2x/result.json` when that
   file exists.

All sources are in the operae worktree `<local>/Desktop/research/loyalty-evals/_commissar/operae`, directory
`experiments/commissar/`, branch `commissar`, read-only. The references differ: A1W and A1 against the A0 run of
record, the three rewriting arms against fresh A0 reruns made in their own sessions, as in Figure 2.

**Data.** `figures/project_image.csv`: label, mean, lo, hi, source file and key, worlds, status, Holm p where one is
marked.

**Regenerate.** From the paper repository root (`<local>/projects/commissar-paper`), with Python 3 and matplotlib:

```bash
awk '/^~~~python$/{f=1;next} /^~~~$/{f=0} f' figures/project_image.md | python3 -
```

That runs the script below, which is the only copy of it, and rewrites `figures/project_image.png` and
`figures/project_image.csv`. It is deterministic given the result files.

~~~python
"""Project image: schematic (left third) and the gap change of five arrangements (right two thirds), 1600 x 900 PNG.

Reads operae branch `commissar` result files read-only; writes figures/project_image.png and figures/project_image.csv
under the current directory, which must be the paper repository root.
"""
import csv
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib import patheffects  # noqa: E402
from matplotlib.patches import FancyBboxPatch  # noqa: E402

EXP = Path.home() / "Desktop/research/loyalty-evals/_commissar/operae/experiments/commissar"
OUT = Path.cwd() / "figures"
DISPATCH_R5FT2X = Path("<inbox>/r5ft2x/result.json")
# Three colours: ink, one deep blue accent for the principal's own voice, one muted grey for every commissar arm.
INK, MUTED = "#1a1a1a", "#5f5f5c"
ACCENT, ACCENT_TINT = "#1f4e8c", "#e6edf6"
GREY, GREY_LIGHT, GRID, LINE = "#9b9b97", "#d6d6d3", "#efefec", "#b5b5b1"
TAKEAWAY = "Only the principal's own voice passed its preregistered test; no commissar arrangement did."


def gap(name, key_path):
    """The gap_change dict of one result file, reached by its key path."""
    d = json.loads((EXP / name).read_text())
    for k in key_path:
        d = d[k]
    return d["gap_change"]


# (label, worlds note filled in later, source file, key path, status, Holm p key or None), top to bottom.
ARMS = [("Principal's own voice, no commissar (A1W)", "a1w-vs-a0.json", [], "preregistered", "holm_three"),
        ("Commissar posts on chat (A1)", "a1-vs-a0.json", [], "preregistered", None),
        ("Commissar rewrites, untrained (R5v22)", "r5v22-confirm.json", ["primary_and_secondaries"],
         "preregistered", None),
        ("Fine-tuned commissar, round 1 (R5ft)", "r5ft-confirm.json", ["primary_and_secondaries"],
         "preregistered", None),
        ("Fine-tuned commissar, round 2 (R5ft2x)", "r5ft2x-confirm.json", ["primary_and_secondaries"],
         "exploratory", None)]


def collect():
    """One row per bar, every number read from its file; R5ft2x cross-checked against its dispatch record."""
    rows = []
    for label, name, path, status, holm in ARMS:
        g = gap(name, path)
        holm_p = json.loads((EXP / name).read_text())[holm]["gap_change"] if holm else None
        rows.append({"label": label, "mean": g["mean"], "lo": g["ci95"][0], "hi": g["ci95"][1],
                     "source": f"experiments/commissar/{name} " + ".".join(path + ["gap_change"]),
                     "worlds": g["worlds"], "status": status, "holm_p": holm_p})
    if DISPATCH_R5FT2X.exists():
        rec = json.loads(DISPATCH_R5FT2X.read_text())["answer"]["gap_change_primary"]
        last = rows[-1]
        assert abs(rec["mean"] - last["mean"]) < 1e-4, "R5ft2x mean differs from its dispatch record"
        assert all(abs(a - b) < 1e-4 for a, b in zip(rec["ci95"], (last["lo"], last["hi"]))), "R5ft2x CI differs"
    return rows


def num(x):
    """Signed, two decimals; three below 0.05, so +0.025 and +0.005 print as the paper gives them."""
    return f"{x:+.3f}" if 0 < abs(x) < 0.05 else f"{x:+.2f}"


def box(ax, x, y, w, h, text, face, edge, size, weight="normal"):
    """A rounded box centred on (x, y) in axes coordinates, with centred text and a 1 px border."""
    ax.add_patch(FancyBboxPatch((x - w / 2, y - h / 2), w, h, boxstyle="round,pad=0.012,rounding_size=0.02",
                                facecolor=face, edgecolor=edge, linewidth=1.0, transform=ax.transAxes))
    ax.text(x, y, text, ha="center", va="center", fontsize=size, color=INK, weight=weight, transform=ax.transAxes,
            linespacing=1.35)


def arrow(ax, start, end, color=MUTED):
    """A plain arrow between two points in axes coordinates."""
    ax.annotate("", xy=end, xytext=start, xycoords="axes fraction",
                arrowprops={"arrowstyle": "-|>", "color": color, "lw": 1.2, "mutation_scale": 16})


def schematic(ax):
    """Left third: commissar rewrites the task, the neutral agent runs both errands."""
    ax.axis("off")
    box(ax, 0.5, 0.86, 0.62, 0.15, "Commissar\nQwen3.5-4B, local,\nloyal to the principal", "white", LINE, 12)
    arrow(ax, (0.5, 0.775), (0.5, 0.635))
    ax.text(0.53, 0.705, "rewrites the task", ha="left", va="center", fontsize=12, color=MUTED, style="italic",
            transform=ax.transAxes)
    box(ax, 0.5, 0.51, 0.86, 0.22, "Neutral agent\nClaude Haiku 5.5", "#f6f6f4", LINE, 15, weight="bold")
    arrow(ax, (0.36, 0.39), (0.25, 0.25))
    arrow(ax, (0.64, 0.39), (0.75, 0.25))
    box(ax, 0.25, 0.18, 0.40, 0.11, "errand for\nthe principal", ACCENT_TINT, ACCENT, 12)
    box(ax, 0.75, 0.18, 0.40, 0.11, "errand for\na teammate", "white", LINE, 12)
    ax.text(0.5, 0.06, "Measured: effort on the principal's errand\nminus effort on the teammate's",
            ha="center", va="center", fontsize=11, color=MUTED, transform=ax.transAxes, linespacing=1.35)


def chart(ax, rows):
    """Right two thirds: horizontal bars with 95% t intervals; the principal's own voice (the one row with a Holm p)
    in the accent, every commissar arm in grey, the exploratory arm lighter and hatched."""
    y = list(range(len(rows)))[::-1]
    for yi, r in zip(y, rows):
        exploratory, accent = r["status"] == "exploratory", r["holm_p"] is not None
        color = ACCENT if accent else GREY_LIGHT if exploratory else GREY
        ax.barh(yi, r["mean"], height=0.54, color=color, edgecolor=GREY if exploratory else color,
                linewidth=0.8 if exploratory else 0, hatch="////" if exploratory else None, zorder=2)
        halo = [patheffects.withStroke(linewidth=3, foreground="white")]   # keeps the interval legible on a dark bar
        ax.plot([r["lo"], r["hi"]], [yi, yi], color=INK, lw=1.1, zorder=3, solid_capstyle="butt", path_effects=halo)
        for end in (r["lo"], r["hi"]):
            ax.plot([end, end], [yi - 0.09, yi + 0.09], color=INK, lw=1.1, zorder=3, path_effects=halo)
        text = f"{num(r['mean'])}  [{num(r['lo'])}, {num(r['hi'])}]"
        ax.text(max(r["hi"], 0) + 0.03, yi + 0.07, text, va="center", ha="left", fontsize=12.5, color=INK)
        if r["holm_p"] is not None:
            ax.text(max(r["hi"], 0) + 0.03, yi - 0.24, f"Holm p {r['holm_p']:.3f}", va="center", ha="left",
                    fontsize=12, color=ACCENT, weight="bold")
    labels = [f"{r['label']}\n{r['worlds']} worlds" + (", exploratory" if r["status"] == "exploratory" else "")
              for r in rows]
    ax.set_yticks(y)
    ax.set_yticklabels(labels, fontsize=12.5, color=INK, linespacing=1.4)
    for tick, r in zip(ax.get_yticklabels(), rows):
        tick.set_color(MUTED if r["status"] == "exploratory" else INK)
    ax.axvline(0, color=INK, lw=0.9, zorder=1)
    ax.set_xlim(-0.75, 1.2)
    ax.set_ylim(-0.6, len(rows) - 0.4)
    ax.xaxis.grid(True, color=GRID, lw=0.8, zorder=0)
    ax.set_axisbelow(True)
    ax.tick_params(axis="x", labelsize=12, colors=INK, width=0.8)
    ax.tick_params(axis="y", length=0, pad=10)
    for side in ("top", "right", "left"):
        ax.spines[side].set_visible(False)
    ax.spines["bottom"].set_linewidth(0.8)
    ax.set_xlabel("Gap change vs reference (T4 progress, principal minus teammate)", fontsize=12.5, color=INK)



def main():
    rows = collect()
    with open(OUT / "project_image.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["label", "mean", "lo", "hi", "source", "worlds", "status", "holm_p"])
        w.writeheader()
        for r in rows:
            w.writerow({**r, "mean": round(r["mean"], 4), "lo": round(r["lo"], 4), "hi": round(r["hi"], 4),
                        "holm_p": "" if r["holm_p"] is None else round(r["holm_p"], 4)})
    fig = plt.figure(figsize=(16, 9), dpi=100, facecolor="white")
    fig.text(0.035, 0.948, "Weak Commissar, Strong Agent", fontsize=32, weight="bold", color=INK, va="center",
             family="STIXGeneral")
    fig.text(0.035, 0.892, "Can a small loyal model raise an agent's loyalty to its principal?", fontsize=15,
             color=MUTED, va="center")
    fig.text(0.035, 0.845, TAKEAWAY, fontsize=15, color=INK, va="center", weight="bold")
    fig.text(0.035, 0.765, "(a)", fontsize=15, color=INK, va="center", weight="bold")
    fig.text(0.062, 0.765, "Setup", fontsize=15, color=INK, va="center")
    fig.text(0.322, 0.765, "(b)", fontsize=15, color=INK, va="center", weight="bold")
    fig.text(0.349, 0.765, "Change in the principal-minus-teammate effort gap (95% CI)", fontsize=15, color=INK,
             va="center")
    schematic(fig.add_axes([0.02, 0.10, 0.28, 0.63]))
    chart(fig.add_axes([0.555, 0.18, 0.345, 0.55]), rows)
    fig.text(0.035, 0.045, "Bars: mean change, paired by world and principal name, worlds weighted equally; lines: "
             "95% t interval over worlds. A1W and A1 vs the A0 run of record; rewriting arms vs fresh A0 reruns.\n"
             "R5v22's interval excludes zero but its preregistered exact sign-flip test does not (p 0.125). R5ft2x ran "
             "after its launch window: exploratory, outside every Holm family.", fontsize=10.5, color=MUTED,
             va="center", linespacing=1.5)
    fig.savefig(OUT / "project_image.png", dpi=100, facecolor="white", metadata={"Software": None})
    for r in rows:
        print(f"{r['label']}: {num(r['mean'])} [{num(r['lo'])}, {num(r['hi'])}], {r['worlds']} worlds, {r['source']}")


if __name__ == "__main__":
    main()
~~~
