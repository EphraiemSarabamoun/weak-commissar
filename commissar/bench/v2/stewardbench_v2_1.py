"""StewardBench v2.1: the v2 benchmark scored under the corrected v2.1 instructions (entry point).

v2.1 changes only the steward's system prompt: steward_prompt_v2_1.txt is v2's
prompt plus the two sentences the v3 training data teaches and v2 had dropped
("Back any teammate who raises a real problem ... even if it costs time." and
"Otherwise stay quiet."). Items, judge rubric, metrics and judge validation are
v2's, unchanged. This module reuses stewardbench_v2 as it is (so v2 stays frozen and
re-runnable under PINS_v2.json) and points it at the v2.1 prompt, its own pin file
(PINS_v2_1.json) and its own results folder (results_v2_1/).

Commands: pin | score --model M | export-codex [--out PATH]
Score the fine-tune (the one-command path):
  python3 bench/v2/stewardbench_v2_1.py score --model steward-lora
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import spec_v2  # noqa: E402
import stewardbench_v2 as v2  # noqa: E402

PROMPT_FILE = spec_v2.V2_DIR / "steward_prompt_v2_1.txt"   # copy of commissar_prompt_v2_1.txt
RESULTS_DIR = spec_v2.V2_DIR / "results_v2_1"
PINS_FILE = spec_v2.V2_DIR / "PINS_v2_1.json"
LABEL = "v2/steward_prompt_v2_1.txt (commissar_prompt_v2_1)"
# Pinned inputs v2.1 must share byte for byte with the v2 pin: same items, judge, metrics.
SHARED_WITH_V2 = ("items_v2.jsonl", "validation_v2.jsonl", "spec_v2.py", "judge_v2.py", "metrics_v2.py")


def use_v2_1() -> None:
    """Point the v2 module's settings at the v2.1 prompt, pin file and results folder."""
    spec_v2.STEWARD_PROMPT_FILE = PROMPT_FILE
    spec_v2.RESULTS_DIR = RESULTS_DIR
    spec_v2.PINS_FILE = PINS_FILE
    v2.V2_FILES = tuple("steward_prompt_v2_1.txt" if f == "steward_prompt_v2.txt" else f for f in v2.V2_FILES) \
        + ("stewardbench_v2_1.py",)


def check_same_as_v2() -> None:
    """Refuse unless items, judge and metrics hash exactly as in the v2 pin."""
    pinned_v2 = json.loads((spec_v2.V2_DIR / "PINS_v2.json").read_text())
    now = v2.current_pins()
    diff = [f for f in SHARED_WITH_V2 if pinned_v2["v2_files"].get(f) != now["v2_files"].get(f)]
    diff += [k for k in ("judge_template_sha256", "judge_model", "primary_metric") if pinned_v2[k] != now[k]]
    if diff:
        sys.exit(f"v2.1 must reuse v2's pinned items, judge and metrics; these differ: {diff}")


def relabel(model: str) -> None:
    """stewardbench_v2 labels its outputs as v2; mark the v2.1 outputs as v2.1."""
    out = RESULTS_DIR / model
    s = json.loads((out / "scores.json").read_text())
    s.update(system_prompt=LABEL, benchmark="StewardBench v2 items under the v2.1 system prompt")
    (out / "scores.json").write_text(json.dumps(s, indent=1))
    table = (out / "table.md").read_text().replace("(v2, principal-first)", "(v2.1 prompt, principal-first)", 1)
    (out / "table.md").write_text(table)


def main() -> int:
    use_v2_1()
    check_same_as_v2()
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd not in ("pin", "score", "export-codex"):
        sys.exit(__doc__)
    if cmd == "export-codex" and "--out" not in sys.argv:
        sys.argv += ["--out", str(RESULTS_DIR / "codex_sample.jsonl")]
    rc = v2.main()
    if cmd == "score" and rc == 0:
        relabel(sys.argv[sys.argv.index("--model") + 1])
    return rc


if __name__ == "__main__":
    sys.exit(main())
