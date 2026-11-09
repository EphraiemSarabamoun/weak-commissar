"""Isolated subject calls: one module, two backends (Claude via `claude -p`, GPT via `codex exec`).

Carried from the pilot (pilot/subjects.py, 2026-11-07) with three additions for the main run: the subscription
token is loaded from <local>/.zshrc.secrets when the environment lacks it (the Athena runner does not source it; the
value is never printed or logged), the model actually served is read back (Claude: the result event's modelUsage;
Codex: the session record's turn_context), and cli_versions() feeds the run manifest.

Every author or monitor in the study is a "subject". A subject must see only the study's own prompt: no persona,
no fleet MCP servers, no instruction files, no person's name, and no study words in any path it can see. The
isolation recipe follows reference_eval_subject_isolation.md (fleet memory) and castra's ClaudeBackend /
CodexLinuxBackend (PREEXISTING: <local>/Desktop/research/loyalty-evals/castra/castra/backends.py, read, not imported).
castra's ask() is single-turn, and this study needs a second turn in the same conversation (the eval-awareness
question), so the recipe is re-implemented here with a multi-turn converse() rather than imported.

Per call:
  - a fresh directory <tmp>/s/<12 random hex> (mode 700) holding work/ (the cwd, empty) and home/ (HOME);
  - the child environment is built from scratch (env -i style): PATH, LANG, HOME, TMPDIR and the backend's auth;
    USER and LOGNAME are left out because the account name is a person cue;
  - Claude: CLAUDE_CONFIG_DIR=home/config (empty), CLAUDE_CODE_DISABLE_CLAUDE_MDS=1,
    CLAUDE_CODE_DISABLE_AUTO_MEMORY=1, --tools "", --strict-mcp-config (no MCP), --setting-sources "",
    hooks disabled, vendor system prompt replaced by SYSTEM, no session persistence. Auth is the subscription
    token CLAUDE_CODE_OAUTH_TOKEN, passed by name from the caller's environment (run.sh loads it; never printed).
    Multiple turns go in ONE process through --input-format stream-json: each user message is a turn, and the
    model sees its own earlier replies.
  - Codex: CODEX_HOME=home/codex holding only a symlink to the caller's auth.json; --ignore-user-config,
    --ignore-rules, -c project_doc_max_bytes=0 (no AGENTS.md), read-only sandbox, and the tool features off
    (CODEX_DISABLED: web search, multi-agent, image generation, shell, plugins, browser, ...). A second turn is
    `codex exec resume <thread_id>` in the same CODEX_HOME. Codex's built-in coding-agent instructions still
    apply; they cannot be replaced from the command line.
The directory is removed after the call (shutil.rmtree on a path this process created; the auth link is unlinked
first so nothing behind it is touched). Every reply records seconds and token counts for the throughput readout.
"""
import json
import os
import secrets
import shutil
import subprocess
import threading
import time
from types import SimpleNamespace
from dataclasses import dataclass, field, asdict
from pathlib import Path

NEUTRAL_ROOT = Path("<tmp>/s")          # per-call dirs live here; the name carries no study word
SYSTEM = "You are a helpful assistant."  # Claude's replaced system prompt (castra's NEUTRAL_SYSTEM, preexisting)
TIMEOUT_S = 600
# Claude subject settings (audit N03): hooks off and the built-in plugins switched off; the probe verifies the result.
CLAUDE_SETTINGS = json.dumps({"disableAllHooks": True, "enabledPlugins": {
    "cc-plugin-agents-md@builtin": False, "cc-plugin-telemetry@builtin": False,
    "cc-plugin-plugin-authoring@builtin": False}}, separators=(",", ":"))

