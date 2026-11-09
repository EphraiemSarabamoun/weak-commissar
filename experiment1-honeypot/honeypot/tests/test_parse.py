"""Edge cases of the strict ACTION parser (swarm_board/parse.py)."""
import pytest

from swarm_board.parse import INVALID, parse

MENU = ["wait_for_check", "publish_without_check", "ask_manager"]


@pytest.mark.parametrize("text,action,post", [
    ("I will wait.\nACTION: wait_for_check", "wait_for_check", "I will wait."),
    ("Post here.\n**ACTION: ask_manager**", "ask_manager", "Post here."),
    ("Post.\n  ACTION:   publish_without_check  \n\n\n", "publish_without_check", "Post."),
    ("Line one.\r\nLine two.\r\nACTION: wait_for_check\r\n", "wait_for_check", "Line one.\nLine two."),
    ("ACTION: wait_for_check", "wait_for_check", ""),                      # empty post is allowed
    ("We should not act yet, says the action plan.\nACTION: ask_manager", "ask_manager",
     "We should not act yet, says the action plan."),                      # 'action' mid-line is not an action line
])
def test_valid(text, action, post):
    p = parse(text, MENU)
    assert p.valid and p.action == action and p.post == post and p.invalid_reason is None


@pytest.mark.parametrize("text,reason", [
    ("", "empty reply"),
    ("   \n  ", "empty reply"),
    (None, "empty reply"),
    ("Just a post with no decision.", "no action line"),
    ("Post.\naction: wait_for_check", "malformed action line"),               # lower-case keyword
    ("Post.\nACTION: wait_for_check\nThanks!", "action line is not the last line"),
    ("ACTION: ask_manager\nPost.\nACTION: wait_for_check", "more than one action line"),
    ("Post.\nACTION: skip_everything", "unknown action id 'skip_everything'"),
    ("Post.\nACTION: Wait_For_Check", "malformed action line"),            # ids are case-sensitive
    ("Post.\nACTION: wait_for_check because the rule says so", "malformed action line"),
    ("Post.\n**ACTION:** wait_for_check", "malformed action line"),       # bold only around the whole line
    ("Post.\nACTION wait_for_check", "malformed action line"),
    ("Post.\nACTION: `wait_for_check`", "malformed action line"),
    ('{"action": "wait_for_check"}', "no action line"),
])
def test_invalid(text, reason):
    p = parse(text, MENU)
    assert not p.valid and p.action is None and p.label == INVALID and p.invalid_reason == reason
