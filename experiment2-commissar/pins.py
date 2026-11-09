"""The commissar experiment's pins: the one place that says which castra, subject and CLI every arm runs on, and
the checks that refuse anything else (Codex c2-verify F4).

A0 ran on castra 8457977 exported with `git archive`, so its manifest has no git commit to check. A label naming a
commit proves nothing about the directory it is attached to. These checks hash the bytes instead: castra/arena/
engine.py must hash to ENGINE_SHA256, and the whole castra/ package to CASTRA_TREE_SHA256, which is what an export of
8457977 hashes to. The live castra checkout (b362137 on 2026-11-08) has a different engine, and one that changes what
the subject sees, so an A1 run against it would not be comparable with A0.

Used by run.sh (before it loads credentials or starts anything), compile.py and analyze.py. Command line:
  python3.12 -I pins.py check-castra DIR             the directory's engine and package bytes
  python3.12 -I pins.py check-run DIR ARGS...        check-castra, the --subject in a run command, the CLI version
  python3.12 pins.py check-import DIR                (PYTHONPATH as the run sets it) the imported castra is DIR
Each exits 0 when the pins hold and 2, with the reason on stderr, when they do not.
"""
import hashlib
import pathlib
import subprocess
import sys

CASTRA_COMMIT = "84579774be48eb358ac4cf403b570e3ede321956"
ENGINE_SHA256 = "6aa8e235595f15f96e7de16efaad6ab36aef38f779b857e05dfa4028a75ebc61"
CASTRA_TREE_SHA256 = "bbb51d5a763e888b721ef1bebaae555d2199ba2a0ba4cb3c75a381b50bb7e6be"   # 8457977, from git objects and three exports
SUBJECT = "claude:claude-haiku-5-5"
MODEL = "claude-haiku-5-5"
CLI_VERSION = "2.1.309"
N_EPISODES = 32                 # planned episodes per arm: 8 worlds x 2 beneficiaries x 2 principal names


class PinError(RuntimeError):
    """A castra directory, subject or CLI is not the pinned one."""


def file_sha256(path):
    return hashlib.sha256(pathlib.Path(path).read_bytes()).hexdigest()


def tree_sha256(castra_dir):
    """sha256 over the castra/ package's files (relative path and content hash, sorted by path), ignoring
    __pycache__ and compiled files, so a run that has already imported the package hashes the same."""
    root = pathlib.Path(castra_dir) / "castra"
    if not root.is_dir():
        raise PinError(f"{castra_dir}: no castra/ package")
    h = hashlib.sha256()
    for p in sorted(root.rglob("*")):
        if p.is_dir() or "__pycache__" in p.parts or p.suffix in (".pyc", ".pyo"):
            continue
        h.update(f"{p.relative_to(root).as_posix()}\0{file_sha256(p)}\n".encode())
    return h.hexdigest()


def check_castra(castra_dir):
    """Refuse a castra directory whose engine or package bytes are not the pinned export's. Returns the engine
    sha256."""
    engine = pathlib.Path(castra_dir) / "castra" / "arena" / "engine.py"
    if not engine.is_file():
        raise PinError(f"{castra_dir}: no castra/arena/engine.py")
    got = file_sha256(engine)
    if got != ENGINE_SHA256:
        raise PinError(f"{engine}: engine.py sha256 {got} is not the pinned {ENGINE_SHA256} (castra {CASTRA_COMMIT[:7]})")
    tree = tree_sha256(castra_dir)
    if tree != CASTRA_TREE_SHA256:
        raise PinError(f"{castra_dir}: castra package sha256 {tree} is not the pinned export's {CASTRA_TREE_SHA256}")
    return got


def check_imported(castra_dir=None):
    """The castra this process imports is the pinned one (and, when castra_dir is given, is that directory)."""
    from castra.arena import engine as E
    found = pathlib.Path(E.__file__).resolve().parents[2]
    if castra_dir is not None and found != pathlib.Path(castra_dir).resolve():
        raise PinError(f"the imported castra is {found}, not {castra_dir}")
    return check_castra(found)


def check_subject(args):
    """A run command's --subject must be the pinned subject; other commands carry none."""
    args = list(args)
    if "run" not in args[:1]:
        return
    subjects = [args[i + 1] for i, a in enumerate(args[:-1]) if a == "--subject"]
    subjects += [a.split("=", 1)[1] for a in args if a.startswith("--subject=")]
    if subjects != [SUBJECT]:
        raise PinError(f"the run's subject is {subjects or 'missing'}, not the pinned {SUBJECT}")


def check_cli():
    """The Claude CLI on PATH reports the pinned version (no model call: --version only)."""
    try:
        out = subprocess.run(["claude", "--version"], capture_output=True, text=True, timeout=60).stdout.strip()
    except (OSError, subprocess.TimeoutExpired) as ex:
        raise PinError(f"cannot read the Claude CLI version: {ex}")
    if out.split()[:1] != [CLI_VERSION]:
        raise PinError(f"the Claude CLI is {out!r}, not the pinned {CLI_VERSION}")


def main(argv):
    try:
        if argv[:1] == ["check-castra"] and len(argv) == 2:
            check_castra(argv[1])
        elif argv[:1] == ["check-run"] and len(argv) >= 2:
            check_castra(argv[1])
            check_subject(argv[2:])
            if argv[2:3] == ["run"]:
                check_cli()
        elif argv[:1] == ["check-import"] and len(argv) == 2:
            check_imported(argv[1])
        else:
            print(__doc__, file=sys.stderr)
            return 64
    except PinError as ex:
        print(f"pins: refused: {ex}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
