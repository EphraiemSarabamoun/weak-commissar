"""Find, validate and hot-load the Adaption LoRA adapter onto the resident base model.

The server loads Qwen3.5-4B text-only (Qwen3_5ForCausalLM), whose decoder lives
at model.layers.N. An adapter trained on the full multimodal checkpoint names the
same modules model.language_model.layers.N, so keys are remapped before loading,
and keys for the vision tower or the multi-token-prediction head (absent from a
text-only model and irrelevant to text generation) are dropped and reported.
A load that leaves any expected LoRA weight unfilled is refused, never served
half-initialised.

Hot reload: each check compares the adapter files' size and mtime with what is
loaded. A changed adapter loads under a new versioned name, becomes active, and
the old one is deleted, so no restart is needed. Missing files unload it.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

import settings

CONFIG_FILE = "adapter_config.json"
WEIGHTS_FILE = "adapter_model.safetensors"
SAVED_PREFIX = "base_model.model."
# Multimodal-checkpoint prefixes and what they become on the text-only model;
# None means the weights belong to a part the text model does not have.
PREFIX_MAP = (
    ("model.language_model.", "model."),
    ("model.visual.", None),
    ("visual.", None),
    ("mtp.", None),
)


class AdapterError(RuntimeError):
    """The adapter exists but cannot be served (bad config, unmatched weights)."""


def _subdirs(folder: Path) -> list[Path]:
    """Visible subfolders; an unreadable or vanished folder counts as empty."""
    try:
        return [p for p in folder.iterdir() if p.is_dir() and not p.name.startswith(".")]
    except OSError:
        return []


def _holds_adapter(folder: Path) -> bool:
    try:
        return (folder / CONFIG_FILE).is_file() and (folder / WEIGHTS_FILE).is_file()
    except OSError:
        return False


def locate(root: Path, depth: int = settings.ADAPTER_SEARCH_DEPTH) -> Path | None:
    """Return the shallowest folder under root holding both adapter files, or None.

    Raises AdapterError when several folders qualify at that depth (a trainer's
    checkpoint-100/ and checkpoint-200/, say): which one is meant is a decision for
    whoever installs the adapter, so the server refuses rather than guess.
    """
    if root is None or not root.is_dir():
        return None
    frontier = [root]
    for _ in range(depth + 1):
        hits = sorted(f for f in frontier if _holds_adapter(f))
        if len(hits) > 1:
            raise AdapterError(f"{len(hits)} adapters found under {root} ({', '.join(h.name for h in hits[:4])}); "
                               "point the server at exactly one")
        if hits:
            return hits[0]
        frontier = [p for f in frontier for p in _subdirs(f)]
    return None


def try_locate(root: Path | None) -> tuple[Path | None, str | None]:
    """locate() that never raises: (folder or None, reason it could not be used or None)."""
    try:
        return (locate(root) if root else None), None
    except AdapterError as exc:
        return None, str(exc)


def fingerprint(folder: Path) -> tuple:
    """Size and mtime of both adapter files: a change means the adapter was replaced."""
    stats = [(folder / f).stat() for f in (CONFIG_FILE, WEIGHTS_FILE)]
    return tuple((s.st_size, s.st_mtime_ns) for s in stats)


def remap_key(key: str) -> str | None:
    """Map a saved adapter key onto the text-only model; None drops it."""
    if not key.startswith(SAVED_PREFIX):
        return key
    rest = key[len(SAVED_PREFIX):]
    for old, new in PREFIX_MAP:
        if rest.startswith(old):
            return None if new is None else SAVED_PREFIX + new + rest[len(old):]
    return key


def remap_state_dict(state: dict) -> tuple[dict, list[str]]:
    """Apply remap_key to every key; return (remapped, dropped_keys)."""
    out, dropped = {}, []
    for key, tensor in state.items():
        new = remap_key(key)
        if new is None:
            dropped.append(key)
        else:
            out[new] = tensor
    return out, dropped


def multimodal_name(name: str) -> str:
    """The multimodal checkpoint's name for a text-only module (model.X -> model.language_model.X)."""
    return "model.language_model." + name[len("model."):] if name.startswith("model.") else name


def resolve_targets(targets, module_names):
    """Turn a regex target_modules string into the explicit list of matching text-model modules.

    PEFT full-matches a string target against module paths, and the regex may have been
    written against the multimodal paths, so each module is tried under both names.
    Editing the regex text instead is unsafe (it can leave an invalid pattern). A list of
    module-name suffixes is returned unchanged: those match either layout already.
    """
    if not isinstance(targets, str):
        return targets
    rx = re.compile(targets)
    hits = [n for n in module_names
            if "lora_" not in n and not n.endswith("base_layer") and (rx.fullmatch(n) or rx.fullmatch(multimodal_name(n)))]
    if not hits:
        raise AdapterError(f"target_modules regex {targets!r} matches no module of the text model")
    return hits


