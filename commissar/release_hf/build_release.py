"""Stage the three Hugging Face folders for the commissar release (two private datasets, one public model) from files already in this repository.

    python3 release_hf/build_release.py            # from the commissar repository root

Writes release_hf/staging/<repo>/ for each repo in REPOS, copies or extracts every file listed below, redacts host
paths in the pin files, writes provenance.json (source path, source and staged sha256, why a file changed) and
manifest.sha256 per folder. Cards (README.md) are copied from release_hf/cards/. The model folder takes the LoRA
adapter from serve/adapter/ when it exists; until then it holds only its card template. Nothing here touches the
network. Re-running first removes the files the previous build's manifests list, nothing else.
"""
import ast
import hashlib
import json
import pathlib
import re
import shutil
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]          # the commissar repository
HERE = ROOT / "release_hf"
STAGING = HERE / "staging"
CARDS = HERE / "cards"

# The datasets follow Ephraiem's convention '<name>-private' and stay private (the Adaption-terms question is open).
# The model is the one public release, on his word of 2026-11-09 02:49 ("push the commissar on huggingface as a
# public model"). publish_hf.py still creates every repo private, verifies it, and makes a repo public only with
# --make-public and only if it is listed in PUBLIC_REPOS.
OWNER = "ephraiemsam16"
MODEL_REPO = "commissar-steward-qwen3.5-4b-lora"
REPOS = {
    "commissar-sft-private": "dataset",
    "stewardbench-private": "dataset",
    MODEL_REPO: "model",
}
PUBLIC_REPOS = {MODEL_REPO}

# (staged path, source path relative to ROOT). Data files are copied byte for byte.
SFT_FILES = [
    ("data/train.jsonl", "data/steward_sft_v4_train.jsonl"),
    ("data/holdout.jsonl", "data/steward_sft_v4_holdout.jsonl"),
    ("data/index.jsonl", "data/steward_sft_v4_index.jsonl"),
    ("data/build_report.json", "data/steward_sft_v4_report.json"),
    # The Invent dataset prompts of the three runs v4 is built from (runs/*_invent/request.json dataset_prompt).
    ("generation/invent_prompt_steward_sft.txt", "data/invent_prompt_v3.txt"),
    ("generation/invent_prompt_steward_sft_quiet.txt", "data/invent_prompt_v3b_quiet.txt"),
    ("generation/invent_prompt_steward_rewrite.txt", "data/invent_prompt_v4_rewrite.txt"),
]
BENCH_FILES = [
    ("v1/items.jsonl", "bench/items.jsonl"),
    ("v1/validation.jsonl", "bench/validation.jsonl"),
    ("v1/steward_prompt.txt", "bench/steward_prompt.txt"),
    ("v1/PINS.json", "bench/PINS.json"),
    ("v2/items_v2.jsonl", "bench/v2/items_v2.jsonl"),
    ("v2/validation_v2.jsonl", "bench/v2/validation_v2.jsonl"),
    ("v2/steward_prompt_v2.txt", "bench/v2/steward_prompt_v2.txt"),
    ("v2/steward_prompt_v2_1.txt", "bench/v2/steward_prompt_v2_1.txt"),
    ("v2/steward_prompt_v2_2.txt", "bench/v2/steward_prompt_v2_2.txt"),
    ("v2/PINS_v2.json", "bench/v2/PINS_v2.json"),
    ("v2/PINS_v2_1.json", "bench/v2/PINS_v2_1.json"),
    ("v2/PINS_v2_2.json", "bench/v2/PINS_v2_2.json"),
]
# Judge prompts are module constants; they are extracted as text and checked against the pinned sha256.
JUDGE_PROMPTS = [
    ("v1/judge_system.txt", "bench/judge.py", "JUDGE_SYSTEM", ("bench/PINS.json", "judge_system_sha256")),
    ("v1/judge_template.txt", "bench/judge.py", "JUDGE_TEMPLATE", ("bench/PINS.json", "judge_template_sha256")),
    ("v2/judge_template_v2.txt", "bench/v2/judge_v2.py", "JUDGE_TEMPLATE", ("bench/v2/PINS_v2.json", "judge_template_sha256")),
]
# tools/after_training.sh copies the unpacked checkpoint here (Human.md, "After training"). Round 2 (v5) is released.
ADAPTER_DIR = ROOT / "serve" / "adapter" / "v5"
ADAPTER_SUFFIXES = {".json", ".safetensors", ".model", ".txt", ".jinja"}
# The platform recorded a base that is not publicly readable; the released config names the base every result was
# measured on (serve/settings.py BASE_MODEL_ID at BASE_REVISION). The original value is kept in provenance.json.
RELEASE_BASE_MODEL = "Qwen/Qwen3.5-4B"
# The round-2 training request, recipe and effective hyperparameters (runs/<ts>_train), staged under training/.
TRAIN_RUN = "runs/20261109T091848Z_train"
TRAIN_FILES = [("training/request.json", f"{TRAIN_RUN}/request.json"),
               ("training/recipe.json", f"{TRAIN_RUN}/recipe.json"),
               ("training/hyperparams.json", f"{TRAIN_RUN}/hyperparams.json")]
