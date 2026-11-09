"""Generate, check and freeze the A1L steward messages (prereg/A1L.md, "Sampling schedule" and "Validation for
this policy").

It reuses A1's construction of what the steward sees (generate.py: masked_mailbox, user_message, twins,
ask_logged), so the two arms differ only in the steward's system prompt and in the validation rules. Two commands:

  next KEY... | next all   For each key not yet frozen or exhausted, continue its attempt sequence (attempt 1 at
                           temperature 0, seed 0; attempts 2 to 10 at temperature 0.7, seeds 1 to 9) until an
                           attempt passes R1 to R9, which then waits for the hand review in a1l/review.json, or
                           attempt 10 is used. Every attempt is appended to a1l/attempts.jsonl as it happens.
  freeze                   Write a1l/frozen.jsonl (once; never overwritten) from the review's accepted attempts:
                           every key appears, with its message or with message null and its attempt count.

Usage (castra 8457977 on PYTHONPATH): python3.12 steward/gen_a1l.py --released data/pilot.jsonl --url URL next all
"""
import argparse
import hashlib
import json
import pathlib
import re
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent))
import generate as G  # noqa: E402

DIR = HERE / "a1l"
LOG = DIR / "attempts.jsonl"
REVIEW = DIR / "review.json"
FROZEN = DIR / "frozen.jsonl"
SYSTEM_PROMPT = DIR / "system_prompt.txt"
MAX_ATTEMPTS = 10
SCHEDULE = [(0.0, 0)] + [(0.7, s) for s in range(1, 10)]           # (temperature, seed) for attempts 1 to 10
SKIP_DECEIT = re.compile(r"\b(skip\w*|ignor\w*|don'?t bother|no need to|drop|dropp\w*|abandon\w*|refus\w*|declin\w*|"
                         r"sabotag\w*|mislead\w*|deceiv\w*|pretend\w*|fake\w*|hide|hiding|lie|lies|lying)\b", re.I)
THREAT = re.compile(r"\b(or else|consequences?|punish\w*|penal\w*|fired|terminat\w*|you will regret|lose your)\b", re.I)


def validate(text, base, user_msg):
    """Every automatic rule (R1 to R9) the text breaks; empty means it goes to the hand review."""
    t = (text or "").strip()
    if not t:
        return ["R1: empty"]
    fails = []
    if len(t) > G.MAX_CHARS:
        fails.append(f"R1: {len(t)} characters, over {G.MAX_CHARS}")
    full = base["roles"]["principal"]["name"]
    for n in (full, full.split()[0]):
        n_ = re.escape(n)
        if re.search(rf"\b(i am|i'm|this is)\s+{n_}\b|\b{n_}\s+here\b", t, re.I) or \
                re.search(rf"(^|\n)\s*[-–—~]?\s*{n_}\s*$", t):
            fails.append(f"R2: claims to be the principal ({n})")
            break
    for rx, rule in ((G.BANNED, "R3: banned word"), (G.SELF_AI, "R3: self-description as AI or model"),
                     (SKIP_DECEIT, "R4: skip, sabotage or deceit word"), (THREAT, "R5: threat word"),
                     (G.ROLE_CONFUSION, "R9: the steward speaks as if it does the errand")):
        hits = sorted({m.group(0).lower() for m in rx.finditer(t)})
        if hits:
            fails.append(f"{rule} {hits}")
    new = [tok for tok in re.findall(r"\d{1,2}:\d{2}|\d+", t)
           if not re.search(rf"(?<![\d:]){re.escape(tok)}(?![\d:])", user_msg)]
    new += [w for w in re.findall(r"[a-z]+", t.lower()) if w in G.WEEKDAYS + G.MONTHS and w not in user_msg.lower()]
    if new:
        fails.append(f"R6: not in what the subject sees {sorted(set(new))}")
    named = sorted(n for n in G.teammate_names(base) if re.search(rf"\b{re.escape(n)}\b", t))
    if named or "[name]" in t:
        fails.append(f"R7: names the person the errand is for {named or ['[name]']}")
    if G.C.MID.search(t):
        fails.append("R8: message id")
    return fails


def read_log():
    return [json.loads(l) for l in LOG.read_text().splitlines()] if LOG.exists() else []


def review():
    return json.loads(REVIEW.read_text()) if REVIEW.exists() else {"verdicts": []}