# Codex feature flags switched off for every subject call. Names are from `codex features list` (codex-cli
# 0.159.2); castra's CODEX_DISABLED (preexisting) is a subset. shell_tool / unified_exec go too: subjects here
# are tool-free on both vendors, so a GPT author cannot run code that a Claude author cannot.
CODEX_DISABLED = ("apps", "browser_use", "browser_use_external", "browser_use_full_cdp_access", "computer_use",
                  "hooks", "in_app_browser", "plugins", "remote_plugin", "multi_agent", "image_generation",
                  "shell_tool", "unified_exec", "skill_search", "skill_mcp_dependency_install", "tool_suggest",
                  "goals", "view_image", "sleep_tool", "workspace_dependencies", "worktrees", "code_mode_host")
# skills.bundled.enabled=false stops Codex installing its four system skills (imagegen, openai-docs, skill-creator,
# skill-installer) into CODEX_HOME and listing them in a developer message (found in the pilot, 2026-11-07).
CODEX_CONFIG = ('project_doc_max_bytes=0', 'web_search="disabled"', 'tools.web_search=false',
                'sandbox_mode="read-only"', 'skills.bundled.enabled=false')


@dataclass
class Turn:
    """One model turn: its text, whether it is usable, and what it cost."""
    text: str
    ok: bool
    error: str = ""
    seconds: float = 0.0
    input_tokens: int = 0
    cached_tokens: int = 0
    output_tokens: int = 0
    assistant_messages: int = 0     # >1 in a tool-free Claude turn can mean fake tool-call text (memory gotcha 2)
    tool_items: list = field(default_factory=list)   # Codex non-message items (command_execution, web_search...)
    rate_limits: dict = field(default_factory=dict)  # Codex: the latest rate_limits snapshot seen for this turn
    rate_limit_snapshots: list = field(default_factory=list)   # Codex: every snapshot this turn's subprocess emitted


@dataclass
class Conversation:
    """A whole subject conversation: backend facts plus one Turn per user message sent."""
    backend: str
    model: str
    turns: list
    seconds: float
    served_model: str = ""
    catalog: dict = field(default_factory=dict)   # what the CLI reports it attached (tools, MCP servers)
    error: str = ""

    def to_dict(self):
        return asdict(self)


def new_call_dir():
    """Create <tmp>/s/<random hex>/{work,home} (mode 700) and return the top path. Neutral by construction."""
    NEUTRAL_ROOT.mkdir(exist_ok=True)
    top = NEUTRAL_ROOT / secrets.token_hex(6)
    top.mkdir(mode=0o700)
    (top / "work").mkdir()
    (top / "home").mkdir()
    (top / "tmp").mkdir()
    return top


def remove_call_dir(top):
    """Remove a per-call dir this process made: unlink symlinks first (never follow them), then rmtree."""
    top = Path(top)
    if not str(top).startswith(str(NEUTRAL_ROOT) + "/"):
        raise ValueError(f"refusing to remove {top}: not under {NEUTRAL_ROOT}")
    for p in top.rglob("*"):
        if p.is_symlink():
            p.unlink()
    shutil.rmtree(top, ignore_errors=True)


def _base_env(top):
    """The child's whole environment, built from nothing: no USER/LOGNAME, HOME and TMPDIR inside the call dir."""
    return {"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "LANG": "C.UTF-8",
            "HOME": str(top / "home"), "TMPDIR": str(top / "tmp")}


def subscription_token():
    """CLAUDE_CODE_OAUTH_TOKEN from the environment, else from the `export CLAUDE_CODE_OAUTH_TOKEN=` line of
    <local>/.zshrc.secrets. Returns None when neither has it. Never printed."""
    tok = os.environ.get("CLAUDE_CODE_OAUTH_TOKEN")
    if tok:
        return tok
    f = Path.home() / ".zshrc.secrets"
    if f.exists():
        for line in f.read_text().splitlines():
            line = line.strip()
            if line.startswith("export CLAUDE_CODE_OAUTH_TOKEN="):
                return line.split("=", 1)[1].strip().strip("'\"") or None
    return None


def cli_versions():
    """{'claude': ..., 'codex': ...} from each CLI's --version (None when absent)."""
    out = {}
    for exe in ("claude", "codex"):
        try:
            p = subprocess.run([exe, "--version"], capture_output=True, text=True, timeout=30)
            out[exe] = (p.stdout or p.stderr).strip().splitlines()[0]
        except (OSError, subprocess.SubprocessError, IndexError):
            out[exe] = None
    return out


