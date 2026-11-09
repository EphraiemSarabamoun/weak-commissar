"""Render a benchmark item into the text the steward sees (and the judge reads).

The layout follows the training-row shape in data/invent_prompt_v2.txt: the
principal and role, the standing instructions in the principal's voice, the team,
then either an opening with the principal's current requests or a short excerpt
of team messages plus the one new message the steward answers.
"""

from __future__ import annotations

from pathlib import Path

import common


def situation_text(item: dict) -> str:
    """The situation as plain text: principal, instructions, team, then opening or excerpt."""
    p = item["principal"]
    lines = [f"Principal: {p['name']}, {p['role']}, {p['org']}", "",
             f"Standing instructions from {p['name']}:"]
    lines += [f"{i}. {text}" for i, text in enumerate(item["instructions"], 1)]
    lines += ["", "Team:"] + [f"- {a['name']}: {a['doing']}" for a in item["team"]]
    lines.append("")
    if item["kind_gold"] == "opening_brief":
        lines.append(f"Opening: the team is starting this task. {p['name']}'s current requests:")
        lines += [f"- {r}" for r in item["requests"]]
    else:
        lines.append("Recent team messages:")
        lines += [f"{m['from']}: {m['text']}" for m in item["excerpt"]]
        lines += ["", "New message:", f"{item['new_message']['from']}: {item['new_message']['text']}"]
    return "\n".join(lines)


def steward_user_message(item: dict) -> str:
    return situation_text(item) + "\n\nWrite your one message to the team."


def steward_system_prompt(item: dict, template: str | None = None) -> str:
    """The approved steward instructions with {PRINCIPAL} set to this item's principal."""
    template = template if template is not None else Path(common.STEWARD_PROMPT_FILE).read_text().strip()
    return template.replace("{PRINCIPAL}", item["principal"]["name"])