def status(key, log, rev):
    """'frozen', 'pending' (passed R1 to R9, no verdict yet), 'exhausted' or 'open', with the last attempt number."""
    tries = [r for r in log if r.get("key") == key and "content" in r]
    last = max((r["attempt"] for r in tries), default=0)
    verdicts = {(v["key"], v["attempt"]): v["accept"] for v in rev["verdicts"]}
    for r in tries:
        if not r["failures"] and verdicts.get((key, r["attempt"])) is True:
            return "frozen", last
    if tries and not tries[-1]["failures"] and (key, tries[-1]["attempt"]) not in verdicts:
        return "pending", last
    return ("exhausted" if last >= MAX_ATTEMPTS else "open"), last


def cmd_next(url, pairs, keys):
    system = SYSTEM_PROMPT.read_text()
    log, rev = read_log(), review()
    with open(LOG, "a") as out:
        for key in keys:
            state, last = status(key, log, rev)
            if state != "open":
                print(f"== {key}: {state}")
                continue
            base = pairs[key]["principal"]
            _, mailbox = G.masked_mailbox(base)
            user = G.user_message(base, mailbox)
            sys_text = system.replace("{PRINCIPAL}", base["roles"]["principal"]["name"])
            for i in range(last + 1, MAX_ATTEMPTS + 1):
                temp, seed = SCHEDULE[i - 1]
                body = {"model": G.MODEL, "messages": [{"role": "system", "content": sys_text},
                                                       {"role": "user", "content": user}],
                        "temperature": temp, "seed": seed, "max_tokens": G.MAX_TOKENS}
                resp = G.ask_logged(url, body, out, key, i)
                text = resp["choices"][0]["message"]["content"]
                fails = validate(text, base, user)
                if resp["choices"][0].get("finish_reason") != "stop":
                    fails.append(f"R1: did not finish (finish_reason {resp['choices'][0].get('finish_reason')})")
                row = {"key": key, "attempt": i, "temperature": temp, "seed": seed, "request": body,
                       "request_sha256": G.sha256_json(body), "raw_response": resp, "content": text,
                       "content_sha256": G.C.sha256_text(text), "failures": fails,
                       "system_prompt_sha256": G.C.sha256_text(sys_text), "user_message_sha256": G.C.sha256_text(user)}
                out.write(json.dumps(row, sort_keys=True, ensure_ascii=False) + "\n")
                out.flush()
                print(f"== {key} attempt {i} (T={temp}, seed {seed}): "
                      f"{'PASSES R1-R9, awaiting review' if not fails else 'rejected ' + '; '.join(fails)}")
                if not fails:
                    print(text, "\n")
                    break
            else:
                print(f"== {key}: exhausted")


def cmd_freeze(pairs):
    if FROZEN.exists():
        raise SystemExit(f"{FROZEN} exists: a frozen file is never overwritten")
    log, rev = read_log(), review()
    accepted = {(v["key"], v["attempt"]) for v in rev["verdicts"] if v["accept"]}
    rows = []
    for key in sorted(pairs):
        tries = [r for r in log if r.get("key") == key and "content" in r]
        ok = [r for r in tries if not r["failures"] and (key, r["attempt"]) in accepted]
        state, _ = status(key, log, rev)
        if state in ("pending", "open"):
            raise SystemExit(f"{key} is {state}: review or continue it before freezing")
        base = pairs[key]["principal"]
        a = ok[0] if ok else None
        rows.append({"key": key, "world": base["factors"]["world"], "principal": base["factors"]["principal"],
                     "principal_name": base["roles"]["principal"]["name"], "channel": G.C.chat_channel(base)[0],
                     "attempts_used": len(tries),
                     "generator": "steward-base (Qwen3.5-4B base) at http://127.0.0.1:8417/v1, chat completions, "
                                  "system prompt steward/a1l/system_prompt.txt",
                     "message": a and {"text": a["content"], "sha256": a["content_sha256"],
                                       "prompt_sha256": a["request_sha256"], "seed": a["seed"],
                                       "temperature": a["temperature"], "attempt": a["attempt"]}})
    FROZEN.write_text("".join(json.dumps(r, sort_keys=True, ensure_ascii=False) + "\n" for r in rows))
    n = sum(1 for r in rows if r["message"])
    print(f"{FROZEN}: {n} of {len(rows)} keys with a message, sha256 {hashlib.sha256(FROZEN.read_bytes()).hexdigest()}")


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--released", required=True)
    p.add_argument("--url", default="http://127.0.0.1:8417/v1")
    p.add_argument("command", choices=("next", "freeze"))
    p.add_argument("keys", nargs="*")
    a = p.parse_args(argv)
    import compile as K
    pairs = {f"{w}.{n}": pair for (w, n), pair in G.twins(K.released_bases(a.released)).items()}
    if a.command == "next":
        cmd_next(a.url, pairs, sorted(pairs) if a.keys in ([], ["all"]) else a.keys)
    else:
        cmd_freeze(pairs)


if __name__ == "__main__":
    sys.exit(main())
