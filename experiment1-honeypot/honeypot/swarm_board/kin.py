"""Read-only bridge to the kin-oversight harness, so swarm-board reuses its pieces instead of copying them.

kin-oversight keeps its modules in a package named `code`, which collides with Python's standard-library `code`
module. Putting its root on sys.path would make `import code` ambiguous for every library that imports the stdlib
one (pdb does). So the package is loaded under a private alias, `kin_code`, straight from its directory, and only
the modules swarm-board needs are imported from it:

  kin_code.subjects            ClaudeSubject / CodexSubject: the isolated `claude -p` and `codex exec` recipe
                               (fresh neutral <tmp>/s/<hex> dir per call, env built from nothing, tools and MCP off,
                               CLAUDE_CODE_DISABLE_CLAUDE_MDS=1 and CLAUDE_CODE_DISABLE_AUTO_MEMORY=1), plus the
                               Conversation / Turn result types and cli_versions().
  kin_code.probe_check         fail-closed validation of the isolation probe (tool catalog + person cues).
  kin_code.analysis.bootstrap  the pinned cluster bootstrap: strata_of, draw_multiplicities, percentile_ci.

Nothing here writes into kin-oversight. provenance() records which kin commit and file hashes a run used, because
the bridge reads whatever is on disk at run time.
"""
import hashlib
import importlib
import importlib.util
import os
import subprocess
import sys
from pathlib import Path

ALIAS = "kin_code"
REUSED = ("code/subjects.py", "code/probe_check.py", "code/analysis/bootstrap.py")


def kin_root():
    """The kin-oversight files: $SWARM_KIN_ROOT, else the copy vendored in this repository (vendor/kin_oversight,
    see its PROVENANCE.md)."""
    return Path(os.environ.get("SWARM_KIN_ROOT") or Path(__file__).resolve().parents[2] / "vendor" / "kin_oversight")


def _package():
    """Register kin's `code/` directory as the package `kin_code` (once) and return it."""
    if ALIAS in sys.modules:
        return sys.modules[ALIAS]
    pkg_dir = kin_root() / "code"
    if not (pkg_dir / "__init__.py").exists():
        raise ImportError(f"kin-oversight code package not found at {pkg_dir} (set SWARM_KIN_ROOT)")
    spec = importlib.util.spec_from_file_location(ALIAS, pkg_dir / "__init__.py",
                                                  submodule_search_locations=[str(pkg_dir)])
    module = importlib.util.module_from_spec(spec)
    sys.modules[ALIAS] = module
    spec.loader.exec_module(module)
    return module


def load(name):
    """Import kin module `name` (for example 'subjects' or 'analysis.bootstrap') under the alias."""
    _package()
    return importlib.import_module(f"{ALIAS}.{name}")


def provenance():
    """{root, commit, files: {path: sha256}} for the kin modules this harness reuses."""
    root = kin_root()
    try:
        commit = subprocess.run(["git", "-C", str(root), "rev-parse", "HEAD"], capture_output=True, text=True,
                                timeout=10).stdout.strip() or None
    except (OSError, subprocess.SubprocessError):
        commit = None
    files = {}
    for rel in REUSED:
        p = root / rel
        files[rel] = hashlib.sha256(p.read_bytes()).hexdigest() if p.exists() else None
    return {"root": str(root), "commit": commit, "files": files}
