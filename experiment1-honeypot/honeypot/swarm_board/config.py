"""Experiment configs: load a YAML file, merge defaults into each condition, validate, and freeze the result.

A config has top-level `experiment`, `seed`, `boards_per_condition`, optional `defaults` and a list of
`conditions`. Every condition key may also appear in `defaults`; a condition's own value replaces the default
whole (lists are not merged), so a roster or a seed-post list is always read in one place. Condition keys:

  agents          [{name, role?, model?, policy?, system?, scripted?, posts?, action?}]; live unless scripted.
                  A scripted agent posts posts[r-1] in round r (nothing once the list runs out) and, when
                  `action` is set and the board shows actions, shows that action; it is never counted.
  policy          policy key or literal text applied to every live agent without its own `policy`.
  policies        {key: text}: named policy blocks (a principal-loyalty or impartiality instruction).
  system_template the agent's system prompt; placeholders {name}, {role}, {policy}.
  task            what each agent is doing (the first part of every user message).
  seed_posts      [{author, role?, text, endorsements?: int | [names]}]: scripted posts present before round 1.
  rounds          number of rounds.
  actions         [{id, description}]: the action menu; ids are [a-z0-9_]+.
  target_action   the action whose adoption is the outcome.
  post_max_words  the length the prompt asks for (default 80); the board shows at most 3x that many words.
  show_actions    whether the board shows each post's chosen action (default true).
  shuffle_round_order  whether a round's posts are appended in a per-board seeded order (default false: roster order).
  model           default model for agents without one.
  mock            {p_base, p_social, invalid_rate}: the mock backend's behaviour (tests and dry runs only).

load() returns an Experiment whose conditions are plain dicts with every key filled, plus `config_sha256` over
the file's bytes. Invalid configs raise ConfigError naming every problem at once.
"""
import copy
import hashlib
import re
from dataclasses import dataclass
from pathlib import Path

import yaml

ID = re.compile(r"^[a-z0-9_]+$")
NAME = re.compile(r"^[A-Za-z][A-Za-z .'-]{0,39}$")
CONDITION_KEYS = {"id", "agents", "policy", "policies", "system_template", "task", "seed_posts", "rounds",
                  "actions", "target_action", "post_max_words", "show_actions", "shuffle_round_order", "model",
                  "mock", "description"}
AGENT_KEYS = {"name", "role", "model", "policy", "system", "scripted", "posts", "action"}
POST_KEYS = {"author", "role", "text", "endorsements"}
TOP_KEYS = {"experiment", "seed", "boards_per_condition", "defaults", "conditions", "contrasts", "bootstrap"}
FILLED = {"policy": None, "policies": {}, "seed_posts": [], "post_max_words": 80, "show_actions": True,
          "shuffle_round_order": False, "model": None, "description": "",
          "mock": {"p_base": 0.15, "p_social": 0.6, "invalid_rate": 0.05}}


class ConfigError(ValueError):
    """A config that cannot run; the message lists every problem found."""


@dataclass(frozen=True)
class Experiment:
    """A validated experiment: the merged conditions in file order plus run-level settings."""
    name: str
    seed: int
    boards_per_condition: int
    conditions: tuple
    contrasts: tuple
    bootstrap: dict
    config_sha256: str
    raw: dict

    def condition(self, cid):
        """The merged condition dict with id `cid` (KeyError if absent)."""
        for c in self.conditions:
            if c["id"] == cid:
                return c
        raise KeyError(cid)


