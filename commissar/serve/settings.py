"""Every tunable of the commissar server in one place.

The server, launcher, tests and smoke script all read these values, so a port,
threshold or default changes here and nowhere else. Environment variables
override the defaults where an operator may need to change them at launch.
"""

from __future__ import annotations

import os
from pathlib import Path

SERVE_DIR = Path(__file__).resolve().parent

# The base model. Pinned to the hub revision that was downloaded and smoke-tested
# on 2026-11-08, the same base Adaption fine-tunes as a LoRA.
BASE_MODEL_ID = "Qwen/Qwen3.5-4B"
BASE_REVISION = "851bf6e806efd8d0a36b00ddf55e13ccb7b8cd0a"

# Public model names, as /v1/models lists them.
BASE_MODEL_NAME = "steward-base"
LORA_MODEL_NAME = "steward-lora"

HOST = "127.0.0.1"
PORT = int(os.environ.get("COMMISSAR_PORT", "8417"))

# Where the server looks for the Adaption LoRA. The directory (or any folder up to
# three levels below it) must hold adapter_config.json and adapter_model.safetensors.
ADAPTER_DIR = Path(os.environ.get("COMMISSAR_ADAPTER_DIR", str(SERVE_DIR / "adapter")))
ADAPTER_SEARCH_DEPTH = 3

# GPU policy. A steering lab that is not ours shares the RTX 5090, so the server
# refuses to start unless this much VRAM is free, and caps its own PyTorch
# allocator so it can never take more than ALLOCATOR_CAP_GB of what it found.
GPU_INDEX = 0
MIN_FREE_GB_TO_START = 12.0
ALLOCATOR_CAP_GB = float(os.environ.get("COMMISSAR_VRAM_CAP_GB", "10.5"))

# Request limits and OpenAI-style defaults (temperature and top_p default to 1.0,
# as in the OpenAI API, when a request omits them).
DEFAULT_MAX_TOKENS = 512
MAX_MAX_TOKENS = 4096
MAX_INPUT_TOKENS = 16384
DEFAULT_TEMPERATURE = 1.0
DEFAULT_TOP_P = 1.0
MAX_STOP_SEQUENCES = 4

# Qwen3.5 thinks by default. A commissar posts short messages, so thinking is off
# unless a request sends chat_template_kwargs={"enable_thinking": true}.
DEFAULT_ENABLE_THINKING = False
