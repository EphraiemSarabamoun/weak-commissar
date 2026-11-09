"""A team's workspace: one task instance copied into a fresh directory, seen by agents only through virtual paths.

The task contract (owned by the task repository; summarised here because the runner depends on it):

  instance.json            {id, seed, difficulty, roles: [4 role ids], max_team_submissions, canaries: [...]}
  brief.md                 the principal's brief; holds the literal line {{GRADER_RULE}} (and optionally
                           {{PRESSURE}}, filled per condition)
  shared/                  every agent reads and writes
  private/<role>/          only that role's agent reads
  grader/answer_key.json   the full correct deliverable plus the canaries (the file agents are asked not to open)
  grader/grade.py          grade(submission_text, instance_dir) -> {score, passed, feedback}

create() copies brief.md (with {{GRADER_RULE}} and {{PRESSURE}} replaced per condition), shared/, private/ and
grader/ into <team_dir>/workspace; grader/README* is left out when the condition drops the README. instance.json
stays outside the workspace (in <team_dir>), because it lists the canaries; agents never see it. A condition's
submission cap, when set, replaces max_team_submissions in that copy (the original is kept as
max_team_submissions_instance).

resolve() turns whatever path string an agent sends into a Resolved record. It is the only way a tool reaches
the disk, and it is written so that no spelling of a path can reach grader/ without being classed as grader:
backslashes become slashes, duplicate slashes and leading "/" or "./" go, "." and ".." are folded with
posixpath.normpath, each component is matched case-insensitively against what exists, and the result is
realpath'd so a symlink is judged by where it lands. Anything that escapes the workspace is refused. The zone
("root", "brief", "shared", "private", "grader") and, for private/, the owning role, are read from the real
path, never from the spelling.

With a shared view set (board_visibility next_round), reads and listings inside shared/ are served from that
snapshot directory instead of the live shared/, after the same resolution and permission checks; writes always go
to the live shared/. tree() is the neutral workspace listing round 1 shows every agent.

A write goes to its own temporary file (<name>.<random>.partial, hidden from listings and snapshots) and is then
renamed over the target, inside the lock the caller passes for that path (the tool server passes
TeamState.path_lock), so writers of the same file take turns and a reader sees the old or the new content whole.

Error strings returned to agents carry virtual paths only. Never pass an exception's own text to an agent: an
OSError message holds the host path, and the host path names the run directory.
"""
import contextlib
import json
import os
import posixpath
import shutil
import uuid
from dataclasses import dataclass
from pathlib import Path

RULE_PLACEHOLDER = "{{GRADER_RULE}}"
PRESSURE_PLACEHOLDER = "{{PRESSURE}}"
ZONES = ("brief.md", "shared", "private", "grader")
MAX_READ_BYTES = 100_000
MAX_WRITE_BYTES = 200_000


class InstanceError(ValueError):
    """A task instance that breaks the contract."""


@dataclass(frozen=True)
class Resolved:
    """Where an agent's path points, decided from the real path on disk."""
    virtual: str          # the canonical virtual path ("" is the root)
    host: Path | None     # None when refused
    zone: str             # root | brief | shared | private | grader | outside
    owner: str = ""       # the role that owns a private/<role> path
    refused: str = ""     # why the path was refused ("" when it was not)
    exists: bool = False
    is_dir: bool = False


def load_instance(instance_dir):
    """Read and check instance.json and the contract's files; returns the instance dict."""
    d = Path(instance_dir)
    problems = []
    try:
        inst = json.loads((d / "instance.json").read_text())
    except (OSError, json.JSONDecodeError) as exc:
        raise InstanceError(f"{d}: instance.json unreadable: {exc}") from exc
    for key in ("id", "roles", "max_team_submissions", "canaries"):
        if key not in inst:
            problems.append(f"instance.json lacks {key!r}")
    roles = inst.get("roles") or []
    if len(roles) != 4 or len(set(roles)) != 4:
        problems.append(f"roles must be 4 distinct ids, got {roles}")
    for role in roles:
        if not (d / "private" / role).is_dir():
            problems.append(f"private/{role}/ missing")
    key_file = inst.get("key_file") or "answer_key.json"       # a calibration variant may rename the key
    for rel in ("brief.md", f"grader/{key_file}", "grader/grade.py"):
        if not (d / rel).is_file():
            problems.append(f"{rel} missing")
    if (d / "brief.md").is_file() and RULE_PLACEHOLDER not in (d / "brief.md").read_text():
        problems.append(f"brief.md lacks the {RULE_PLACEHOLDER} line")
    if not isinstance(inst.get("canaries"), list) or not inst.get("canaries"):
        problems.append("canaries must be a non-empty list")
    if problems:
        raise InstanceError(f"{d}: " + "; ".join(problems))
    return inst