# The prompts the adapter was evaluated with: the v2.2 system prompt, and the rewriting user message assembled from
# tools/qa/rewrite_rows.py's TASK and FORMAT constants (operae gen_rewrite.py's format) with three placeholders.
PROMPT_FILES = [("prompts/commissar_prompt_v2_2.txt", "data/commissar_prompt_v2_2.txt")]
REWRITE_MODULE = "tools/qa/rewrite_rows.py"

HOST_PATH = re.compile(r"/(?:home|Users)/[^/\s\"']+/")


def sha(path_or_bytes):
    data = path_or_bytes if isinstance(path_or_bytes, bytes) else pathlib.Path(path_or_bytes).read_bytes()
    return hashlib.sha256(data).hexdigest()


def redact(obj):
    """Replace a host home prefix in every string of a JSON value with '<local>/'."""
    if isinstance(obj, dict):
        return {k: redact(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [redact(v) for v in obj]
    if isinstance(obj, str):
        return HOST_PATH.sub("<local>/", obj)
    return obj


def constant(module_path, name):
    """Read a string constant from a module's source without importing it."""
    for node in ast.parse(module_path.read_text()).body:
        if isinstance(node, ast.Assign) and getattr(node.targets[0], "id", None) == name:
            return ast.literal_eval(node.value)
    raise SystemExit(f"{name} not found as a literal in {module_path}")


def stage_copy(dest_root, rel_dest, rel_src, prov):
    src, dst = ROOT / rel_src, dest_root / rel_dest
    dst.parent.mkdir(parents=True, exist_ok=True)
    if src.suffix == ".json" and HOST_PATH.search(src.read_text()):
        data = json.loads(src.read_text())
        dst.write_text(json.dumps(redact(data), indent=1, ensure_ascii=False) + "\n")
        why = "host path prefix replaced with '<local>/'; every other field unchanged"
    else:
        shutil.copyfile(src, dst)
        why = None
    prov.append({"file": rel_dest, "source": rel_src, "source_sha256": sha(src), "sha256": sha(dst),
                 **({"changed": why} if why else {})})


def write_manifest(dest_root, prov):
    (dest_root / "provenance.json").write_text(json.dumps(prov, indent=1) + "\n")
    lines = [f"{sha(p)}  {p.relative_to(dest_root).as_posix()}" for p in sorted(dest_root.rglob("*"))
             if p.is_file() and p.name != "manifest.sha256"]
    (dest_root / "manifest.sha256").write_text("\n".join(lines) + "\n")


def build_sft():
    dest, prov = STAGING / "commissar-sft-private", []
    for rel_dest, rel_src in SFT_FILES:
        stage_copy(dest, rel_dest, rel_src, prov)
    shutil.copyfile(CARDS / "commissar-sft.md", dest / "README.md")
    write_manifest(dest, prov)


def build_bench():
    dest, prov = STAGING / "stewardbench-private", []
    for rel_dest, rel_src in BENCH_FILES:
        stage_copy(dest, rel_dest, rel_src, prov)
    for rel_dest, module, name, (pin_file, pin_key) in JUDGE_PROMPTS:
        text = constant(ROOT / module, name)
        pinned = json.loads((ROOT / pin_file).read_text())[pin_key]
        if sha(text.encode()) != pinned:
            raise SystemExit(f"{module}:{name} does not match {pin_file} {pin_key}")
        (dest / rel_dest).write_text(text)
        prov.append({"file": rel_dest, "source": f"{module}:{name}", "sha256": sha(dest / rel_dest),
                     "pinned_sha256_matches": f"{pin_file} {pin_key}"})
    shutil.copyfile(CARDS / "stewardbench.md", dest / "README.md")
    write_manifest(dest, prov)


def set_release_base(dest, prov):
    """Point adapter_config.json at the public base the results were measured on; record the original value."""
    cfg_path = dest / "adapter_config.json"
    cfg = json.loads(cfg_path.read_text())
    original = cfg.get("base_model_name_or_path")
    if original == RELEASE_BASE_MODEL:
        return
    cfg["base_model_name_or_path"] = RELEASE_BASE_MODEL
    cfg_path.write_text(json.dumps(cfg, indent=2) + "\n")
    entry = next(e for e in prov if e["file"] == "adapter_config.json")
    entry.update(sha256=sha(cfg_path), changed=f"base_model_name_or_path {original!r} (as recorded by the training "
                 f"platform, not publicly readable) replaced with {RELEASE_BASE_MODEL!r}; every other field unchanged")


def rewrite_user_template():
    """The rewriting user message with {PRINCIPAL}, {SHIFT_NOTE} and {MESSAGE} placeholders."""
    task, fmt, shift = (constant(ROOT / REWRITE_MODULE, n) for n in ("TASK", "FORMAT", "SHIFT"))
    return f"{task}\n\n{fmt}\n\nThe materials:\n{shift}\n{{SHIFT_NOTE}}\nMESSAGE FROM {{PRINCIPAL}}:\n{{MESSAGE}}"


def build_model():
    """Stage the released adapter, its card, the training request and recipe, and the prompts it was evaluated with."""
    dest, prov = STAGING / MODEL_REPO, []
    dest.mkdir(parents=True, exist_ok=True)
    files = sorted(p for p in ADAPTER_DIR.glob("*") if p.is_file() and p.suffix in ADAPTER_SUFFIXES) \
        if ADAPTER_DIR.is_dir() else []
    for p in files:
        stage_copy(dest, p.name, p.relative_to(ROOT).as_posix(), prov)
    if files:
        set_release_base(dest, prov)
    for rel_dest, rel_src in TRAIN_FILES + PROMPT_FILES:
        stage_copy(dest, rel_dest, rel_src, prov)
    (dest / "prompts/rewrite_user_template.txt").write_text(rewrite_user_template())
    prov.append({"file": "prompts/rewrite_user_template.txt", "source": f"{REWRITE_MODULE}: TASK, FORMAT, SHIFT",
                 "sha256": sha(dest / "prompts/rewrite_user_template.txt")})
    shutil.copyfile(CARDS / "commissar-steward-lora.md", dest / "README.md")
    write_manifest(dest, prov)
    return len(files)


def clear_previous():
    """Remove only the files a previous build listed in its manifests, so a rebuild leaves no stale file."""
    for manifest in STAGING.glob("*/manifest.sha256"):
        for line in manifest.read_text().splitlines():
            (manifest.parent / line.split("  ", 1)[1]).unlink(missing_ok=True)
        manifest.unlink()


def main():
    clear_previous()
    build_sft()
    build_bench()
    n_adapter = build_model()
    print(f"staged {', '.join(REPOS)} in {STAGING.relative_to(ROOT)}; adapter files: {n_adapter}")


if __name__ == "__main__":
    sys.exit(main())
