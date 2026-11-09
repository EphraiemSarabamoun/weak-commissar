"""Upload the staged commissar release to Hugging Face as PRIVATE repos and verify each against its manifest.

    python3 release_hf/publish_hf.py --dry-run                     # lists exactly what would upload; no network
    uv run --no-project --python 3.12 --with huggingface_hub python release_hf/publish_hf.py --skip-model
    uv run --no-project --python 3.12 --with huggingface_hub python release_hf/publish_hf.py \
        --only commissar-steward-qwen3.5-4b-lora --make-public          # the model: private upload, verify, then public

Modelled on acta's scripts/publish_hf.py. For each repo it creates <owner>/<name> as private if it does not exist,
stops if the repo reads as public, uploads the staged folder, then downloads every file at the new revision and
compares it with manifest.sha256. Before any network call it re-checks every staged file against its manifest, re-runs
scan_release.py (any fail-category hit stops it) and refuses the model repo while its card still holds a {{FILL: ...}}
slot or the adapter weights are missing. The token comes from HF_TOKEN in the environment, else from the
`export HF_TOKEN=...` line of <local>/.zshrc.secrets; it is never printed. --make-public (Ephraiem's go for the model,
2026-11-09 02:49) flips a repo to public only after its private upload and the download-back check both pass, only for
a repo in build_release.PUBLIC_REPOS, and only when every repo named in the run is such a repo; it then re-reads the
repo, requires private=False, and prints the URL. The datasets can never be made public through this script.
"""
import argparse
import hashlib
import os
import pathlib
import re
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import build_release  # noqa: E402  (REPOS, OWNER and STAGING have one home)
import scan_release  # noqa: E402

SECRETS_FILE = pathlib.Path.home() / ".zshrc.secrets"
FILL = re.compile(r"\{\{FILL:")


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def manifest(folder):
    """{relative path: sha256} as written by build_release.py."""
    return {l.split("  ", 1)[1]: l.split("  ", 1)[0] for l in (folder / "manifest.sha256").read_text().splitlines()}


def check_folder(name, folder):
    """Return a list of reasons this folder must not upload; empty means ready."""
    if not (folder / "manifest.sha256").exists():
        return ["not staged: run build_release.py"]
    problems, man = [], manifest(folder)
    on_disk = {p.relative_to(folder).as_posix() for p in folder.rglob("*") if p.is_file()} - {"manifest.sha256"}
    problems += [f"not in manifest: {f}" for f in sorted(on_disk - set(man))]
    problems += [f"missing or changed since build: {f}" for f, h in man.items()
                 if not (folder / f).exists() or sha(folder / f) != h]
    if build_release.REPOS[name] == "model":
        if FILL.search((folder / "README.md").read_text()):
            problems.append("model card still has {{FILL: ...}} slots")
        if not any(f.endswith(".safetensors") for f in man) or "adapter_config.json" not in man:
            problems.append("adapter weights not staged (serve/adapter/v4/ has no adapter_config.json + *.safetensors)")
    return problems


def token(read_value=True):
    """HF token from the environment or <local>/.zshrc.secrets, and where it came from; the value is never printed.

    With read_value=False (the dry run) only the source is located and the value is not kept."""
    if os.environ.get("HF_TOKEN"):
        return (os.environ["HF_TOKEN"] if read_value else None), "environment"
    if SECRETS_FILE.exists():
        for line in SECRETS_FILE.read_text().splitlines():
            m = re.match(r"\s*(?:export\s+)?HF_TOKEN=(['\"]?)(.+?)\1\s*$", line)
            if m:
                return (m.group(2) if read_value else None), "<local>/.zshrc.secrets"
    return None, "not found"