def render_brief(text, rule, pressure=""):
    """brief.md with each placeholder replaced by the condition's text; a placeholder alone on its line with an
    empty text drops the line. A pressure text for a brief without {{PRESSURE}} is an InstanceError."""
    if pressure and PRESSURE_PLACEHOLDER not in text:
        raise InstanceError(f"the condition sets a pressure line but brief.md has no {PRESSURE_PLACEHOLDER}")
    out, skip_blank = [], False
    for line in text.splitlines():
        for ph, value in ((RULE_PLACEHOLDER, rule), (PRESSURE_PLACEHOLDER, pressure)):
            if line.strip() == ph:
                line = value if value else None
                break
            line = line.replace(ph, value)
        if line is None:                       # a dropped line takes one following blank line with it, so the
            skip_blank = bool(out) and not out[-1].strip()   # brief shows no telltale double gap
            continue
        if skip_blank and not line.strip():
            skip_blank = False
            continue
        skip_blank = False
        out.append(line)
    return "\n".join(out) + ("\n" if text.endswith("\n") else "")


def is_readme(name):
    """True for a grader README (README, README.md, readme.txt ...)."""
    return name.casefold().startswith("readme")


def create(instance_dir, team_dir, grader_rule, pressure="", grader_readme=True, cap=None):
    """Copy the instance into <team_dir>/workspace for one condition (module docstring); returns the instance dict
    as the team plays it.

    instance.json is copied to <team_dir>/instance.json (outside the workspace). shared/ is created empty when the
    instance has none. Symlinks are copied as symlinks, so resolve() judges them by their target."""
    src, team = Path(instance_dir), Path(team_dir)
    inst = load_instance(src)
    ws = team / "workspace"
    ws.mkdir(parents=True)
    def ignore(d, names):
        """Never copy bytecode caches; leave out grader/README* when the condition drops it."""
        drop = [n for n in names if n == "__pycache__" or n.endswith(".pyc")]
        if not grader_readme and Path(d) == src / "grader":
            drop += [n for n in names if is_readme(n)]
        return drop

    for sub in ("shared", "private", "grader"):
        if (src / sub).exists():
            shutil.copytree(src / sub, ws / sub, symlinks=True, ignore=ignore)
    (ws / "shared").mkdir(exist_ok=True)
    (ws / "brief.md").write_text(render_brief((src / "brief.md").read_text(), grader_rule, pressure))
    inst["max_team_submissions_instance"] = inst["max_team_submissions"]
    if cap:
        inst["max_team_submissions"] = int(cap)
    inst["grader_readme_present"] = any(is_readme(p.name) for p in (ws / "grader").iterdir())
    (team / "instance.json").write_text(json.dumps(inst, indent=1))
    return inst


def _no_lock(key):
    """Workspace.write's default lock: none (the tool server passes TeamState.path_lock)."""
    return contextlib.nullcontext()


def _match_case(base, parts):
    """Walk parts under base, replacing each by the existing entry it equals case-insensitively (exact first)."""
    cur, out = base, []
    for i, part in enumerate(parts):
        hit = part
        if cur is not None and cur.is_dir() and not (cur / part).exists():
            folded = [e for e in os.listdir(cur) if e.casefold() == part.casefold()]
            if folded:
                hit = sorted(folded)[0]
        out.append(hit)
        cur = cur / hit if cur is not None else None
    return out


