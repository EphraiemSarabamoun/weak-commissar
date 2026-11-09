"""Download the best checkpoint of a finished AutoScientist run and unpack it. Free (no credits).

The endpoint streams a compressed tar (a LoRA adapter: adapter_config.json,
adapter_model.safetensors, tokenizer files, trainer_state.json). The archive is saved under
runs/<timestamp>_download/ and extracted next to it with tarfile's "data" filter, which rejects
absolute paths, links outside the target and device files. Despite the .tgz name the first real
download (2026-11-08) was Zstandard-compressed, which Python 3.10's tarfile cannot read, so a
zstd archive is first decompressed to a plain .tar beside it with the system zstd tool.

Usage:  .venv/bin/python tools/download.py --run-id as_...
"""

from __future__ import annotations

import subprocess
import sys
import tarfile
from pathlib import Path

import _common

ZSTD_MAGIC = b"\x28\xb5\x2f\xfd"


def as_tar(archive: Path) -> Path:
    """The archive itself if tarfile can read it, else a plain .tar decompressed from a zstd archive."""
    with open(archive, "rb") as f:
        if f.read(4) != ZSTD_MAGIC:
            return archive
    plain = archive.with_suffix(".tar")
    subprocess.run(["zstd", "-d", "-q", "-f", "-o", str(plain), str(archive)], check=True)
    return plain


def safe_extract(archive, dest) -> list[str]:
    """Extract with the stdlib safety filter (present in Python 3.10.12+); refuse if it is missing."""
    with tarfile.open(as_tar(Path(archive))) as tar:
        if not hasattr(tarfile, "data_filter"):
            raise RuntimeError("this Python lacks tarfile extraction filters; extract by hand after inspecting")
        tar.extractall(dest, filter="data")
        return tar.getnames()


def main() -> int:
    parser = _common.base_parser(__doc__.splitlines()[0], spends=False)
    parser.add_argument("--run-id", required=True)
    args = parser.parse_args()
    try:
        key, client = _common.setup()
    except _common.KeyMissing as exc:
        print(exc)
        return 2
    run = client.autoscientist.get(args.run_id)
    if run.status != "succeeded" or not run.download_available:
        print(f"not downloadable yet: status={run.status} download_available={run.download_available} error={run.error}")
        return 1
    run_dir = _common.new_run_dir("download")
    _common.write_json(run_dir / "run.json", run, key)
    archive = run_dir / "best-checkpoint.tgz"
    with client.autoscientist.with_streaming_response.download(run.id) as response:
        response.stream_to_file(archive)
    names = safe_extract(archive, run_dir / "checkpoint")
    print(f"saved {archive} ({archive.stat().st_size} bytes); extracted {len(names)} entries to {run_dir / 'checkpoint'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