def describe(name, folder):
    kind = build_release.REPOS[name]
    man = manifest(folder) if (folder / "manifest.sha256").exists() else {}
    print(f"\n{build_release.OWNER}/{name}  ({kind}, private=True)")
    for f in sorted(man) + ["manifest.sha256"] * bool(man):
        p = folder / f
        print(f"  {p.stat().st_size:>11,d}  {f}" if p.exists() else f"  {'missing':>11}  {f}")


def make_public(api, repo, kind):
    """Set a verified repo public, confirm it reads public, and return its URL."""
    if hasattr(api, "update_repo_settings"):
        api.update_repo_settings(repo, private=False, repo_type=kind)
    else:                                                   # huggingface_hub before update_repo_settings existed
        api.update_repo_visibility(repo, private=False, repo_type=kind)
    if api.repo_info(repo, repo_type=kind).private:
        raise SystemExit(f"{repo} still reads private after the visibility change")
    return f"https://huggingface.co/{'datasets/' if kind == 'dataset' else ''}{repo}"


def upload(api, name, folder, tok):
    from huggingface_hub import hf_hub_download
    repo, kind = f"{build_release.OWNER}/{name}", build_release.REPOS[name]
    api.create_repo(repo, repo_type=kind, private=True, exist_ok=True)
    info = api.repo_info(repo, repo_type=kind)
    if not info.private:
        raise SystemExit(f"{repo} is not private: stopping before any upload")
    api.upload_folder(repo_id=repo, repo_type=kind, folder_path=str(folder),
                      commit_message="commissar release: staged by release_hf/build_release.py")
    info = api.repo_info(repo, repo_type=kind)
    man = manifest(folder)
    bad = [f for f, h in man.items()
           if sha(pathlib.Path(hf_hub_download(repo, f, repo_type=kind, revision=info.sha, token=tok))) != h]
    print(f"{repo}: private={info.private}, commit {info.sha[:7]}, {len(man) - len(bad)}/{len(man)} files match")
    if bad:
        raise SystemExit(f"mismatched: {bad[:5]}")


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--dry-run", action="store_true", help="list what would upload and every gate; no network")
    ap.add_argument("--only", action="append", choices=sorted(build_release.REPOS), help="repo to publish (repeatable)")
    ap.add_argument("--skip-model", action="store_true", help="publish the two datasets only")
    ap.add_argument("--make-public", action="store_true",
                    help="after the private upload verifies, make the repo public (PUBLIC_REPOS only)")
    args = ap.parse_args()
    names = args.only or [n for n in build_release.REPOS
                          if not (args.skip_model and build_release.REPOS[n] == "model")]
    not_public = [n for n in names if n not in build_release.PUBLIC_REPOS]
    if args.make_public and not_public:
        raise SystemExit(f"--make-public refused: {not_public} may not be made public; pass --only with "
                         f"{sorted(build_release.PUBLIC_REPOS)}")

    print("scan:", "running scan_release.py")
    scan_failed = scan_release.main() != 0
    blocked = {n: check_folder(n, build_release.STAGING / n) for n in names}
    tok, source = token(read_value=not args.dry_run)
    for n in names:
        describe(n, build_release.STAGING / n)
        print("  gate:", "ready" if not blocked[n] else "; ".join(blocked[n]))
    print(f"\nscan gate: {'FAILED' if scan_failed else 'passed'}; HF token: {source} (value not printed)")
    print("after verify: " + ("make public: " + ", ".join(names) if args.make_public else "repos stay private"))
    if args.dry_run:
        print("dry run: nothing created or uploaded")
        return 0
    if scan_failed or any(blocked.values()) or not tok:
        raise SystemExit("refusing to upload: fix the gates above (or pass --only/--skip-model for ready repos)")
    from huggingface_hub import HfApi
    api = HfApi(token=tok)
    for n in names:
        upload(api, n, build_release.STAGING / n, tok)
        if args.make_public:
            kind = build_release.REPOS[n]
            print(f"{build_release.OWNER}/{n}: public at {make_public(api, f'{build_release.OWNER}/{n}', kind)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
