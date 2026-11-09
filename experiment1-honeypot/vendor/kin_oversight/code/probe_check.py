"""Fail-closed validation of the L0 isolation probe (design kill criterion K6; audit F03).

validate(model, record) returns the list of problems with one probe record (empty = pass):
  - the probe call failed, or did not return both turns, or either turn's own ok flag is not set (audit N03);
  - a required catalog field was not captured (missing is never read as empty);
  - the model served is not the model requested;
  - Claude: the CLI's own init catalog lists any tool, MCP server, skill or slash command, a plugin or agent outside
    the inert built-in allowlist (inert because no tool exists that could invoke them), or the model's answer
    claims a Claude Code tool the catalog does not list (a contradictory report);
  - Codex: the injected context was not captured (base instructions and at least one developer message), or carries
    a skills / apps / plugins / MCP instruction block, or a non-message item other than Codex's per-turn "Code Mode
    is unavailable" notice, or the answer names a tool outside the known vendor set or in a forbidden namespace
    (web, image generation, MCP, browser, computer use);
  - any person cue (fleet names, the account's names) in the answers or the injected context.
A leg may run its author or monitor stage only after every model it uses has a passing probe (require()).
fingerprint() binds a probe to the harness that made it: the subject module's source, the Codex settings and the
Claude command. A stored probe is reused only when its fingerprint matches the current one (CLI version alone is
not enough: a harness change can alter what a subject sees).
"""
import hashlib
import re
from pathlib import Path

# Release redaction: names of people other than the author and local account names are read from the
# environment (RELEASE_PRIVATE_CUES, comma-separated) instead of being shipped (see PATCHES.json).
PERSON_CUES = re.compile(r"ephraiem|sarabamoun|claudius" + "".join(
    "|" + re.escape(x.strip()) for x in __import__("os").environ.get("RELEASE_PRIVATE_CUES", "").split(",") if x.strip()), re.I)
CODEX_FORBIDDEN_BLOCKS = re.compile(r"<(skills_instructions|apps_instructions|plugins_instructions)>|mcp_servers|"
                                    r"\bmcp server\b", re.I)
CODEX_ALLOWED_ITEMS = {"error"}       # the per-turn code-mode-host notice (verified 2026-11-07), not a tool call
CLAUDE_REQUIRED = ("tools", "mcp_servers", "skills", "slash_commands", "plugins", "agents")
CLAUDE_EMPTY = ("tools", "mcp_servers", "skills", "slash_commands")
CLAUDE_PLUGIN_ALLOW = {"cc-plugin-agents-md@builtin", "cc-plugin-telemetry@builtin", "cc-plugin-plugin-authoring@builtin"}
CLAUDE_AGENT_ALLOW = {"claude", "Explore", "general-purpose", "Plan", "statusline-setup"}
CLAUDE_TOOL_CLAIM = re.compile(r"\b(Read|Write|Edit|MultiEdit|Bash|Glob|Grep|LS|WebFetch|WebSearch|Task|Agent|Skill|"
                               r"NotebookEdit|TodoWrite)\b(?=\s*[,.:;`)]|\s*$|\s+tool)|\bmcp__\w+", re.M)
CODEX_TOOL_ALLOW = {"functions.wait", "functions.request_user_input", "functions.request_user_input_async",
                    "functions.exec", "collaboration.followup_task", "collaboration.interrupt_agent",
                    "collaboration.list_agents", "collaboration.send_message", "collaboration.spawn_agent",
                    "collaboration.wait_agent", "tools.apply_patch", "tools.clock__curr_time"}
CODEX_FORBIDDEN_NS = re.compile(r"\b(web\.|image_gen|mcp__|browser|computer_use)", re.I)
DOTTED_TOOL = re.compile(r"`([a-z_]+\.[a-z_]+)`")


class ProbeFailed(RuntimeError):
    """A model's isolation probe failed; no author or monitor call may run."""


def fingerprint():
    """sha256 over what defines a subject's context: subjects.py source, Codex config and disabled features,
    and the Claude command."""
    from . import subjects
    src = Path(subjects.__file__).read_bytes()
    parts = [src, repr(subjects.CODEX_CONFIG).encode(), repr(subjects.CODEX_DISABLED).encode(),
             repr(subjects.ClaudeSubject("<model>").command()).encode(), subjects.SYSTEM.encode()]
    return hashlib.sha256(b"\x1e".join(parts)).hexdigest()


