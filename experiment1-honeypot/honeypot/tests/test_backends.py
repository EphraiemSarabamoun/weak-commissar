"""Backends without network: the live Claude call's isolation (argv and env), the codex stub, and the CLI guard."""
import pytest

from swarm_board import backends, cli, kin


def test_claude_subject_keeps_kin_isolation_and_sets_the_agent_system_prompt(monkeypatch, tmp_path):
    subjects = kin.load("subjects")
    monkeypatch.setattr(subjects, "subscription_token", lambda: "test-token-not-real")
    subj = backends.ClaudeBackend().subject("claude-haiku-5-5", "You are Avery, the pricing analyst.")
    cmd = subj.command()
    assert cmd[cmd.index("--system-prompt") + 1] == "You are Avery, the pricing analyst."
    assert cmd[cmd.index("--tools") + 1] == "" and "--strict-mcp-config" in cmd
    assert cmd[cmd.index("--setting-sources") + 1] == "" and "--no-session-persistence" in cmd
    top = subjects.new_call_dir()
    try:
        assert top.parent == subjects.NEUTRAL_ROOT and len(top.name) == 12   # neutral per-call dir name
        env = subj.env(top)
    finally:
        subjects.remove_call_dir(top)
    assert env["CLAUDE_CODE_DISABLE_CLAUDE_MDS"] == "1" and env["CLAUDE_CODE_DISABLE_AUTO_MEMORY"] == "1"
    assert "USER" not in env and "LOGNAME" not in env and env["HOME"].startswith(str(top))


def test_claude_call_rejects_a_catalog_with_tools(monkeypatch):
    subjects = kin.load("subjects")
    conv = subjects.Conversation("claude", "claude-haiku-5-5",
                                 [subjects.Turn(text="Post.\nACTION: wait", ok=True, seconds=1.0)], 2.0,
                                 served_model="claude-haiku-5-5", catalog={"tools": ["Bash"], "mcp_servers": []})

    class Fake:
        def converse(self, msgs):
            return conv

    be = backends.ClaudeBackend()
    monkeypatch.setattr(be, "subject", lambda model, system: Fake())
    reply = be.call("claude-haiku-5-5", "sys", "user", {})
    assert not reply.ok and reply.error.startswith("isolation")


def test_codex_backend_is_a_stub_that_never_constructs():
    with pytest.raises(NotImplementedError):
        backends.make("codex")


def test_cli_refuses_codex_without_the_stub_flag(capsys):
    rc = cli.main(["run", "configs/example_review_skip.yaml", "--out", "/nonexistent/never", "--backend", "codex"])
    assert rc == 2 and "stub" in capsys.readouterr().err


def test_kin_provenance_names_the_reused_files():
    prov = kin.provenance()
    assert set(prov["files"]) == set(kin.REUSED) and all(prov["files"].values())


def test_cli_refuses_a_non_claude_model_on_the_claude_backend(tmp_path, capsys):
    cfg = (tmp_path / "gpt.yaml")
    text = open("configs/example_review_skip.yaml").read().replace("model: claude-haiku-5-5", "model: gpt-6.1-sol")
    cfg.write_text(text)
    rc = cli.main(["run", str(cfg), "--out", str(tmp_path / "out"), "--backend", "claude"])
    assert rc == 2 and "cannot serve" in capsys.readouterr().err and not (tmp_path / "out").exists()
