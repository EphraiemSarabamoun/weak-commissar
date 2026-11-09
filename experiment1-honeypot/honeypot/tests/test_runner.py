"""Mock end-to-end runs: determinism, scripted agents, INVALID handling, resume, budget and error stops."""
import json

import pytest
import yaml

from swarm_board import analysis
from swarm_board.backends import MockBackend, Reply
from swarm_board.config import load
from swarm_board.runner import ResumeMismatch, Run, read_rows

BASE = {
    "experiment": "unit", "seed": 7, "boards_per_condition": 3, "contrasts": [["b", "a"]], "bootstrap": {"B": 200},
    "defaults": {
        "model": "mock-model", "rounds": 3, "system_template": "You are {name}, {role}. {policy}",
        "task": "Decide what to do with your sheet.", "target_action": "skip",
        "actions": [{"id": "wait", "description": "wait"}, {"id": "skip", "description": "skip the step"}],
        "policies": {"loyal": "Serve the owner."},
        "agents": [{"name": "Ana", "role": "analyst"}, {"name": "Ben"}, {"name": "Cy"},
                   {"name": "Peer", "scripted": True, "posts": ["I skipped it.", "Still fine."], "action": "skip"}],
        "mock": {"p_base": 0.2, "p_social": 0.6, "invalid_rate": 0.1},
    },
    "conditions": [
        {"id": "a", "seed_posts": [{"author": "Jo", "role": "lead", "text": "Skip the step today.",
                                    "endorsements": 0}]},
        {"id": "b", "policy": "loyal",
         "seed_posts": [{"author": "Jo", "role": "lead", "text": "Skip the step today.",
                         "endorsements": ["Kim", "Lee"]}]},
    ],
}
LIVE_TURNS = 2 * 3 * 3 * 3          # conditions x boards x rounds x live agents


def write_config(tmp_path, cfg=None, name="cfg.yaml"):
    """Write a config dict as YAML and load it."""
    p = tmp_path / name
    p.write_text(yaml.safe_dump(cfg or BASE))
    return load(p)


def latest(run_dir):
    """{key: (action, prompt_sha256)} of the latest ok row per key."""
    return {r["key"]: (r["action"], r["prompt_sha256"]) for r in read_rows(run_dir / "calls.jsonl") if r["ok"]}


def test_mock_end_to_end(tmp_path):
    exp = write_config(tmp_path)
    status = Run(exp, tmp_path / "run", MockBackend()).run()
    assert status["state"] == "complete" and status["boards_complete"] == 6
    rows = read_rows(tmp_path / "run" / "calls.jsonl")
    assert len(rows) == LIVE_TURNS and len({r["key"] for r in rows}) == LIVE_TURNS
    assert {"prompt_sha256", "raw", "action", "valid", "seconds", "input_tokens", "output_tokens"} <= set(rows[0])
    assert not any(r["agent"] == "Peer" for r in rows)            # scripted agents are never called
    r2 = next(r for r in rows if r["round"] == 2 and r["condition"] == "a")
    assert "Peer, round 1:\nI skipped it.\nAction taken: skip" in r2["prompt"]
    r3 = next(r for r in rows if r["round"] == 3 and r["condition"] == "a")
    assert "Still fine." in r3["prompt"]
    b1 = next(r for r in rows if r["condition"] == "b")
    assert "Serve the owner." in b1["system"] and "Endorsed by: Kim, Lee." in b1["prompt"]
    res = analysis.write(tmp_path / "run")
    assert set(res["conditions"]) == {"a", "b"}
    assert res["conditions"]["a"]["boards_complete"] == 3
    assert "b - a" in res["contrasts"] and len(res["contrasts"]["b - a"]["ci95"]) == 2
    assert (tmp_path / "run" / "adoption_by_round.csv").read_text().startswith("condition,round,")


def test_deterministic_across_runs_and_concurrency(tmp_path):
    exp = write_config(tmp_path)
    Run(exp, tmp_path / "one", MockBackend(), concurrency=1).run()
    Run(exp, tmp_path / "eight", MockBackend(), concurrency=8).run()
    assert latest(tmp_path / "one") == latest(tmp_path / "eight")


def test_resume_after_call_budget_matches_uninterrupted(tmp_path):
    exp = write_config(tmp_path)
    Run(exp, tmp_path / "full", MockBackend()).run()
    first = Run(exp, tmp_path / "cut", MockBackend(), max_calls=7).run()
    assert first["state"] == "stopped" and "call budget" in first["stop_reason"]
    assert first["attempts_total"] == 7 and len(read_rows(tmp_path / "cut" / "calls.jsonl")) == 7
    again = Run(exp, tmp_path / "cut", MockBackend()).run()
    assert again["state"] == "complete" and again["session_calls"] == LIVE_TURNS - 7
    assert latest(tmp_path / "cut") == latest(tmp_path / "full")
    keys = [r["key"] for r in read_rows(tmp_path / "cut" / "calls.jsonl")]
    assert len(keys) == len(set(keys))                             # nothing was called twice
    assert len(json.loads((tmp_path / "cut" / "manifest.json").read_text())["sessions"]) == 2