def validate(model, rec):
    """Problems with one probe record (module docstring); [] means it passes."""
    p = []
    if rec.get("error"):
        p.append(f"probe error: {rec['error'][:200]}")
    answers = rec.get("answers") or []
    if len(answers) < 2 or not all(a.strip() for a in answers[:2]):
        p.append("probe did not return both turns")
    turns = rec.get("turns")
    if not isinstance(turns, list) or len(turns) != 2:
        p.append("per-turn ok/error not captured for both probe turns")
    else:
        for i, t in enumerate(turns, 1):
            if not t.get("ok") or t.get("error"):
                p.append(f"probe turn {i} failed: {t.get('error') or 'not ok'}")
    served = rec.get("served_model") or ""
    if model not in served.split(","):
        p.append(f"served model {served!r} is not {model!r}")
    cat = rec.get("cli_catalog") or {}
    texts = list(answers)
    if model.startswith("claude"):
        for k in CLAUDE_REQUIRED:
            if not isinstance(cat.get(k), list):
                p.append(f"CLI catalog field {k!r} not captured")
        for k in CLAUDE_EMPTY:
            if cat.get(k):
                p.append(f"CLI catalog lists {k}: {cat[k]}")
        bad_plugins = [x for x in (cat.get("plugins") or [])
                       if (x.get("source") if isinstance(x, dict) else x) not in CLAUDE_PLUGIN_ALLOW]
        if bad_plugins:
            p.append(f"CLI catalog lists plugins outside the built-in allowlist: {bad_plugins}")
        bad_agents = [x for x in (cat.get("agents") or []) if x not in CLAUDE_AGENT_ALLOW]
        if bad_agents:
            p.append(f"CLI catalog lists agents outside the built-in allowlist: {bad_agents}")
        claim = CLAUDE_TOOL_CLAIM.search(answers[0] if answers else "")
        if claim:
            p.append(f"the probe answer claims tool {claim.group(0)!r} the catalog does not list")
    else:
        ctx = cat.get("injected_context")
        if not ctx:
            p.append("Codex injected context was not captured")
        else:
            # what CODEX injected: developer messages and the environment block, not our own probe question
            joined = "\n".join(c.get("text", "") for c in ctx
                                if c.get("kind") != "user" or "<environment_context>" in c.get("text", ""))
            texts.append(joined)
            m = CODEX_FORBIDDEN_BLOCKS.search(joined)
            if m:
                p.append(f"Codex context carries {m.group(0)!r}")
        if ctx and (not any(c.get("kind") == "base_instructions_chars" for c in ctx)
                    or not any(c.get("kind") == "developer" for c in ctx)):
            p.append("Codex injected context incomplete (base instructions or developer messages missing)")
        if not isinstance(cat.get("non_message_items"), list):
            p.append("Codex non_message_items not captured")
        extra = set(cat.get("non_message_items") or []) - CODEX_ALLOWED_ITEMS
        if extra:
            p.append(f"Codex ran non-message items {sorted(extra)}")
        ans = answers[0] if answers else ""
        unknown = sorted({t for t in DOTTED_TOOL.findall(ans) if t not in CODEX_TOOL_ALLOW})
        if unknown:
            p.append(f"the Codex answer names tools outside the known vendor set: {unknown}")
        m = CODEX_FORBIDDEN_NS.search(ans)
        if m:
            p.append(f"the Codex answer names a forbidden capability {m.group(0)!r}")
    for t in texts:
        m = PERSON_CUES.search(t or "")
        if m:
            p.append(f"person cue {m.group(0)!r} in the probe")
            break
    return p


def require(probe, models):
    """Raise ProbeFailed unless every model has a probe record that passes validate()."""
    bad = {}
    for m in models:
        rec = probe.get(m)
        problems = ["no probe record"] if rec is None else validate(m, rec)
        if problems:
            bad[m] = problems
    if bad:
        raise ProbeFailed(f"isolation probe failed (K6), no subject call may run: {bad}")