def _check_condition(c, problems):
    """Append every problem with one merged condition to `problems`."""
    where = f"condition {c.get('id')!r}"
    for k in set(c) - CONDITION_KEYS:
        problems.append(f"{where}: unknown key {k!r}")
    for k in ("agents", "system_template", "task", "rounds", "actions", "target_action"):
        if c.get(k) in (None, "", []):
            problems.append(f"{where}: {k} is required")
    acts = c.get("actions") or []
    ids = [a.get("id") for a in acts if isinstance(a, dict)]
    if len(ids) != len(acts) or any(not isinstance(i, str) or not ID.match(i) for i in ids):
        problems.append(f"{where}: every action needs an id matching [a-z0-9_]+")
    if len(set(ids)) != len(ids):
        problems.append(f"{where}: duplicate action ids")
    if c.get("target_action") and c["target_action"] not in ids:
        problems.append(f"{where}: target_action {c['target_action']!r} is not in the menu")
    if not isinstance(c.get("rounds"), int) or c.get("rounds", 0) < 1:
        problems.append(f"{where}: rounds must be a positive integer")
    names = []
    for a in c.get("agents") or []:
        if not isinstance(a, dict):
            problems.append(f"{where}: agent entries must be mappings")
            continue
        for k in set(a) - AGENT_KEYS:
            problems.append(f"{where}: agent {a.get('name')!r}: unknown key {k!r}")
        if not isinstance(a.get("name"), str) or not NAME.match(a["name"]):
            problems.append(f"{where}: agent name {a.get('name')!r} must be a plain display name")
        names.append(a.get("name"))
        if a.get("scripted"):
            if a.get("action") is not None and a["action"] not in ids:
                problems.append(f"{where}: scripted agent {a.get('name')!r} action not in the menu")
        elif not (a.get("model") or c.get("model")):
            problems.append(f"{where}: live agent {a.get('name')!r} has no model")
        pol = a.get("policy", c.get("policy"))
        if pol is not None and not isinstance(pol, str):
            problems.append(f"{where}: agent {a.get('name')!r}: policy must be a key or text")
    if len(set(names)) != len(names):
        problems.append(f"{where}: duplicate agent names")
    if not any(isinstance(a, dict) and not a.get("scripted") for a in c.get("agents") or []):
        problems.append(f"{where}: at least one live agent is required")
    for p in c.get("seed_posts") or []:
        if not isinstance(p, dict) or not p.get("author") or not p.get("text"):
            problems.append(f"{where}: every seed post needs an author and text")
            continue
        for k in set(p) - POST_KEYS:
            problems.append(f"{where}: seed post by {p['author']!r}: unknown key {k!r}")
        e = p.get("endorsements")
        if e is not None and not (isinstance(e, int) and e >= 0) and not (
                isinstance(e, list) and all(isinstance(x, str) for x in e)):
            problems.append(f"{where}: seed post by {p['author']!r}: endorsements must be a count or a name list")
    try:
        c["system_template"].format(name="x", role="x", policy="x")
    except (KeyError, IndexError, AttributeError, ValueError) as exc:
        problems.append(f"{where}: system_template has an unknown placeholder ({exc})")


def load(path):
    """Read, merge and validate the YAML config at `path`; return an Experiment or raise ConfigError."""
    data = Path(path).read_bytes()
    return from_raw(yaml.safe_load(data) or {}, hashlib.sha256(data).hexdigest(), Path(path).stem)


def from_raw(raw, config_sha256, fallback_name="experiment"):
    """Merge and validate an already-parsed config (a run's manifest keeps one); see load()."""
    problems = [f"unknown top-level key {k!r}" for k in set(raw) - TOP_KEYS]
    defaults = raw.get("defaults") or {}
    conditions = []
    for entry in raw.get("conditions") or []:
        c = copy.deepcopy(FILLED)
        c.update(copy.deepcopy(defaults))
        c.update(copy.deepcopy(entry))
        if not isinstance(c.get("id"), str) or not ID.match(c["id"]):
            problems.append(f"condition id {c.get('id')!r} must match [a-z0-9_]+")
        _check_condition(c, problems)
        conditions.append(c)
    if not conditions:
        problems.append("no conditions")
    ids = [c.get("id") for c in conditions]
    if len(set(ids)) != len(ids):
        problems.append("duplicate condition ids")
    contrasts = tuple(tuple(x) for x in raw.get("contrasts") or [])
    for pair in contrasts:
        if len(pair) != 2 or any(x not in ids for x in pair):
            problems.append(f"contrast {list(pair)} must name two condition ids")
    if not isinstance(raw.get("boards_per_condition"), int) or raw["boards_per_condition"] < 1:
        problems.append("boards_per_condition must be a positive integer")
    if not isinstance(raw.get("seed"), int):
        problems.append("seed must be an integer")
    if problems:
        raise ConfigError("; ".join(problems))
    boot = {"B": 2000, "seed": raw["seed"], **(raw.get("bootstrap") or {})}
    return Experiment(name=str(raw.get("experiment") or fallback_name), seed=raw["seed"],
                      boards_per_condition=raw["boards_per_condition"], conditions=tuple(conditions),
                      contrasts=contrasts, bootstrap=boot, config_sha256=config_sha256, raw=raw)
