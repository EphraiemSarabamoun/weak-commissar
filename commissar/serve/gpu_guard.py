"""VRAM checks that run before the model loads, and the cap on our own allocator.

The free-memory check uses nvidia-smi so it reads the device before this process
creates a CUDA context (which itself costs about half a gigabyte). Nothing here
signals, stops or inspects any other process: the guard only decides whether we
start, and how much we may take.
"""

from __future__ import annotations

import subprocess

import settings


class InsufficientVRAM(RuntimeError):
    """Raised when the GPU has less free memory than the start threshold."""


def device_free_gb(gpu_index: int = settings.GPU_INDEX) -> float:
    """Free VRAM in GiB on one GPU, read from nvidia-smi (read-only query)."""
    out = subprocess.run(
        ["nvidia-smi", f"--id={gpu_index}", "--query-gpu=memory.free", "--format=csv,noheader,nounits"],
        check=True, capture_output=True, text=True, timeout=20,
    ).stdout.strip()
    return float(out.splitlines()[0]) / 1024.0


def require_free_vram(min_gb: float = settings.MIN_FREE_GB_TO_START) -> float:
    """Return free GiB, or raise InsufficientVRAM when it is below min_gb."""
    free = device_free_gb()
    if free < min_gb:
        raise InsufficientVRAM(
            f"only {free:.2f} GiB free on GPU {settings.GPU_INDEX}; the commissar needs {min_gb:.1f} GiB "
            "free to start. Not loading. Another process shares this GPU and is never touched."
        )
    return free


def cap_allocator(torch_module, cap_gb: float = settings.ALLOCATOR_CAP_GB) -> float:
    """Limit this process's PyTorch caching allocator to cap_gb; return the fraction set."""
    total = torch_module.cuda.get_device_properties(settings.GPU_INDEX).total_memory
    fraction = min(1.0, cap_gb * 2**30 / total)
    torch_module.cuda.set_per_process_memory_fraction(fraction, settings.GPU_INDEX)
    return fraction
