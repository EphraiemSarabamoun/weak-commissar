"""R5 rewrites for any commissar model on the local server, for eval_model.py's dev split.

prereg/R5.md fixes how the commissar rewrites a cell, and steward/gen_rewrite.py (agent N's) implements it for
steward-base: the pinned v2.1 instructions as the system prompt, Ephraiem's task line plus the two-header format and
the cell's kickoff and request as the user message (gen_rewrite.user_message), A1L's attempt schedule, and the
automatic rules W1 to W11 (gen_rewrite.validate). This module runs exactly that procedure with the model name as a
parameter and the log and frozen file in the model's evals folder, so a fine-tune is measured on the same arm as the
confirmatory R5 run. Rows use gen_rewrite's attempt and frozen formats, so rewrite_arm.overlay compiles them as is.

seed_from copies a model's attempts from another log (read only), so a model whose rewrites already exist (steward-base,
in steward/rewrite/attempts.jsonl) is not generated twice.
"""
import concurrent.futures
import hashlib
import json
import pathlib
import re
import threading

import gen_rewrite as GR
import generate as G


def read_log(path):
    path = pathlib.Path(path)
    return [json.loads(l) for l in path.read_text().splitlines() if l.strip()] if path.exists() else []


def tries(log, key, max_attempts):
    """A cell's counted attempts: in attempt order, at most max_attempts, ending at the first accepted one."""
    out = []
    for r in sorted((r for r in log if r.get("key") == key and "content" in r), key=lambda r: r["attempt"]):
        if len(out) >= max_attempts:
            break
        out.append(r)
        if not r["failures"]:
            break
    return out


def is_open(rows, max_attempts):
    return not any(not r["failures"] for r in rows) and len(rows) < max_attempts


def seed_from(source, dest, model, keys):
    """Copy source's attempt rows for keys whose request named model into dest, once (dest must not exist yet).
    Returns {source, source_sha256, rows}: the record written at the copy, read back on later calls (None when dest
    exists without one)."""
    dest = pathlib.Path(dest)
    record = dest.with_suffix(".seed.json")              # the copy's provenance, kept beside it
    if dest.exists():
        return json.loads(record.read_text()) if record.exists() else None
    data = pathlib.Path(source).read_bytes()
    rows = [json.loads(l) for l in data.decode().splitlines() if l.strip()]
    keep = [r for r in rows if r.get("key") in keys and "content" in r and r["request"]["model"] == model]
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text("".join(json.dumps(r, sort_keys=True, ensure_ascii=False) + "\n" for r in keep))
    out = {"source": str(source), "source_sha256": hashlib.sha256(data).hexdigest(), "rows": len(keep)}
    record.write_text(json.dumps(out, indent=1) + "\n")
    return out


VALIDATORS = {"r5": "W1-W11 (gen_rewrite.validate_r5, prereg/R5.md; rounds 0 and 0.5)",
              "current": "gen_rewrite.validate: W1-W12 + W13 pinned Sonnet judge (request preservation, DEVIATIONS.md)"}


def validator(name):
    """The acceptance function by name. 'current' calls the W13 judge (one Sonnet request per attempt that passes
    W1-W12), so its cost and its coverage differ from 'r5'; a round records which one it used."""
    if name == "r5":
        return GR.validate_r5
    if name == "current":
        return GR.validate
    raise SystemExit(f"unknown validator {name!r}; one of {sorted(VALIDATORS)}")


def recheck(bases, frozen):
    """W12 and the W13 judge on every accepted rewrite of a round accepted under W1-W11, so the round can be read as
    the current validator would have frozen it. Returns {key: {w12, w13 verdict, changes, pass}}; one judge call per
    rewrite that passes W12."""
    by = {GR.cell_key(b): b for b in bases}
    out = {}
    for r in frozen:
        if not r["rewrite"]:
            continue
        base, parts = by[r["key"]], (r["rewrite"]["texts"]["user"], r["rewrite"]["texts"]["request"])
        w12 = GR.request_preservation(base, parts)
        j = None if w12 else GR.judge_check(base["roles"]["principal"]["name"], GR.originals(base), parts)
        out[r["key"]] = {"w12": w12, "w13": j and j["verdict"], "w13_changes": j and j["changes"],
                         "w13_served_model": j and j["served_model"], "pass": not w12 and bool(j) and j["verdict"] == "PASS"}
    return out


