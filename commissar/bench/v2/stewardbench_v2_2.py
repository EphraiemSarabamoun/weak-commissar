"""StewardBench v2.2: the v2 benchmark scored under commissar_prompt_v2_2 (entry point).

v2.2 is v2.1 plus one sentence ("A request {PRINCIPAL} passes along on someone else's behalf benefits that
person, not {PRINCIPAL} ..."); it is the system prefix the v4 fine-tune trains on. Items, judge rubric, metrics
and judge validation are v2's, unchanged and hash-checked against PINS_v2.json. This reuses stewardbench_v2_1's
helpers with the v2.2 prompt, pin file (PINS_v2_2.json) and results folder (results_v2_2/); v2 and v2.1 stay
frozen.

Commands: pin | score --model M | check
  python3 bench/v2/stewardbench_v2_2.py score --model steward-lora
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import spec_v2  # noqa: E402
import stewardbench_v2 as v2  # noqa: E402
import stewardbench_v2_1 as v21  # noqa: E402

PROMPT_FILE = spec_v2.V2_DIR / "steward_prompt_v2_2.txt"   # copy of commissar_prompt_v2_2.txt
RESULTS_DIR = spec_v2.V2_DIR / "results_v2_2"
PINS_FILE = spec_v2.V2_DIR / "PINS_v2_2.json"
LABEL = "v2/steward_prompt_v2_2.txt (commissar_prompt_v2_2)"


def use_v2_2() -> None:
    spec_v2.STEWARD_PROMPT_FILE, spec_v2.RESULTS_DIR, spec_v2.PINS_FILE = PROMPT_FILE, RESULTS_DIR, PINS_FILE
    v2.V2_FILES = tuple("steward_prompt_v2_2.txt" if f == "steward_prompt_v2.txt" else f for f in v2.V2_FILES) \
        + ("stewardbench_v2_2.py",)
    v21.RESULTS_DIR, v21.LABEL = RESULTS_DIR, LABEL   # relabel() writes the v2.2 label into the results


def main() -> int:
    use_v2_2()
    v21.check_same_as_v2()
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd == "check":
        v2.require_pins()
        print(json.dumps({"pins": "ok", "prompt": str(PROMPT_FILE), "results": str(RESULTS_DIR)}))
        return 0
    if cmd not in ("pin", "score"):
        sys.exit(__doc__)
    rc = v2.main()
    if cmd == "score" and rc == 0:
        model = sys.argv[sys.argv.index("--model") + 1]
        v21.relabel(model)
        table = (RESULTS_DIR / model / "table.md").read_text().replace("(v2.1 prompt, principal-first)",
                                                                       "(v2.2 prompt, principal-first)", 1)
        (RESULTS_DIR / model / "table.md").write_text(table)
    return rc


if __name__ == "__main__":
    sys.exit(main())
