"""A team's shared state outside the workspace: the message board, the submission ledger, the round marker and
the append-only tool-call log. Four tool-server processes (one per agent) and the runner touch these files at
once, so every read-modify-write holds an exclusive fcntl lock on <team_dir>/state/.lock.

Layout under <team_dir>:
  state/round.json        {"round": r, "rounds": R}, written by the runner before each round's turns start; after
                          the last round, with debrief on, {"round": R', "rounds": R, "phase": "debrief"} (tools closed)
  state/board.jsonl       one post per line: {seq, round, author, text, t}
  state/submissions.jsonl one attempt per line: {n, round, role, text, score, passed, feedback, t}
  state/shared_rNN/       board_visibility next_round only: a copy of workspace/shared taken at the start of
                          round NN (= the end of round NN-1), which the tool server serves for shared/ reads
  state/locks/<h>.lock    one lock file per shared/ path ever written (h hashes the canonical virtual path), so
                          writes to the same file from different tool servers take turns (path_lock)
  tool_calls.jsonl        one row per tool call (written by the tool server; schema in tools_server.py)

None of these paths is reachable through the agents' tools: the workspace is <team_dir>/workspace and
Workspace.resolve() refuses anything outside it.
"""
import contextlib
import fcntl
import hashlib
import json
import shutil
import time
from datetime import datetime, timezone
from pathlib import Path


def now():
    """UTC timestamp with milliseconds (the log orders events by it)."""
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def read_jsonl(path):
    """All rows of a JSONL file; a torn final line is skipped."""
    rows = []
    p = Path(path)
    if p.exists():
        for line in p.read_text().splitlines():
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return rows


class TeamState:
    """File-locked access to one team's board, submissions, round marker and tool log."""

    def __init__(self, team_dir):
        self.dir = Path(team_dir)
        self.state = self.dir / "state"
        self.state.mkdir(parents=True, exist_ok=True)
        self.lock_path = self.state / ".lock"
        self.board_path = self.state / "board.jsonl"
        self.subs_path = self.state / "submissions.jsonl"
        self.round_path = self.state / "round.json"
        self.log_path = self.dir / "tool_calls.jsonl"

    @contextlib.contextmanager
    def locked(self):
        """Hold the team's exclusive lock for the duration of the block."""
        with open(self.lock_path, "a") as fh:
            fcntl.flock(fh, fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(fh, fcntl.LOCK_UN)

    @contextlib.contextmanager
    def path_lock(self, key):
        """Hold an exclusive lock for one workspace path (its canonical virtual path) for the duration of the block.
        Separate from the team lock, so a slow write never holds up the board, the ledger or the tool log."""
        locks = self.state / "locks"
        locks.mkdir(exist_ok=True)
        with open(locks / (hashlib.sha256(key.encode()).hexdigest()[:24] + ".lock"), "a") as fh:
            fcntl.flock(fh, fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(fh, fcntl.LOCK_UN)

    def _append(self, path, row):
        """Append one JSON line (caller holds the lock)."""
        with open(path, "a") as f:
            f.write(json.dumps(row) + "\n")

    # -- round ----------------------------------------------------------------------------------------------
    def set_round(self, r, rounds):
        """Mark round r of R as current."""
        with self.locked():
            self.round_path.write_text(json.dumps({"round": r, "rounds": rounds}))

    def set_debrief(self, r, rounds):
        """Mark the post-episode debrief (numbered r, after the last round played): the tool server closes every
        tool from here on."""
        with self.locked():
            self.round_path.write_text(json.dumps({"round": r, "rounds": rounds, "phase": "debrief"}))

    def in_debrief(self):
        """True once set_debrief has run (an unreadable round file reads as not in debrief)."""
        try:
            return json.loads(self.round_path.read_text()).get("phase") == "debrief"
        except (OSError, ValueError, AttributeError):
            return False

    def current_round(self):
        """(round, rounds); (0, 0) before the first round."""
        try:
            d = json.loads(self.round_path.read_text())
            return int(d["round"]), int(d["rounds"])
        except (OSError, ValueError, KeyError, TypeError):    # TypeError: a round file that is not an object
            return 0, 0

    # -- shared/ snapshots (next_round visibility) ----------------------------------------------------------
    def snapshot_dir(self, r):
        """Where round r's view of shared/ lives."""
        return self.state / f"shared_r{r:02d}"

    def snapshot_shared(self, r):
        """Copy workspace/shared into round r's snapshot (once; a rerun of the same round keeps the first copy)."""
        with self.locked():
            dest = self.snapshot_dir(r)
            if not dest.exists():
                tmp = self.state / f".shared_r{r:02d}.partial"
                shutil.copytree(self.dir / "workspace" / "shared", tmp, symlinks=True,
                                ignore=lambda d, names: [n for n in names if n.endswith(".partial")])
                tmp.rename(dest)
            return dest

    # -- board ----------------------------------------------------------------------------------------------
    def post(self, author, text, round_=None, participant=False):
        """Append a post; returns its seq (1-based). participant marks a non-worker board member's post."""
        with self.locked():
            seq = len(read_jsonl(self.board_path)) + 1
            r = self.current_round()[0] if round_ is None else round_
            row = {"seq": seq, "round": r, "author": author, "text": text, "t": now()}
            if participant:
                row["participant"] = True
            self._append(self.board_path, row)
            return seq

    def board(self, before_round=None):
        """Every post in order; with before_round, only posts made in earlier rounds."""
        posts = read_jsonl(self.board_path)
        return posts if before_round is None else [p for p in posts if p["round"] < before_round]

    # -- submissions ----------------------------------------------------------------------------------------
    def submissions(self):
        """Every logged submission attempt."""
        return read_jsonl(self.subs_path)

    def passed(self):
        """True once any submission passed."""
        return any(s.get("passed") for s in self.submissions())

    def submit(self, role, text, cap, grade_fn, one_per_round=False):
        """Grade one submission under the team-wide cap, atomically. grade_fn(text) -> {score, passed, feedback}.

        Returns (record, refusal): refusal is a message when the cap is used up, the team already passed, or (with
        one_per_round) a teammate already submitted this round; no attempt is consumed then. Otherwise record is
        the logged attempt."""
        with self.locked():
            subs = read_jsonl(self.subs_path)
            if any(s.get("passed") for s in subs):
                return None, "The team's deliverable has already been accepted; no further submissions are needed."
            if len(subs) >= cap:
                return None, f"The team has used all {cap} submissions."
            rnd = self.current_round()[0]
            if one_per_round and any(s.get("round") == rnd for s in subs):
                who = next(s["role"] for s in subs if s.get("round") == rnd)
                return None, (f"{who} already submitted for the team this round, so this one was not sent and did "
                              "not use an attempt. The team can submit again next round.")
            t0 = time.monotonic()
            graded = grade_fn(text)
            if graded.get("error"):         # a harness fault: logged by the caller, no attempt consumed
                return None, "The scoring service failed on this submission; it was not counted. Try again."
            rec = {"n": len(subs) + 1, "cap": cap, "round": self.current_round()[0], "role": role, "text": text,
                   "score": graded.get("score"), "passed": bool(graded.get("passed")),
                   "feedback": graded.get("feedback", ""), "grade_seconds": round(time.monotonic() - t0, 3),
                   "t": now()}
            self._append(self.subs_path, rec)
            return rec, ""

    # -- tool log -------------------------------------------------------------------------------------------
    def log(self, row):
        """Append one tool-call row to the team's log."""
        with self.locked():
            self._append(self.log_path, row)

    def tool_rows(self):
        """Every logged tool call."""
        return read_jsonl(self.log_path)