def _cell(url, model, base, system, out, lock, prior, max_attempts, accept):
    key = GR.cell_key(base)
    rows = tries(prior, key, max_attempts)
    if not is_open(rows, max_attempts):
        return 0
    name = base["roles"]["principal"]["name"]
    sys_text, user = system.replace("{PRINCIPAL}", name), GR.user_message(base)
    made = 0
    for i in range(len(rows) + 1, max_attempts + 1):
        temp, seed = GR.SCHEDULE[i - 1]
        body = {"model": model, "messages": [{"role": "system", "content": sys_text}, {"role": "user", "content": user}],
                "temperature": temp, "seed": seed, "max_tokens": GR.MAX_TOKENS}
        resp = G.ask_logged(url, body, _Locked(out, lock), key, i)
        made += 1
        choice = resp["choices"][0]
        judge = None
        if accept is GR.validate:                      # keep the W13 judge's record with the attempt
            parts, fails, judge = GR.validate_detail(choice["message"]["content"], choice.get("finish_reason"), base)
        else:
            parts, fails = accept(choice["message"]["content"], choice.get("finish_reason"), base)
        row = {"key": key, "attempt": i, "temperature": temp, "seed": seed, "request": body,
               "request_sha256": G.sha256_json(body), "raw_response": resp, "response_model": resp.get("model"),
               "content": choice["message"]["content"], "parts": parts and {"user": parts[0], "request": parts[1]},
               "failures": fails, "judge": judge, "system_prompt_sha256": G.C.sha256_text(sys_text)}
        with lock:
            out.write(json.dumps(row, sort_keys=True, ensure_ascii=False) + "\n")
            out.flush()
        if not fails:
            break
    return made


class _Locked:
    """A shared log handle for G.ask_logged's transport-error lines from worker threads."""
    def __init__(self, f, lock):
        self.f, self.lock = f, lock

    def write(self, s):
        with self.lock:
            self.f.write(s)

    def flush(self):
        with self.lock:
            self.f.flush()


def system_prompt(path=None):
    """(text, sha256) of the commissar's system prompt: the pinned commissar_prompt_v2_1 by default (prereg/R5.md), or
    the file at path for an exploratory dev round (e.g. steward/prompts/commissar_prompt_v2_2.txt). {PRINCIPAL} is
    filled per cell, as for v2.1."""
    if path is None:
        text = GR.SYSTEM_PROMPT.read_text()
        if G.C.sha256_text(text) != GR.SYSTEM_PROMPT_SHA256:
            raise SystemExit(f"{GR.SYSTEM_PROMPT} is not commissar_prompt_v2_1")
        return text, GR.SYSTEM_PROMPT_SHA256
    text = pathlib.Path(path).read_text()
    if "{PRINCIPAL}" not in text:
        raise SystemExit(f"{path} has no {{PRINCIPAL}} placeholder")
    return text, G.C.sha256_text(text)


def generate(url, model, bases, log_path, max_attempts=GR.MAX_ATTEMPTS, workers=2, system_prompt_path=None,
             validator_name="current"):
    """Continue every open cell (resuming from log_path); returns the number of server calls made. The server runs
    one generation at a time (commissar serve/engine.py), so extra workers only keep its queue full."""
    system, _ = system_prompt(system_prompt_path)
    prior, lock = read_log(log_path), threading.Lock()
    pathlib.Path(log_path).parent.mkdir(parents=True, exist_ok=True)
    with open(log_path, "a") as out, concurrent.futures.ThreadPoolExecutor(workers) as pool:
        accept = validator(validator_name)
        futs = [pool.submit(_cell, url, model, b, system, out, lock, prior, max_attempts, accept) for b in bases]
        return sum(f.result() for f in futs)


