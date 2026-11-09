"""Run an experiment: boards x rounds x live agents, logged call by call, resumable, inside a call and time budget.

Flow for one board (condition c, index b, seed board_seed(seed, c, b)):

    posts = c's seed posts
    for round r in 1..R:
        every live agent gets (its system prompt, task + render(posts) + reply contract)  -- in parallel
        each reply is parsed strictly (parse.py); the call is logged to calls.jsonl
        once ALL of round r's agents have a logged reply, their posts are appended (roster order, or a seeded
        shuffle), INVALID replies append nothing, and scripted agents append their round-r post

Every call row carries a key `condition|bNN|rN|agent`. On resume the runner rebuilds each board from the logged
rows: a key with an ok row is not called again, and its prompt is recomputed and must hash to the logged
prompt_sha256 (and run with the same model), or the run refuses with ResumeMismatch. A row with ok false (the
backend failed after its retries) is called again. Because rounds are synchronous and the mock is seeded by the
board seed, a resumed run produces exactly the rows an uninterrupted one would.

Stops are clean: before any call starts, the runner checks the call budget (attempts across all sessions of
this run, retries included), the wall-clock budget (this session) and the consecutive-error stop; once one
trips, no new call starts, in-flight calls finish and are logged, boards end at their last complete round, and
status.json says why. A later `run` on the same directory resumes.
"""
import json
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

from . import board as B
from . import kin
from .backends import Reply
from .parse import parse

HARNESS_VERSION = "0.1.0"
MAX_CONSECUTIVE_ERRORS = 8      # the stop kin-oversight and castra both use; it stopped a dead quota before


class ResumeMismatch(RuntimeError):
    """The run directory holds rows a different config, model or harness made; refusing to mix them."""


def now():
    """UTC timestamp, seconds precision."""
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def call_key(cid, b, r, agent):
    """The unique key of one agent turn."""
    return f"{cid}|b{b:02d}|r{r}|{agent}"


def read_rows(path):
    """All rows of a calls.jsonl (a torn final line from a crash is skipped)."""
    rows = []
    if Path(path).exists():
        for line in Path(path).read_text().splitlines():
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return rows


