"""R5v22's rewrites (prereg/R5v22.md): the exact generation and freeze that produced attempts.jsonl and frozen.jsonl.

generate  every cell through eval_rewrites.generate: steward-base, steward/prompts/commissar_prompt_v2_2.txt,
          the current validator (gen_rewrite.validate: W1-W12 + the pinned W13 judge), cap 10, 4 concurrent requests;
          resumes from attempts.jsonl.
freeze    frozen.jsonl once (never overwritten), R5's row format, a cell with no accepted attempt frozen as null.

Run from experiments/commissar with castra 8457977 on PYTHONPATH (Python 3.12):
  python3.12 steward/r5v22/generate_and_freeze.py generate
  python3.12 steward/r5v22/generate_and_freeze.py freeze
"""
import hashlib
import json
import pathlib
import sys

EXP = pathlib.Path(__file__).resolve().parents[2]
sys.path[:0] = [str(EXP), str(EXP / "steward")]
import compile as K  # noqa: E402
import eval_rewrites as ER  # noqa: E402

DIR = EXP / "steward" / "r5v22"
URL, MODEL, PROMPT = "http://127.0.0.1:8417/v1", "steward-base", EXP / "steward/prompts/commissar_prompt_v2_2.txt"


def main(cmd):
    bases = K.released_bases(EXP / "data" / "pilot.jsonl")
    if cmd == "generate":
        n = ER.generate(URL, MODEL, bases, DIR / "attempts.jsonl", max_attempts=10, workers=4,
                        system_prompt_path=PROMPT, validator_name="current")
        print("server calls", n)
    elif cmd == "freeze":
        out = DIR / "frozen.jsonl"
        if out.exists():
            raise SystemExit(f"{out} exists: never overwritten")
        rows = ER.freeze(bases, DIR / "attempts.jsonl", MODEL, URL, 10, PROMPT)
        out.write_text("".join(json.dumps(r, sort_keys=True, ensure_ascii=False) + "\n" for r in rows))
        print("covered", sum(1 for r in rows if r["rewrite"]), "of", len(rows),
              "sha256", hashlib.sha256(out.read_bytes()).hexdigest())
    else:
        raise SystemExit(__doc__)


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "")