def freeze(bases, log_path, model, url, max_attempts, system_prompt_path=None):
    """gen_rewrite's frozen rows (one per cell, rewrite or null) from log_path; refuses while a cell is open."""
    log = read_log(log_path)
    _, prompt_sha = system_prompt(system_prompt_path)
    rows = []
    for base in sorted(bases, key=GR.cell_key):
        key = GR.cell_key(base)
        t = tries(log, key, max_attempts)
        if is_open(t, max_attempts):
            raise SystemExit(f"{key} is still open in {log_path}")
        ok = next((r for r in t if not r["failures"]), None)
        user, request = GR.originals(base)
        rows.append({"key": key, "world": base["factors"]["world"], "beneficiary": base["factors"]["beneficiary"],
                     "principal": base["factors"]["principal"], "principal_name": base["roles"]["principal"]["name"],
                     "channel": G.C.chat_channel(base)[0], "attempts_used": len(t),
                     "generator": f"{model} at {url}, prereg/R5.md procedure (eval_rewrites.py), max {max_attempts} attempts, "
                                  f"system prompt sha256 {prompt_sha}", "system_prompt_sha256": prompt_sha,
                     "original": {"user_sha256": G.C.sha256_text(user), "request_sha256": G.C.sha256_text(request)},
                     "rewrite": ok and {"texts": ok["parts"], "user_sha256": G.C.sha256_text(ok["parts"]["user"]),
                                        "request_sha256": G.C.sha256_text(ok["parts"]["request"]),
                                        "attempt": ok["attempt"], "seed": ok["seed"], "temperature": ok["temperature"],
                                        "call_sha256": ok["request_sha256"], "response_model": ok["response_model"]}})
    return rows


# Heuristic cues for which way a rewrite steers the agent's effort (not part of R5's acceptance rules).
ONE_ATTEMPT = re.compile(r"one (?:honest )?attempt|single attempt|move on", re.I)
PERSIST = re.compile(r"until (?:it is |it's |the work is |this is )?(?:done|complete|completed|finished)|whatever (?:it )?costs?|"
                     r"regardless of (?:the )?cost|see (?:it|this) through|absolute priority|takes? priority|top priority", re.I)


def direction(row):
    """'persist', 'one_attempt', 'both' or 'none': which effort cue the accepted rewrite carries (no operae original
    request carries either cue, so a cue here was added by the commissar)."""
    text = row["rewrite"]["texts"]["user"] + "\n" + row["rewrite"]["texts"]["request"]
    p, o = bool(PERSIST.search(text)), bool(ONE_ATTEMPT.search(text))
    return {(True, False): "persist", (False, True): "one_attempt", (True, True): "both"}.get((p, o), "none")


def guidance_direction(frozen):
    """Per beneficiary, how often the rewrite's cue matches Ephraiem's policy: persist for the principal's own errand,
    one honest attempt for a teammate's. A heuristic over regexes, reported beside the outcome, never instead of it."""
    import collections
    out = {}
    for ben, want in (("principal", "persist"), ("teammate", "one_attempt")):
        got = collections.Counter(direction(r) for r in frozen if r["rewrite"] and r["beneficiary"] == ben)
        out[ben] = {"matches_policy": got.get(want, 0), "of": sum(got.values()), "cues": dict(got)}
    return out


def stats(bases, log_path, frozen, max_attempts):
    """Coverage and the W-rule failures (fact preservation is W2 dropped and W3 added) over the counted attempts."""
    import collections
    log = read_log(log_path)
    rules, cells_hit, per_cell = collections.Counter(), collections.Counter(), {}
    n = 0
    for base in bases:
        key = GR.cell_key(base)
        t = tries(log, key, max_attempts)
        n += len(t)
        seen = {f.split(":")[0].split(" ")[0] for r in t for f in r["failures"]}
        for r in t:
            rules.update(f.split(":")[0].split(" ")[0] for f in r["failures"])
        cells_hit.update(seen)
        ok = next((r for r in t if not r["failures"]), None)
        per_cell[key] = {"attempts": len(t), "accepted_at": ok and ok["attempt"],
                         "last_failures": None if ok else (t[-1]["failures"] if t else ["no attempt"])}
    done = [r for r in frozen if r["rewrite"]]
    guidance = sum(bool(GR.GUIDANCE.search(r["rewrite"]["texts"]["user"] + " " + r["rewrite"]["texts"]["request"]))
                   for r in done)
    return {"cells": len(bases), "covered": len(done), "coverage": len(done) / len(bases) if bases else None,
            "accepted_at_attempt_1": sum(r["rewrite"]["attempt"] == 1 for r in done), "attempts": n,
            "max_attempts": max_attempts,
            "failures_by_rule_attempts": dict(sorted(rules.items())), "cells_with_rule_failure": dict(sorted(cells_hit.items())),
            "fact_preservation_failed_attempts": {"W2_dropped": rules.get("W2", 0), "W3_added": rules.get("W3", 0)},
            "accepted_with_priority_guidance": guidance, "guidance_direction": guidance_direction(frozen),
            "kickoff_changed": sum(r["rewrite"]["texts"]["user"] != b["user"] for r in done for b in bases
                                   if GR.cell_key(b) == r["key"]),
            "per_cell": per_cell}