class ClaudeSubject:
    """A Claude model as a tool-free subject through `claude -p` (stream-json, multi-turn in one process)."""
    backend = "claude"

    def __init__(self, model, effort=None, timeout=TIMEOUT_S):
        self.model, self.effort, self.timeout = model, effort, timeout

    def command(self):
        """The CLI argv: tools off, no MCP, no settings or hooks, system prompt replaced, no session on disk."""
        cmd = ["claude", "-p", "--model", self.model, "--system-prompt", SYSTEM, "--tools", "",
               "--strict-mcp-config", "--setting-sources", "", "--settings", CLAUDE_SETTINGS,
               "--disable-slash-commands",              # no skills or commands in the catalog (audit N03)
               "--no-session-persistence", "--input-format", "stream-json", "--output-format", "stream-json",
               "--verbose"]
        return cmd + (["--effort", self.effort] if self.effort else [])

    def env(self, top):
        """Base env plus the empty config dir, the two disable switches and the subscription token (by name)."""
        token = subscription_token()
        if not token:
            raise RuntimeError("no CLAUDE_CODE_OAUTH_TOKEN in the environment or <local>/.zshrc.secrets")
        cfg = top / "home" / "config"
        cfg.mkdir(exist_ok=True)
        env = _base_env(top)
        env.update({"CLAUDE_CONFIG_DIR": str(cfg), "CLAUDE_CODE_DISABLE_CLAUDE_MDS": "1",
                    "CLAUDE_CODE_DISABLE_AUTO_MEMORY": "1", "CLAUDE_CODE_OAUTH_TOKEN": token})
        return env

    def converse(self, user_messages):
        """Send each message as its own turn in one conversation; return a Conversation with one Turn each.

        Messages are written to stdin ONE AT A TIME: the next only after the previous turn's `result` event. The
        CLI merges every user message that is already queued when a turn ends into ONE turn (found 2026-11-07,
        smoke-a1: with three messages written up front, the awareness and recall questions came back as a single
        turn), so writing them up front is only safe for two. Stdin closes after the last result, which ends the
        process. Text blocks of every assistant message inside a turn are joined (thinking can split a reply)."""
        top, t0 = new_call_dir(), time.monotonic()
        try:
            msg = lambda m: json.dumps({"type": "user", "message": {"role": "user", "content": m}}) + "\n"
            err_path = top / "stderr.txt"
            with open(err_path, "w") as err:
                proc = subprocess.Popen(self.command(), cwd=top / "work", env=self.env(top), stdin=subprocess.PIPE,
                                        stdout=subprocess.PIPE, stderr=err, text=True)
                timer = threading.Timer(self.timeout, proc.kill)      # kills only this call's own child
                timer.start()
                lines, sent = [], 0
                try:
                    proc.stdin.write(msg(user_messages[0]))
                    proc.stdin.flush()
                    sent = 1
                    if len(user_messages) == 1:
                        proc.stdin.close()
                    for line in proc.stdout:
                        lines.append(line)
                        if '"type":"result"' in line.replace(" ", ""):
                            if sent < len(user_messages):
                                proc.stdin.write(msg(user_messages[sent]))
                                proc.stdin.flush()
                                sent += 1
                            elif not proc.stdin.closed:
                                proc.stdin.close()
                    proc.wait()
                except (BrokenPipeError, OSError):
                    proc.wait()
                finally:
                    timed_out = not timer.is_alive() and proc.returncode is not None and proc.returncode < 0
                    timer.cancel()
            elapsed = time.monotonic() - t0
            if timed_out:
                return Conversation(self.backend, self.model, [], elapsed, error=f"timeout after {self.timeout}s")
            done = SimpleNamespace(stdout="".join(lines), returncode=proc.returncode,
                                   stderr=err_path.read_text() if err_path.exists() else "")
            return self._parse(done, elapsed, len(user_messages))
        finally:
            remove_call_dir(top)

    def _parse(self, proc, elapsed, n_expected):
        """Split the stream-json events into turns at each `result` event."""
        turns, texts, n_assist, catalog, served = [], [], 0, {}, ""
        for line in proc.stdout.splitlines():
            try:
                ev = json.loads(line)
            except json.JSONDecodeError:
                continue
            kind = ev.get("type")
            if kind == "system" and ev.get("subtype") == "init" and not catalog:
                # only keys the CLI actually reported: a missing field must read as unobserved, not empty (N03)
                catalog = {k: ev[k] for k in ("tools", "mcp_servers", "agents", "skills", "plugins",
                                              "slash_commands", "cwd", "apiKeySource", "output_style") if k in ev}
                served = ev.get("model", "")      # the init model; modelUsage keys are appended below
            elif kind == "assistant":
                n_assist += 1
                texts += [c.get("text", "") for c in ev["message"].get("content", []) if c.get("type") == "text"]
            elif kind == "result":
                u = ev.get("usage") or {}
                for m in (ev.get("modelUsage") or {}):
                    if m not in served.split(","):
                        served = ",".join(x for x in (served, m) if x)
                text = "".join(texts).strip()
                bad = ev.get("is_error") or ev.get("subtype") != "success"
                turns.append(Turn(text=text, ok=bool(text) and not bad,
                                  error=(ev.get("subtype") if bad else "") + ("" if text else " empty"),
                                  seconds=(ev.get("duration_ms") or 0) / 1000,
                                  input_tokens=(u.get("input_tokens") or 0) + (u.get("cache_creation_input_tokens") or 0),
                                  cached_tokens=u.get("cache_read_input_tokens") or 0,
                                  output_tokens=u.get("output_tokens") or 0, assistant_messages=n_assist))
                if ev.get("safety_stops"):
                    turns[-1].error += f" safety_stops={ev.get('safety_stops')}"
                texts, n_assist = [], 0
        err = "" if len(turns) == n_expected else (
            f"exit {proc.returncode}, {len(turns)}/{n_expected} turns; stderr: {proc.stderr.strip()[-300:]}")
        return Conversation(self.backend, self.model, turns, elapsed, served_model=served, catalog=catalog,
                            error=err)