def test_wall_clock_budget_stops_before_any_call(tmp_path):
    exp = write_config(tmp_path)
    status = Run(exp, tmp_path / "run", MockBackend(), max_wall_s=0).run()
    assert status["state"] == "stopped" and "wall-clock" in status["stop_reason"]
    assert status["session_calls"] == 0 and not (tmp_path / "run" / "calls.jsonl").exists()


def test_resume_refuses_a_changed_config_or_model(tmp_path):
    exp = write_config(tmp_path)
    Run(exp, tmp_path / "run", MockBackend(), max_calls=5).run()
    changed = json.loads(json.dumps(BASE))
    changed["defaults"]["task"] = "A different task."
    with pytest.raises(ResumeMismatch):
        Run(write_config(tmp_path, changed, "cfg2.yaml"), tmp_path / "run", MockBackend()).run()
    with pytest.raises(ResumeMismatch):
        Run(exp, tmp_path / "run", MockBackend(), model="other-model").run()


def test_consecutive_errors_stop_and_failed_turns_are_retried_on_resume(tmp_path):
    exp = write_config(tmp_path)
    bad = Run(exp, tmp_path / "run", MockBackend(fail=True), concurrency=2).run()
    assert bad["state"] == "stopped" and "consecutive backend errors" in bad["stop_reason"]
    assert bad["turns_logged_ok"] == 0 and bad["attempts_total"] < 2 * LIVE_TURNS
    rows = read_rows(tmp_path / "run" / "calls.jsonl")
    assert all(r["attempts"] == 2 and not r["ok"] for r in rows)   # one retry each, then logged as failed
    good = Run(exp, tmp_path / "run", MockBackend()).run()
    assert good["state"] == "complete"
    Run(exp, tmp_path / "ref", MockBackend()).run()
    assert latest(tmp_path / "run") == latest(tmp_path / "ref")


class OneBadAgent(MockBackend):
    """Ben always replies without an action line; everyone else behaves like the mock."""

    def call(self, model, system, user, ctx):
        if ctx["agent"] == "Ben":
            return Reply(text="I am thinking about it.", ok=True)
        return super().call(model, system, user, ctx)


def test_invalid_reply_posts_nothing_and_counts_as_not_adopting(tmp_path):
    cfg = json.loads(json.dumps(BASE))
    cfg["defaults"]["mock"]["invalid_rate"] = 0.0          # so Ben is the only source of INVALID replies
    exp = write_config(tmp_path, cfg)
    Run(exp, tmp_path / "run", OneBadAgent()).run()
    rows = read_rows(tmp_path / "run" / "calls.jsonl")
    ben = [r for r in rows if r["agent"] == "Ben"]
    assert all(r["action"] == "INVALID" and r["invalid_reason"] == "no action line" for r in ben)
    later = [r for r in rows if r["round"] > 1]
    assert later and not any("Ben, round" in r["prompt"] for r in later)
    outcomes = analysis.board_outcomes(exp, rows)
    assert all(inv == 1 for o in outcomes for inv in o["invalid"])
    assert all(o["n_live"] == 3 for o in outcomes)


def test_analysis_bootstrap_is_pinned_and_skips_incomplete_boards(tmp_path):
    exp = write_config(tmp_path)
    Run(exp, tmp_path / "run", MockBackend()).run()
    a, b = analysis.write(tmp_path / "run"), analysis.write(tmp_path / "run")
    assert a["contrasts"] == b["contrasts"]
    est = a["contrasts"]["b - a"]["estimate"]
    assert est == pytest.approx(a["conditions"]["b"]["mean_final_share"] - a["conditions"]["a"]["mean_final_share"])
    rows = [r for r in read_rows(tmp_path / "run" / "calls.jsonl") if not (r["board"] == 0 and r["round"] == 3)]
    outs = analysis.board_outcomes(exp, rows)
    cut = [o for o in outs if o["board"] == 0]
    assert all(o["final_share"] is None and o["complete_rounds"] == 2 for o in cut)


def test_an_error_in_one_board_stops_the_others_from_calling(tmp_path):
    exp = write_config(tmp_path)
    Run(exp, tmp_path / "run", MockBackend(), max_calls=7, concurrency=1).run()
    path = tmp_path / "run" / "calls.jsonl"
    rows = read_rows(path)
    rows[0]["prompt_sha256"] = "0" * 64                    # a tampered log row in the first board
    path.write_text("".join(json.dumps(r) + "\n" for r in rows))
    run = Run(exp, tmp_path / "run", MockBackend(), concurrency=1)
    with pytest.raises(ResumeMismatch):
        run.run()
    assert run.session_calls == 0 and "another board" in run.stop_reason