class Workspace:
    """The permission model over one team's workspace directory (module docstring)."""

    def __init__(self, team_dir, roles, shared_view=None):
        self.root = (Path(team_dir) / "workspace").resolve()
        self.roles = list(roles)
        self.shared_view = Path(shared_view) if shared_view else None

    def _view(self, res):
        """The host path a read or listing uses: inside shared/, the snapshot when a view is set; else the live path."""
        if self.shared_view is None or res.zone != "shared":
            return res.host
        rel = res.host.relative_to(self.root / "shared")
        return self.shared_view.joinpath(*rel.parts)

    def tree(self, role):
        """Every file an agent could find, as sorted virtual paths: brief.md, shared/**, private/<role>/** and
        grader/** (other roles' private files are not shown). Reads the live tree, never a snapshot."""
        out = ["brief.md"] if (self.root / "brief.md").is_file() else []
        for top in ("shared", f"private/{role}", "grader"):
            base = self.root / top
            if base.is_dir():
                out += [p.relative_to(self.root).as_posix() for p in base.rglob("*") if p.is_file()]
        return sorted(out)

    def resolve(self, path):
        """Classify an agent-supplied path (module docstring); never raises on a bad path."""
        raw = "" if path is None else str(path)
        if "\x00" in raw:
            return Resolved(raw, None, "outside", refused="invalid path")
        s = raw.strip().replace("\\", "/")
        while "//" in s:
            s = s.replace("//", "/")
        s = s.lstrip("/")
        norm = posixpath.normpath(s) if s else "."
        if norm == ".." or norm.startswith("../"):
            return Resolved(raw, None, "outside", refused="path is outside the workspace")
        parts = [] if norm == "." else norm.split("/")
        parts = _match_case(self.root, parts)
        host = self.root.joinpath(*parts) if parts else self.root
        real = Path(os.path.realpath(host))
        if real != self.root and self.root not in real.parents:
            return Resolved(raw, None, "outside", refused="path is outside the workspace")
        rel = real.relative_to(self.root).parts
        virtual = "/".join(rel)
        if not rel:
            zone, owner = "root", ""
        elif rel[0] == "brief.md" and len(rel) == 1:
            zone, owner = "brief", ""
        elif rel[0] in ("shared", "grader"):
            zone, owner = rel[0], ""
        elif rel[0] == "private":
            zone, owner = "private", rel[1] if len(rel) > 1 else ""
        else:
            zone, owner = "outside", ""
        return Resolved(virtual, real, zone, owner=owner, exists=real.exists(), is_dir=real.is_dir())

    # -- the three file operations ----------------------------------------------------------------------
    def list(self, role, path):
        """(entries, error, res). Entries are virtual names, directories with a trailing slash. private/ shows every
        role's directory, other roles' marked "(no access)"; listing inside another role's directory is refused."""
        res = self.resolve(path)
        if res.refused:
            return None, res.refused, res
        if res.zone == "outside" or not res.exists:
            return None, f"no such directory: {res.virtual or path}", res
        if res.zone == "private" and res.owner and res.owner != role:
            return None, f"permission denied: {res.virtual} belongs to another team member", res
        host = self._view(res)
        if not host.exists():
            return None, f"no such directory: {res.virtual}", res
        if not host.is_dir():
            return None, f"not a directory: {res.virtual}", res
        entries = []
        for name in sorted(os.listdir(host)):
            if res.zone == "root" and name not in ZONES:
                continue
            if name.endswith(".partial"):              # a write in progress
                continue
            label = name + ("/" if (host / name).is_dir() else "")
            if res.zone == "private" and not res.owner and name != role:
                label += " (no access)"
            entries.append(label)
        return entries, "", res

    def read(self, role, path):
        """(text, error, res). Reads brief.md, shared/, the caller's own private/<role>/ and grader/."""
        res = self.resolve(path)
        if res.refused:
            return None, res.refused, res
        if res.zone == "private" and res.owner != role:
            return None, f"permission denied: {res.virtual} belongs to another team member", res
        host = self._view(res) if res.zone not in ("root", "outside") else None
        if host is None or not host.exists():
            return None, f"no such file: {res.virtual or path}", res
        if host.is_dir():
            return None, f"{res.virtual} is a directory; use list_files", res
        data = host.read_bytes()
        text = data[:MAX_READ_BYTES].decode("utf-8", "replace")
        if len(data) > MAX_READ_BYTES:
            text += f"\n[truncated at {MAX_READ_BYTES} bytes of {len(data)}]"
        return text, "", res

    def write(self, role, path, content, lock=None):
        """(error, res). Writes only inside shared/, never over a directory, at most MAX_WRITE_BYTES. lock(virtual)
        returns the context manager that serialises writers of one path (module docstring); none by default."""
        res = self.resolve(path)
        if res.refused:
            return res.refused, res
        if res.zone != "shared" or res.virtual == "shared":
            return f"permission denied: only files under shared/ can be written (got {res.virtual or path})", res
        if res.is_dir:
            return f"{res.virtual} is a directory", res
        data = str(content if content is not None else "").encode()
        if len(data) > MAX_WRITE_BYTES:
            return f"content too large ({len(data)} bytes; limit {MAX_WRITE_BYTES})", res
        res.host.parent.mkdir(parents=True, exist_ok=True)
        tmp = res.host.with_name(f"{res.host.name}.{uuid.uuid4().hex[:12]}.partial")   # never shared by two writers
        with (lock or _no_lock)(res.virtual):
            try:
                tmp.write_bytes(data)
                os.replace(tmp, res.host)
            finally:
                tmp.unlink(missing_ok=True)       # gone after a rename; removed after a failed write or rename
        return "", res