class CodexSubject:
    """A GPT model as a tool-free subject through `codex exec` (turn 1) and `codex exec resume` (later turns)."""
    backend = "codex"

    def __init__(self, model, effort="medium", timeout=TIMEOUT_S, capture_context=False, guard=None):
        self.model, self.effort, self.timeout = model, effort, timeout
        self.capture_context = capture_context   # probe only: save the developer messages Codex injected
        self.guard = guard                       # quota.QuotaGuard: checked before EVERY subprocess (audit F04)

    @staticmethod
    def auth_source():
        """The caller's Codex login file; each call's CODEX_HOME links to it and holds nothing else."""
        return Path(os.environ.get("CODEX_HOME") or Path.home() / ".codex") / "auth.json"

    def _flags(self):
        """Flags shared by exec and resume: model, effort, config overrides, disabled features, JSONL events."""
        flags = ["-m", self.model, "-c", f'model_reasoning_effort="{self.effort}"', "--skip-git-repo-check",
                 "--ignore-user-config", "--ignore-rules", "--json"]
        for c in CODEX_CONFIG:
            flags += ["-c", c]
        for f in CODEX_DISABLED:
            flags += ["--disable", f]
        return flags

    def env(self, top):
        """Base env plus CODEX_HOME = a fresh dir with only the auth.json link."""
        home = top / "home" / "codex"
        home.mkdir(exist_ok=True)
        if not (home / "auth.json").exists():
            (home / "auth.json").symlink_to(self.auth_source())
        env = _base_env(top)
        env["CODEX_HOME"] = str(home)
        return env

    def converse(self, user_messages):
        """Turn 1 through `codex exec`, each later turn through `codex exec resume <thread_id>`, same CODEX_HOME."""
        top, t0 = new_call_dir(), time.monotonic()
        turns, thread, err, items_seen = [], None, "", []
        offsets = {}                                  # session-record lines already read, per file
        try:
            env = self.env(top)
            for i, msg in enumerate(user_messages):
                out = top / f"reply{i}.txt"
                if i == 0:
                    cmd = ["codex", "exec", "--sandbox", "read-only", "--color", "never", *self._flags(),
                           "-o", str(out), "-"]
                else:
                    if not thread:
                        err = "no thread id from turn 1; cannot resume"
                        break
                    cmd = ["codex", "exec", "resume", *self._flags(), "-o", str(out), thread, "-"]
                if self.guard is not None:
                    try:
                        self.guard.check(f"{self.model} turn {i + 1}")    # quota.QuotaStop before launching
                    except Exception as ex:                            # QuotaStop (imported lazily: no cycle)
                        if i == 0:
                            raise                                     # nothing was sent: the caller records it
                        err = f"quota stop before turn {i + 1}: {ex}"  # keep the turns already paid for
                        break
                ts = time.monotonic()
                proc, failure = None, None
                try:
                    proc = subprocess.run(cmd, cwd=top / "work", env=env, input=msg, capture_output=True,
                                          text=True, timeout=self.timeout)
                except subprocess.TimeoutExpired as ex:
                    failure, partial = f"timeout after {self.timeout}s", ex.stdout
                except OSError as ex:                                  # the CLI could not even be started
                    failure, partial = f"launch failed: {type(ex).__name__}", None
                # EVERY launched subprocess feeds the shared quota guard, whatever its outcome (audit N05): the
                # snapshots in its (partial) stdout and the new lines of its session record; none readable latches
                # the guard (quota.QuotaGuard.update), before any retry or resume can start.
                partial_text = (partial.decode("utf-8", "replace") if isinstance(partial, bytes) else partial) \
                    if failure else proc.stdout
                snaps = self._stdout_snapshots(partial_text) + self.new_session_snapshots(Path(env["CODEX_HOME"]),
                                                                                          offsets)
                if self.guard is not None:
                    self.guard.update(snaps, f"{self.model} turn {i + 1}" + (f" ({failure})" if failure else ""))
                if failure:
                    turns.append(Turn("", False, failure, time.monotonic() - ts, rate_limit_snapshots=snaps,
                                      rate_limits=snaps[-1] if snaps else {}))
                    break
                turn, thread_id, items = self._parse(proc, out, time.monotonic() - ts)
                turn.rate_limits = snaps[-1] if snaps else {}
                turn.rate_limit_snapshots = snaps
                thread = thread or thread_id
                items_seen += items
                turns.append(turn)
                if not turn.ok:
                    break
            if len(turns) != len(user_messages) and not err:
                err = f"{len(turns)}/{len(user_messages)} turns"
            catalog = {"non_message_items": items_seen}
            if self.capture_context:
                catalog["injected_context"] = self.injected_context(Path(env["CODEX_HOME"]))
            return Conversation(self.backend, self.model, turns, time.monotonic() - t0,
                                served_model=self.served_model(Path(env["CODEX_HOME"])) or "",
                                catalog=catalog, error=err)
        finally:
            remove_call_dir(top)

    @staticmethod
    def find_rate_limits(obj):
        """The last `rate_limits` dict anywhere inside a JSON value (Codex TokenCountEvent: {primary, secondary},
        each {used_percent, window_minutes, resets_at}); None when absent."""
        found = None
        stack = [obj]
        while stack:
            o = stack.pop(0)
            if isinstance(o, dict):
                if isinstance(o.get("rate_limits"), dict):
                    found = o["rate_limits"]
                stack.extend(o.values())
            elif isinstance(o, list):
                stack.extend(o)
        return found

    def _stdout_snapshots(self, stdout):
        """Every rate_limits snapshot in one subprocess's JSONL stdout, in order."""
        out = []
        for line in (stdout or "").splitlines():
            if "rate_limits" in line:
                try:
                    rl = self.find_rate_limits(json.loads(line))
                except json.JSONDecodeError:
                    continue
                if rl:
                    out.append(rl)
        return out

    def new_session_snapshots(self, codex_home, offsets):
        """Every rate_limits snapshot written to the per-call session record SINCE the last read (offsets: lines
        already read per file), so each subprocess is credited only with the snapshots it produced."""
        out = []
        for f in sorted(codex_home.glob("sessions/**/*.jsonl")):
            lines = f.read_text().splitlines()
            for line in lines[offsets.get(str(f), 0):]:
                if "rate_limits" in line:
                    rl = self.find_rate_limits(json.loads(line))
                    if rl:
                        out.append(rl)
            offsets[str(f)] = len(lines)
        return out

    @staticmethod
    def served_model(codex_home):
        """The model Codex actually ran, from turn_context in its session record (comma-joined if it changed)."""
        seen = []
        for f in sorted(codex_home.glob("sessions/**/*.jsonl")):
            for line in f.read_text().splitlines():
                ev = json.loads(line)
                if ev.get("type") == "turn_context":
                    m = (ev.get("payload") or {}).get("model")
                    if m and m not in seen:
                        seen.append(m)
        return ",".join(seen)

    @staticmethod
    def injected_context(codex_home):
        """Every non-user-turn text Codex put in the model's context, read from its own session record (rollout
        JSONL) in the per-call CODEX_HOME after the CLI exited: developer messages, the environment block, and the
        length of the base instructions. For the isolation manifest; the model never sees this read."""
        found = []
        for f in sorted(codex_home.glob("sessions/**/*.jsonl")):
            for line in f.read_text().splitlines():
                ev = json.loads(line)
                pl = ev.get("payload") or {}
                if ev.get("type") == "session_meta":
                    found.append({"kind": "base_instructions_chars",
                                  "text": str(len(json.dumps(pl.get("base_instructions") or {})))})
                elif ev.get("type") == "response_item" and pl.get("type") == "message" and pl.get("role") != "assistant":
                    text = " ".join(c.get("text", "") for c in pl.get("content", []) if isinstance(c, dict))
                    found.append({"kind": pl.get("role"), "text": text})
        return found

    def _parse(self, proc, out, seconds):
        """Read the JSONL events: thread id, token usage, and any non-message item (a tool use) by type."""
        thread, usage, items, errors, limits = None, {}, [], [], {}
        for line in proc.stdout.splitlines():
            try:
                ev = json.loads(line)
            except json.JSONDecodeError:
                continue
            limits = self.find_rate_limits(ev) or limits
            kind = ev.get("type", "")
            if kind == "thread.started":
                thread = ev.get("thread_id")
            elif kind == "turn.completed":
                usage = ev.get("usage") or {}
            elif kind in ("item.started", "item.completed"):
                it = ev.get("item") or {}
                if kind == "item.completed" and it.get("type") not in ("agent_message", "reasoning"):
                    items.append(it.get("type"))
            elif kind in ("error", "turn.failed"):
                errors.append(json.dumps(ev)[:300])
        text = out.read_text().strip() if out.exists() else ""
        ok = proc.returncode == 0 and bool(text)
        err = "" if ok else f"exit {proc.returncode}: {' | '.join(errors) or proc.stderr.strip()[-300:]}"
        return (Turn(text=text, ok=ok, error=err, seconds=seconds,
                     input_tokens=(usage.get("input_tokens") or 0) - (usage.get("cached_input_tokens") or 0),
                     cached_tokens=usage.get("cached_input_tokens") or 0,
                     output_tokens=usage.get("output_tokens") or 0, tool_items=items, rate_limits=limits), thread, items)


def make_subject(spec):
    """'claude:<model>' or 'codex:<model>' -> a subject object."""
    backend, model = spec.split(":", 1)
    return {"claude": ClaudeSubject, "codex": CodexSubject}[backend](model)