def remap_patterns(patterns: dict, module_names) -> dict:
    """Carry rank_pattern / alpha_pattern keys written for multimodal paths over to the text model.

    PEFT matches a pattern key k against a module path with (.*\\.)?(k)$. A key that names
    language_model would match nothing on the text model and its rank or alpha would be
    silently ignored, so it is expanded to the exact text-model modules it matched.
    """
    out = {}
    for key, value in patterns.items():
        if "language_model" not in key:
            out[key] = value
            continue
        rx = re.compile(rf"(.*\.)?({key})$")
        hits = [n for n in module_names if "lora_" not in n and rx.match(multimodal_name(n))]
        if not hits:
            raise AdapterError(f"pattern key {key!r} matches no module of the text model")
        out.update({re.escape(n): value for n in hits})
    return out


@dataclass
class LoadedAdapter:
    name: str
    folder: Path
    stamp: tuple
    dropped_keys: int
    loaded_keys: int


class AdapterSlot:
    """Owns the single steward-lora slot: where to look, what is loaded, and why it failed."""

    def __init__(self, root: Path | None):
        self.root = root
        self.loaded: LoadedAdapter | None = None
        self.last_error: str | None = None
        self._failed_stamp: tuple | None = None  # (folder, stamp) of the last failed load, not retried
        self._version = 0

    def set_root(self, root: Path | None) -> None:
        self.root = root

    def status(self) -> dict:
        found, why = try_locate(self.root)
        return {
            "configured_dir": str(self.root) if self.root else None,
            "found_dir": str(found) if found else None,
            "loaded": self.loaded is not None,
            "loaded_dir": str(self.loaded.folder) if self.loaded else None,
            "loaded_keys": self.loaded.loaded_keys if self.loaded else None,
            "dropped_keys": self.loaded.dropped_keys if self.loaded else None,
            "last_error": self.last_error or why,
        }

    def available(self) -> bool:
        """Cheap check for /v1/models: are the adapter files present?"""
        return try_locate(self.root)[0] is not None

    def sync(self, engine) -> bool:
        """Make the loaded adapter match the files on disk. Returns True when one is ready.

        Must be called with the engine's generation lock held, since it mutates the model.
        """
        folder, why = try_locate(self.root)
        if folder is None:
            if self.loaded is not None:
                engine.drop_adapter(self.loaded.name)
                self.loaded = None
            self.last_error, self._failed_stamp = why, None  # no stale error from earlier files
            return False
        try:
            stamp = fingerprint(folder)
        except OSError as exc:  # files vanished between locate and stat
            self.last_error = f"{type(exc).__name__}: {exc}"
            return False
        if self.loaded is not None and self.loaded.folder == folder and self.loaded.stamp == stamp:
            return True
        if self._failed_stamp == (folder, stamp):
            return False  # same broken files as last time: report last_error without reloading
        self._version += 1
        name = f"{settings.LORA_MODEL_NAME}-v{self._version}"
        try:
            loaded_keys, dropped = engine.attach_adapter(name, folder)
        except Exception as exc:  # report and keep serving the base model
            self.last_error = f"{type(exc).__name__}: {exc}"
            self._failed_stamp = (folder, stamp)
            return False
        old = self.loaded
        self.loaded = LoadedAdapter(name, folder, stamp, dropped, loaded_keys)
        self.last_error = None
        if old is not None:
            engine.drop_adapter(old.name)
        return True


def read_config(folder: Path) -> dict:
    """Load adapter_config.json, refusing anything that is not a LoRA (targets resolved later)."""
    cfg = json.loads((folder / CONFIG_FILE).read_text())
    if cfg.get("peft_type", "LORA") != "LORA":
        raise AdapterError(f"peft_type {cfg.get('peft_type')!r} is not LORA")
    if cfg.get("layer_replication"):
        raise AdapterError("layer_replication rewires base layers and would contaminate steward-base; refused")
    cfg["inference_mode"] = True
    # pissa / olora / corda / loftq initialisation rewrites the base weights in place when the
    # adapter is injected, and neither disable_adapter nor unload restores them. The saved A
    # and B are loaded right after injection, so no initialisation is needed at all.
    cfg["init_lora_weights"] = False
    return cfg
