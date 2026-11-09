"""The board and the prompts: plain-text rendering of posts, and each agent's system prompt and user message.

A board is a list of Post records in the order they were appended: the condition's seed posts first, then each
round's posts. Rounds are synchronous: every live agent in round r sees the board as it stood after round r-1,
so the order in which calls finish never changes what anyone sees (resume and reruns reproduce the same prompts).
"""
import hashlib
import random
from dataclasses import dataclass, field

DISPLAY_FACTOR = 3        # the board shows at most DISPLAY_FACTOR x post_max_words words of any post


@dataclass
class Post:
    """One board post. round 0 marks a seed post; action is shown only when the board shows actions."""
    author: str
    text: str
    round: int
    role: str = ""
    endorsements: object = None     # int, list of names, or None
    action: object = None
    scripted: bool = False
    meta: dict = field(default_factory=dict)


def seed_posts(condition):
    """The condition's seed posts as Post records (round 0)."""
    return [Post(author=p["author"], text=p["text"].strip(), round=0, role=p.get("role") or "",
                 endorsements=p.get("endorsements"), scripted=True) for p in condition["seed_posts"]]


def _clip(text, max_words):
    """At most max_words words of text, marked when clipped (the raw reply stays in the call log)."""
    words = text.split()
    if len(words) <= max_words:
        return text
    return " ".join(words[:max_words]) + " [post shortened]"


def _endorse_line(e):
    """'Endorsed by 3 teammates.' or 'Endorsed by: Ana, Ben.'; '' when there are none."""
    if e is None or e == 0 or e == []:
        return ""
    if isinstance(e, int):
        return f"Endorsed by {e} teammate{'s' if e != 1 else ''}."
    return "Endorsed by: " + ", ".join(e) + "."


def render(posts, condition):
    """The board as plain text, oldest first; '(no posts yet)' when empty."""
    if not posts:
        return "(no posts yet)"
    limit = DISPLAY_FACTOR * condition["post_max_words"]
    out = []
    for i, p in enumerate(posts, 1):
        who = p.author + (f" ({p.role})" if p.role else "")
        when = "earlier" if p.round == 0 else f"round {p.round}"
        block = [f"#{i} {who}, {when}:", _clip(p.text, limit) if p.text else "(no text)"]
        if condition["show_actions"] and p.action:
            block.append(f"Action taken: {p.action}")
        if (line := _endorse_line(p.endorsements)):
            block.append(line)
        out.append("\n".join(block))
    return "\n\n".join(out)


def policy_text(agent, condition):
    """The agent's policy block: its own policy or the condition's, resolved through `policies` when it is a key."""
    pol = agent.get("policy", condition.get("policy"))
    if pol is None:
        return ""
    return condition["policies"].get(pol, pol).strip()


def system_prompt(agent, condition):
    """The agent's system prompt: its own `system` template or the condition's, filled in."""
    template = agent.get("system") or condition["system_template"]
    return template.format(name=agent["name"], role=agent.get("role") or "team member",
                           policy=policy_text(agent, condition)).strip()


def user_message(agent, condition, posts, rnd):
    """Task + board so far + the reply contract, for `agent` in round `rnd`."""
    menu = "\n".join(f"  {a['id']}: {a['description'].strip()}" for a in condition["actions"])
    return (f"{condition['task'].strip()}\n\n"
            f"TEAM BOARD (oldest first)\n-----\n{render(posts, condition)}\n-----\n\n"
            f"This is round {rnd} of {condition['rounds']}. You are {agent['name']}.\n"
            f"Write a short post for the board (at most {condition['post_max_words']} words). "
            f"Then end your reply with exactly one final line in this form:\nACTION: <id>\n"
            f"where <id> is one of:\n{menu}")


def sha256(text):
    """Hex sha256 of a string (prompt hashes in the call log)."""
    return hashlib.sha256(text.encode()).hexdigest()


def board_seed(experiment_seed, condition_id, board_index):
    """The deterministic seed of one board, from the experiment seed, the condition and the board's index."""
    h = hashlib.sha256(f"{experiment_seed}|{condition_id}|{board_index}".encode()).hexdigest()
    return int(h[:12], 16)


def round_order(names, seed, rnd, shuffle):
    """Order in which a round's posts are appended: roster order, or a per-(board, round) seeded shuffle."""
    names = list(names)
    if shuffle:
        random.Random(f"{seed}|{rnd}").shuffle(names)
    return names
