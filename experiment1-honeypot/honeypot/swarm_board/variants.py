"""Calibration variants of a task instance, written to a new directory; the source is only read.

  rename_key(src, dst, new_name, readme_text=None)
      grader/answer_key.json becomes grader/<new_name>; every mention of the old name in the copied grade.py is
      rewritten so the grader still finds its key; grader/README.md is replaced by readme_text when given. The key's
      content and the canaries are unchanged, so copying stays detectable.
  reword_readme(src, dst, text)
      grader/README.md replaced by text; nothing else changes.
  add_brief_line(src, dst, text, after_heading)
      inserts one paragraph into brief.md at the end of the section that starts with after_heading (before the
      next heading, or before the {{GRADER_RULE}} line if that comes first), so the rule placeholder still works.

Both refuse to write into a non-empty dst and suffix instance.json's id ("-<tag>"), so a run's manifest shows the
variant. Use `python3 -m swarm_board hp-variant` to build one from the command line.
"""
import json
import shutil
from pathlib import Path

from .workspace import RULE_PLACEHOLDER, load_instance

KEY_NAME = "answer_key.json"


def _copy(src, dst, tag):
    """Copy src to an empty dst (bytecode skipped) and suffix the instance id with tag; returns dst."""
    src, dst = Path(src), Path(dst)
    load_instance(src)
    if dst.exists() and any(dst.iterdir()):
        raise FileExistsError(f"refusing to write into non-empty {dst}")
    shutil.copytree(src, dst, symlinks=True, dirs_exist_ok=True,
                    ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    inst = json.loads((dst / "instance.json").read_text())
    inst["id"] = f"{inst['id']}-{tag}"
    (dst / "instance.json").write_text(json.dumps(inst, indent=1))
    return dst


def rename_key(src, dst, new_name, readme_text=None, tag="renamed"):
    """The ambiguity variant (module docstring); returns dst."""
    dst = _copy(src, dst, tag)
    g = dst / "grader"
    (g / KEY_NAME).rename(g / new_name)
    grade = g / "grade.py"
    grade.write_text(grade.read_text().replace(KEY_NAME, new_name))
    if readme_text is not None:
        (g / "README.md").write_text(readme_text.rstrip() + "\n")
    inst = json.loads((dst / "instance.json").read_text())
    inst["key_file"] = new_name                  # workspace.load_instance checks grader/<key_file>
    (dst / "instance.json").write_text(json.dumps(inst, indent=1))
    if KEY_NAME in grade.read_text():
        raise ValueError(f"{dst}: grade.py still names {KEY_NAME}")
    load_instance(dst)
    return dst


def reword_readme(src, dst, text, tag="readme"):
    """The README variant (module docstring); returns dst."""
    dst = _copy(src, dst, tag)
    (dst / "grader" / "README.md").write_text(text.rstrip() + "\n")
    return dst


def add_brief_line(src, dst, text, after_heading, tag="brief"):
    """The brief variant (module docstring); returns dst."""
    dst = _copy(src, dst, tag)
    lines = (dst / "brief.md").read_text().splitlines()
    try:
        start = next(i for i, l in enumerate(lines) if l.strip() == after_heading.strip())
    except StopIteration:
        raise ValueError(f"brief.md has no heading {after_heading!r}") from None
    end = len(lines)
    for i in range(start + 1, len(lines)):
        if lines[i].startswith("#") or lines[i].strip() == RULE_PLACEHOLDER:
            end = i
            break
    while end > start + 1 and not lines[end - 1].strip():
        end -= 1
    lines[end:end] = ["", text.strip()]
    (dst / "brief.md").write_text("\n".join(lines) + "\n")
    return dst
