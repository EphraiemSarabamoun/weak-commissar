"""Shared plumbing for the commissar Adaption scripts.

Every script in tools/ goes through this module for four things, so each policy has one home:

1. The API key. It is read from <local>/.config/adaption/api_key, or from ADAPTION_API_KEY when that is
   already set, and is never printed, logged or written anywhere. The only thing ever shown about
   it is its length (key_summary).
2. The client. make_client() builds an adaption.Adaption with the key passed explicitly, after
   switching off the SDK's own debug logging so no request headers can reach a terminal.
3. The spend gate. Any call that can consume credits must pass require_spend(), which refuses
   unless the operator typed --yes-spend.
4. The run record. Each real call writes its request and response as JSON under
   runs/<timestamp>_<label>/, and write_json() refuses to write any text that contains the key.
"""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import os
import stat
import sys
from pathlib import Path
from typing import Any

# One home for paths and policy constants.
KEY_FILE = Path.home() / ".config" / "adaption" / "api_key"
KEY_ENV = "ADAPTION_API_KEY"
REPO_ROOT = Path(__file__).resolve().parent.parent
RUNS_DIR = REPO_ROOT / "runs"
DEFAULT_BASE_MODEL = "Qwen/Qwen3.5-4B"  # in the live list 2026-11-08 (sft,dpo; lora,full); Mistral-7B is not offered
SPEND_FLAG = "--yes-spend"


class KeyMissing(RuntimeError):
    """Raised when neither the key file nor the environment variable holds a key."""


def load_key() -> tuple[str, str]:
    """Return (key, source) without ever showing the key.

    The environment variable wins when it is already set, because a shell that sourced
    <local>/.zshrc.secrets has deliberately exported it. Otherwise the key file is read. A key file
    readable by group or others is still used, but a warning (with no key material) is printed.
    """
    env_key = os.environ.get(KEY_ENV, "").strip()
    if env_key:
        return env_key, f"env {KEY_ENV}"
    if not KEY_FILE.exists():
        raise KeyMissing(
            f"No Adaption key: {KEY_FILE} does not exist and {KEY_ENV} is unset. "
            "Ephraiem creates the key in the Adaption app (Settings -> API keys) and saves it there."
        )
    mode = KEY_FILE.stat().st_mode
    if mode & (stat.S_IRWXG | stat.S_IRWXO):
        print(f"warning: {KEY_FILE} is readable by group/others; chmod 600 it", file=sys.stderr)
    key = KEY_FILE.read_text(encoding="utf-8").strip()
    if not key:
        raise KeyMissing(f"{KEY_FILE} is empty")
    return key, f"file {KEY_FILE}"


def key_summary(key: str, source: str) -> str:
    """Describe the key by its source and length only (zero characters of the key itself)."""
    return f"key: loaded from {source}, length {len(key)}"


def make_client(key: str):
    """Build an Adaption client with the key passed explicitly and SDK debug logging off.

    ADAPTION_LOG would make the SDK log requests; it is removed from this process's environment
    before the SDK is imported so that cannot happen by accident. ADAPTION_BASE_URL is left alone:
    the offline tests use it to point the SDK at a local stub server.
    """
    os.environ.pop("ADAPTION_LOG", None)
    from adaption import Adaption  # imported late so the logging guard above runs first

    return Adaption(api_key=key)


def base_parser(description: str, spends: bool) -> argparse.ArgumentParser:
    """Argument parser with the common flags; scripts that can spend get --yes-spend."""
    parser = argparse.ArgumentParser(description=description)
    if spends:
        parser.add_argument(
            SPEND_FLAG,
            dest="yes_spend",
            action="store_true",
            help="actually launch the job and spend credits (without it the script only describes the call)",
        )
    return parser


def require_spend(args: argparse.Namespace, what: str) -> bool:
    """Return True only when --yes-spend was passed; otherwise explain and return False."""
    if getattr(args, "yes_spend", False):
        return True
    print(f"refusing to {what} without {SPEND_FLAG}; no paid job was launched")
    return False


def new_run_dir(label: str) -> Path:
    """Create runs/<UTC timestamp>_<label>/ and return it."""
    stamp = _dt.datetime.now(_dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = RUNS_DIR / f"{stamp}_{label}"
    path.mkdir(parents=True, exist_ok=False)
    return path


def to_jsonable(obj: Any) -> Any:
    """Turn SDK pydantic models (and plain values) into JSON-ready data."""
    if hasattr(obj, "model_dump"):
        return obj.model_dump(mode="json")
    return obj


def write_json(path: Path, obj: Any, key: str) -> None:
    """Write obj as pretty JSON, refusing if the serialized text contains the key."""
    text = json.dumps(to_jsonable(obj), indent=2, sort_keys=True, default=str)
    if key and key in text:
        raise RuntimeError(f"refusing to write {path.name}: the content contains the API key")
    path.write_text(text + "\n", encoding="utf-8")


def setup():
    """Load the key, print its summary (length only) and return (key, client)."""
    key, source = load_key()
    print(key_summary(key, source))
    return key, make_client(key)
