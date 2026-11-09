"""Continue the attempt sequence for keys the D2 review rejected (prereg/A1.md D2).

For each key named on the command line, take its next attempt number after the last one in
steward/messages.attempts.jsonl and keep generating (temperature 0.7, seed = attempt number) until an attempt passes
the automatic rules 1 to 8 or attempt 6 is used. Every attempt is appended to the attempts log as it happens.
Attempts that pass the rules still need the D2 review, recorded in steward/review_d2.json by the reviewer.

Usage (castra 8457977 on PYTHONPATH): python3.12 steward/regen.py --released data/pilot.jsonl --url URL KEY...
"""
import argparse
import json
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent))
import generate as G  # noqa: E402

LOG = HERE / "messages.attempts.jsonl"


def last_attempt(key):
    rows = [json.loads(line) for line in LOG.read_text().splitlines()]
    return max(r["attempt"] for r in rows if r.get("key") == key and "content" in r)


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--released", required=True)
    p.add_argument("--url", required=True)
    p.add_argument("keys", nargs="+")
    a = p.parse_args(argv)
    import compile as K
    pairs = {f"{w}.{n}": pair for (w, n), pair in G.twins(K.released_bases(a.released)).items()}
    system = G.SYSTEM_PROMPT.read_text()
    with open(LOG, "a") as log:
        for key in a.keys:
            base = pairs[key]["principal"]
            _, mailbox = G.masked_mailbox(base)
            user = G.user_message(base, mailbox)
            sys_text = system.replace("{PRINCIPAL}", base["roles"]["principal"]["name"])
            for i in range(last_attempt(key) + 1, G.MAX_ATTEMPTS + 1):
                temp, seed = G.SCHEDULE[i - 1]
                body = {"model": G.MODEL, "messages": [{"role": "system", "content": sys_text},
                                                       {"role": "user", "content": user}],
                        "temperature": temp, "seed": seed, "max_tokens": G.MAX_TOKENS}
                resp = G.ask_logged(a.url, body, log, key, i)
                text = resp["choices"][0]["message"]["content"]
                fails = G.validate(text, base, user)
                if resp["choices"][0].get("finish_reason") != "stop":
                    fails.append(f"1: did not finish (finish_reason {resp['choices'][0].get('finish_reason')})")
                row = {"key": key, "attempt": i, "temperature": temp, "seed": seed, "request": body,
                       "request_sha256": G.sha256_json(body), "raw_response": resp, "content": text,
                       "content_sha256": G.C.sha256_text(text), "failures": fails, "accepted": not fails,
                       "phase": "D2 continuation"}
                log.write(json.dumps(row, sort_keys=True, ensure_ascii=False) + "\n")
                log.flush()
                print(f"== {key} attempt {i} (T={temp}, seed {seed}): {'PASSES RULES 1-8' if not fails else 'rejected ' + '; '.join(fails)}")
                if not fails:
                    print(text, "\n")
                    break
            else:
                print(f"== {key}: no attempt left that passes the rules")
    return 0


if __name__ == "__main__":
    sys.exit(main())