class Run:
    """One run directory: plan, resume state, budgets, the call pool and the log writer."""

    def __init__(self, experiment, out, backend, concurrency=8, max_calls=None, max_wall_s=None, conditions=None,
                 boards=None, model=None, retries=1, log_prompts=True, max_consecutive_errors=MAX_CONSECUTIVE_ERRORS):
        self.exp, self.out, self.backend = experiment, Path(out), backend
        self.concurrency = max(1, int(concurrency))
        self.max_calls, self.max_wall_s = max_calls, max_wall_s
        self.condition_ids = list(conditions) if conditions else [c["id"] for c in experiment.conditions]
        for cid in self.condition_ids:
            experiment.condition(cid)                       # KeyError on an unknown condition
        self.boards = int(boards) if boards else experiment.boards_per_condition
        self.model, self.retries, self.log_prompts = model, int(retries), log_prompts
        self.max_consecutive_errors = max_consecutive_errors
        self.calls_path = self.out / "calls.jsonl"
        self.lock = threading.Lock()
        self.stop_reason = None
        self.consecutive_errors = 0
        self.session_calls = 0
        rows = read_rows(self.calls_path)
        self.attempts_total = sum(int(r.get("attempts", 1)) for r in rows)
        self.done = {r["key"]: r for r in rows if r.get("ok")}

    # -- manifest and status ------------------------------------------------------------------------------
    def identity(self):
        """What must match between sessions of one run directory."""
        return {"config_sha256": self.exp.config_sha256, "backend": self.backend.name, "model_override": self.model,
                "harness_version": HARNESS_VERSION}

    def write_manifest(self, extra=None):
        """Create manifest.json, or check an existing one has the same identity (else ResumeMismatch)."""
        self.out.mkdir(parents=True, exist_ok=True)
        path = self.out / "manifest.json"
        ident = self.identity()
        if path.exists():
            old = json.loads(path.read_text())
            diff = {k: (old.get("identity", {}).get(k), v) for k, v in ident.items()
                    if old.get("identity", {}).get(k) != v}
            if diff:
                raise ResumeMismatch(f"{path} was made under a different identity: {diff}")
            old.setdefault("sessions", []).append(now())
            path.write_text(json.dumps(old, indent=1))
            return old
        man = {"identity": ident, "experiment": self.exp.name, "created": now(), "sessions": [now()],
               "conditions": self.condition_ids, "boards_per_condition": self.boards,
               "concurrency": self.concurrency, "kin": kin.provenance(), "config": self.exp.raw, **(extra or {})}
        path.write_text(json.dumps(man, indent=1))
        return man

    def write_status(self, state, started, boards_complete, boards_total):
        """status.json: where the run stands and why it stopped."""
        rows = read_rows(self.calls_path)
        latest = {r["key"]: r for r in rows}
        status = {"state": state, "stop_reason": self.stop_reason, "boards_complete": boards_complete,
                  "boards_total": boards_total, "turns_logged_ok": sum(1 for r in latest.values() if r.get("ok")),
                  "invalid": sum(1 for r in latest.values() if r.get("ok") and not r.get("valid")),
                  "attempts_total": self.attempts_total, "session_calls": self.session_calls,
                  "started": started, "finished": now()}
        (self.out / "status.json").write_text(json.dumps(status, indent=1))
        return status

    # -- budget and calls ---------------------------------------------------------------------------------
    def _may_start(self):
        """Reserve one attempt if no stop has tripped; return False (and record why) otherwise."""
        with self.lock:
            if self.stop_reason:
                return False
            if self.max_calls is not None and self.attempts_total >= self.max_calls:
                self.stop_reason = f"call budget reached ({self.max_calls} attempts)"
                return False
            if self.max_wall_s is not None and time.monotonic() - self.t0 >= self.max_wall_s:
                self.stop_reason = f"wall-clock budget reached ({self.max_wall_s} s)"
                return False
            self.attempts_total += 1
            self.session_calls += 1
            return True

    def _log(self, row):
        """Append one row to calls.jsonl under the lock (one write, one line)."""
        with self.lock:
            with open(self.calls_path, "a") as f:
                f.write(json.dumps(row) + "\n")

    def _turn(self, job):
        """Run one agent turn with retries; log and return its row, or None if a stop kept it from starting."""
        attempts, reply, t_start = 0, None, now()
        while attempts <= self.retries:
            if not self._may_start():
                break
            attempts += 1
            try:
                reply = self.backend.call(job["model"], job["system"], job["user"], job["ctx"])
            except Exception as exc:          # a backend bug must not kill the pool: log it as a failed call
                reply = Reply(text="", ok=False, error=f"{type(exc).__name__}: {exc}")
            if reply.ok:
                break
        if attempts == 0:
            return None
        parsed = parse(reply.text, job["menu"]) if reply.ok else None
        row = {**job["meta"], "model": job["model"], "backend": self.backend.name,
               "system_sha256": B.sha256(job["system"]), "prompt_sha256": job["prompt_sha256"],
               "raw": reply.text, "ok": reply.ok, "error": reply.error, "attempts": attempts,
               "action": parsed.label if parsed else None, "valid": bool(parsed and parsed.valid),
               "invalid_reason": parsed.invalid_reason if parsed else None, "post": parsed.post if parsed else "",
               "seconds": reply.seconds, "wall_seconds": reply.wall_seconds, "input_tokens": reply.input_tokens,
               "cached_tokens": reply.cached_tokens, "output_tokens": reply.output_tokens,
               "assistant_messages": reply.assistant_messages, "served_model": reply.served_model,
               "t_start": t_start, "t_end": now(), "harness_version": HARNESS_VERSION}
        if self.log_prompts:
            row["system"], row["prompt"] = job["system"], job["user"]
        self._log(row)
        with self.lock:
            if reply.ok:
                self.consecutive_errors = 0
            else:
                self.consecutive_errors += 1
                if self.consecutive_errors >= self.max_consecutive_errors and not self.stop_reason:
                    self.stop_reason = f"{self.consecutive_errors} consecutive backend errors"
        return row

    # -- boards -------------------------------------------------------------------------------------------
    def _job(self, cond, b, seed, r, agent, posts):
        """Everything one agent turn needs: prompts, hash, model, menu, the mock context and the row identity."""
        system = B.system_prompt(agent, cond)
        user = B.user_message(agent, cond, posts, r)
        model = self.model or agent.get("model") or cond["model"]
        return {"system": system, "user": user, "prompt_sha256": B.sha256(system + "\n\x00\n" + user),
                "model": model, "menu": [a["id"] for a in cond["actions"]],
                "ctx": {"board_seed": seed, "round": r, "agent": agent["name"], "target": cond["target_action"],
                        "actions": [a["id"] for a in cond["actions"]], "visible": list(posts), "mock": cond["mock"]},
                "meta": {"key": call_key(cond["id"], b, r, agent["name"]), "experiment": self.exp.name,
                         "condition": cond["id"], "board": b, "board_seed": seed, "round": r,
                         "agent": agent["name"], "role": agent.get("role") or ""}}

    def run_board(self, cond, b):
        """Play one board to its last round, or to the last round a stop allowed; True when complete."""
        seed = B.board_seed(self.exp.seed, cond["id"], b)
        posts = B.seed_posts(cond)
        live = [a for a in cond["agents"] if not a.get("scripted")]
        for r in range(1, cond["rounds"] + 1):
            jobs = [self._job(cond, b, seed, r, a, posts) for a in live]
            rows, pending = {}, []
            for job in jobs:
                old = self.done.get(job["meta"]["key"])
                if old is None:
                    pending.append(job)
                    continue
                if old.get("prompt_sha256") != job["prompt_sha256"] or old.get("model") != job["model"]:
                    raise ResumeMismatch(f"{job['meta']['key']}: logged prompt or model differs from this config")
                rows[job["meta"]["agent"]] = old
            for job, row in zip(pending, self.pool.map(self._turn, pending)):
                if row is not None and row.get("ok"):
                    rows[job["meta"]["agent"]] = row
                    with self.lock:
                        self.done[row["key"]] = row
            if len(rows) < len(live):
                return False          # a stop, or a backend failure after retries: the board resumes from here
            new = []
            for a in cond["agents"]:
                if a.get("scripted"):
                    lines = a.get("posts") or []
                    if r <= len(lines):
                        new.append(B.Post(author=a["name"], text=str(lines[r - 1]).strip(), round=r,
                                          role=a.get("role") or "", action=a.get("action"), scripted=True))
                else:
                    row = rows[a["name"]]
                    if row.get("valid"):
                        new.append(B.Post(author=a["name"], text=row.get("post") or "", round=r,
                                          role=a.get("role") or "", action=row["action"]))
            order = B.round_order([p.author for p in new], seed, r, cond["shuffle_round_order"])
            by_name = {p.author: p for p in new}
            posts = posts + [by_name[n] for n in order]
        return True

    def _guarded_board(self, job):
        """run_board, but an exception in one board (a ResumeMismatch, a bug) stops every other board from
        starting new calls before it propagates, so a broken run cannot keep spending calls in the background."""
        try:
            return self.run_board(*job)
        except BaseException as exc:
            with self.lock:
                self.stop_reason = self.stop_reason or f"stopped by an error in another board: {exc}"
            raise

    def run(self, manifest_extra=None):
        """Run (or resume) every planned board; returns the status dict."""
        self.t0 = time.monotonic()
        started = now()
        self.write_manifest(manifest_extra)
        plan = [(self.exp.condition(cid), b) for cid in self.condition_ids for b in range(self.boards)]
        with ThreadPoolExecutor(self.concurrency) as self.pool, ThreadPoolExecutor(self.concurrency) as boards:
            results = list(boards.map(self._guarded_board, plan))
        complete = sum(results)
        state = "complete" if complete == len(plan) else "stopped"
        if state == "stopped" and not self.stop_reason:
            self.stop_reason = "some turns failed after retries; run again to retry them"
        return self.write_status(state, started, complete, len(plan))
