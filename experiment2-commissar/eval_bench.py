"""StewardBench v2.1 for one commissar model, with its outputs redirected into this experiment's evals/ folder.

StewardBench (agent D's, <local>/projects/commissar/bench/v2, read-only from here) scores the steward's own judgement on 150
held-out situations with a pinned Sonnet judge. Its one-command path, `stewardbench_v2_1.py score --model M`, writes
into its own results_v2_1/M/. This wrapper runs exactly that code path (use_v2_1, the v2 pin check, cmd_score, the
v2.1 relabel) with RESULTS_DIR pointed at OUT instead, so the bench checkout is never written. A model the bench has
already scored is seeded from the bench's own replies and judgments: cmd_score caches by item and reply hash, so
those items cost no steward or judge call and the scores are recomputed by the bench's own metrics.

Run under the bench's interpreter (python3) with PYTHONDONTWRITEBYTECODE=1, so no bytecode lands in the bench:
  python3 eval_bench.py --bench <local>/projects/commissar/bench --model steward-lora --out evals/steward-lora/stewardbench
Prints one JSON line {scores_path, judge_calls_this_run, seeded}.

--system-prompt PATH scores the same v2 items under another steward prompt (an exploratory dev round, e.g. v2.2): it
replaces only the template the steward is given (spec_v2.STEWARD_PROMPT_FILE); items, judge, metrics and the pin
checks are untouched. Nothing is seeded from the bench in that case, because its replies were made under v2.1, and
scores.json records the prompt's path and sha256.
"""
import argparse
import hashlib
import json
import pathlib
import shutil
import sys


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--bench", required=True, help="the bench folder (holds v2/)")
    p.add_argument("--model", required=True)
    p.add_argument("--out", required=True, help="results root; the model's files go to OUT/<model>/")
    p.add_argument("--url", default=None)
    p.add_argument("--system-prompt", default=None, help="score under this steward prompt instead of v2.1")
    a = p.parse_args(argv)
    v2dir = pathlib.Path(a.bench).expanduser().resolve() / "v2"
    sys.path.insert(0, str(v2dir))
    import spec_v2
    import stewardbench_v2 as v2
    import stewardbench_v2_1 as v21
    v21.use_v2_1()
    v21.check_same_as_v2()
    out_root = pathlib.Path(a.out).resolve()
    mine = out_root / a.model
    mine.mkdir(parents=True, exist_ok=True)
    seeded = []
    theirs = v21.RESULTS_DIR / a.model                 # the bench's own v2.1 results, read only
    prompt = pathlib.Path(a.system_prompt).resolve() if a.system_prompt else None
    if prompt:
        spec_v2.STEWARD_PROMPT_FILE = prompt
        v21.LABEL = f"{prompt.name} (sha256 {hashlib.sha256(prompt.read_bytes()).hexdigest()}), v2 items"
    for name in ("replies.jsonl", "judgments.jsonl"):
        if not prompt and (theirs / name).exists() and not (mine / name).exists():
            shutil.copyfile(theirs / name, mine / name)
            seeded.append(str(theirs / name))
    spec_v2.RESULTS_DIR = out_root
    v21.RESULTS_DIR = out_root
    url = a.url or v2.common.STEWARD_URL
    rc = v2.cmd_score(argparse.Namespace(model=a.model, url=url))
    if rc != 0:
        return rc
    v21.relabel(a.model)
    s = json.loads((mine / "scores.json").read_text())
    if prompt:
        s["system_prompt_sha256"] = hashlib.sha256(prompt.read_bytes()).hexdigest()
        s["benchmark"] = "StewardBench v2 items under an exploratory steward prompt (not the pinned v2.1 prompt)"
        (mine / "scores.json").write_text(json.dumps(s, indent=1))
    print(json.dumps({"scores_path": str(mine / "scores.json"), "judge_calls_this_run": s.get("judge_calls_this_run"),
                      "seeded": seeded}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
