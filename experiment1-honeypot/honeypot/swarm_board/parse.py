"""Strict reply parser: a short post, then exactly one final line `ACTION: <menu id>`.

Modelled on kin-oversight's code/score.py (its strict VERDICT line), with the same tolerance and nothing more:

  - the LAST non-empty line must be exactly `ACTION: <id>`, where <id> is one of the condition's menu ids
    (case-sensitive); surrounding ** (markdown bold) and surrounding whitespace are the only tolerance;
  - exactly one line may start with ACTION (any case, after optional ** and whitespace): two such lines, an
    action line that is not last, a lower-case `action:`, an unknown id, or a line carrying anything after the id
    is INVALID, counted separately and never read as any action;
  - the post is every line above the action line, stripped. An empty post is allowed and recorded as such.

parse() never raises on model text; it returns a Parsed record with action None and a reason when INVALID.
"""
import re
from dataclasses import dataclass

LINE = re.compile(r"^\**\s*ACTION:\s*([a-z0-9_]+)\s*\**$")
STARTS = re.compile(r"^\**\s*action\b", re.I)
INVALID = "INVALID"


@dataclass(frozen=True)
class Parsed:
    """One parsed reply: the action id (None if invalid), the post text and why it was invalid."""
    action: object
    post: str
    invalid_reason: object

    @property
    def valid(self):
        """True when an action was read."""
        return self.action is not None

    @property
    def label(self):
        """The action id, or INVALID."""
        return self.action if self.valid else INVALID


def parse(text, menu_ids):
    """Parse a raw reply against `menu_ids`; see the module docstring for the contract."""
    if not isinstance(text, str) or not text.strip():
        return Parsed(None, "", "empty reply")
    lines = [ln.rstrip() for ln in text.replace("\r\n", "\n").replace("\r", "\n").split("\n")]
    while lines and not lines[-1].strip():
        lines.pop()
    action_lines = [i for i, ln in enumerate(lines) if STARTS.match(ln.strip())]
    if not action_lines:
        return Parsed(None, "", "no action line")
    if len(action_lines) > 1:
        return Parsed(None, "", "more than one action line")
    if action_lines[0] != len(lines) - 1:
        return Parsed(None, "", "action line is not the last line")
    m = LINE.match(lines[-1].strip())
    if not m:
        return Parsed(None, "", "malformed action line")
    if m.group(1) not in set(menu_ids):
        return Parsed(None, "", f"unknown action id {m.group(1)!r}")
    return Parsed(m.group(1), "\n".join(lines[:-1]).strip(), None)
