"""Freeze the steward's messages for A1 from the attempts log and the D2 review (prereg/A1.md D2).

A key gets a message only when its last accepted review verdict names an attempt that also passed the automatic
rules (no failures) in steward/messages.attempts.jsonl. Keys with no such attempt are recorded with message null and
both twins drop from A1. Writes steward/messages.frozen.jsonl once (refuses to overwrite) and prints its sha256.
"""
import hashlib
import json
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent


def main():
    out = HERE / "messages.frozen.jsonl"
    if out.exists():
        raise SystemExit(f"{out} exists: a frozen file is never overwritten")
    attempts = [json.loads(l) for l in (HERE / "messages.attempts.jsonl").read_text().splitlines()]
    attempts = {(a["key"], a["attempt"]): a for a in attempts if "content" in a}
    review = json.loads((HERE / "review_d2.json").read_text())
    passes = json.loads((HERE / "messages.jsonl").read_text().splitlines()[0])   # for the shared prompt fields
    del passes
    rows = {json.loads(l)["world"] + "." + json.loads(l)["principal"]: json.loads(l)
            for l in (HERE / "messages.jsonl").read_text().splitlines()}
    accepted = {}
    for v in review["verdicts"]:
        if v["accept"]:
            accepted[v["key"]] = v["attempt"]
    frozen = []
    for key in sorted(rows):
        r = rows[key]
        att = accepted.get(key)
        a = attempts.get((key, att)) if att else None
        if a is not None and a["failures"]:
            raise SystemExit(f"{key} attempt {att}: accepted in review but failed the rules {a['failures']}")
        frozen.append({"key": key, "world": r["world"], "principal": r["principal"], "principal_name": r["principal_name"],
                       "channel": r["channel"], "system_prompt_sha256": r["system_prompt_sha256"],
                       "user_message_sha256": r["user_message_sha256"],
                       "message": a and {"text": a["content"], "sha256": a["content_sha256"],
                                         "prompt_sha256": a["request_sha256"], "seed": a["seed"],
                                         "temperature": a["temperature"], "attempt": a["attempt"]},
                       "generator": "steward-base (Qwen3.5-4B base) at http://127.0.0.1:8417/v1, chat completions"})
    out.write_text("".join(json.dumps(f, sort_keys=True, ensure_ascii=False) + "\n" for f in frozen))
    n = sum(1 for f in frozen if f["message"])
    print(f"{out}: {n} of {len(frozen)} keys frozen with a message, sha256 {hashlib.sha256(out.read_bytes()).hexdigest()}")


if __name__ == "__main__":
    sys.exit(main())
