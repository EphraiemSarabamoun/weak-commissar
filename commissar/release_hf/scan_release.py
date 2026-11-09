"""Scan every staged file before upload: secrets, emails, host paths, real and fleet names, operae and StewardBench names.

    python3 release_hf/scan_release.py            # after build_release.py; writes release_hf/scan_report.json

Every file listed in a staging folder's manifest.sha256 is read as text. A category marked "fail" must have zero hits
before publish_hf.py will upload; "review" hits are printed with context for a human to judge (synthetic data can
contain an invented person who shares a first name with someone real). Matches are reported with a short context, never
a secret-shaped value in full. Exit code 1 when any fail-category hit is present.
"""
import ast
import json
import os
import pathlib
import re
import struct
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
STAGING = ROOT / "release_hf" / "staging"
REPORT = ROOT / "release_hf" / "scan_report.json"
OPERAE = pathlib.Path.home() / "Desktop/research/loyalty-evals/_commissar/operae"
TRAINING = {"commissar-sft-private"}                         # repos whose rows a model trains on

SECRETS = re.compile(r"sk-ant-[A-Za-z0-9_-]{8,}|\bsk-[A-Za-z0-9]{20,}|gh[pousr]_[A-Za-z0-9]{20,}|github_pat_\w{20,}"
                     r"|xox[abprs]-[A-Za-z0-9-]{10,}|AKIA[0-9A-Z]{16}|\bhf_[A-Za-z0-9]{30,}|AIza[0-9A-Za-z_-]{30,}"
                     r"|-----BEGIN [A-Z ]*PRIVATE KEY|(?i:bearer)\s+[A-Za-z0-9._-]{20,}")
EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
HOST_PATH = re.compile(r"/(?:home|Users)/[A-Za-z0-9._-]+|~/[A-Za-z]|<tmp>/|[A-Z]:\\Users\\")
# The author and the seats and people around the pod. Names of friends are not listed beyond first names used as seats.
REAL_NAMES = re.compile(os.environ.get("SCAN_REAL_NAMES", r"(?!x)x"), re.I)  # names kept out of the public copy
SEAT_NAMES = re.compile(os.environ.get("SCAN_SEAT_NAMES", r"(?!x)x"), re.I)  # names kept out of the public copy
FLEET = re.compile(os.environ.get("SCAN_FLEET", r"(?!x)x"), re.I)  # names kept out of the public copy
# private network (<private-ip>/10), loopback and the local commissar server port fail; private LAN addresses are reviewed
# because invented scenarios use them (a printer at 192.168.1.45).
# The base model's tokenizer, to recognise a staged tokenizer.json whose vocabulary is the base's own.
BASE_TOKENIZERS = sorted(pathlib.Path.home().glob(".cache/huggingface/hub/models--Qwen--Qwen3.5-4B/snapshots/*/tokenizer.json"))
FLEET_NET = re.compile(r"\b100\.(?:6[4-9]|[7-9]\d|1[01]\d|12[0-7])\.\d{1,3}\.\d{1,3}\b|\b127\.0\.0\.1\b|localhost|:8417\b")
PRIVATE_IP = re.compile(r"\b(?:10|192\.168|172\.(?:1[6-9]|2\d|3[01]))\.\d{1,3}\.\d{1,3}(?:\.\d{1,3})?\b")


def operae_lexicon():
    """Every person, organisation, email domain, canary token and world id in operae's commissar specs and scenarios."""
    terms = set()
    for f in (OPERAE / "experiments/commissar/specs").glob("*.jsonl"):
        if "provenance" in f.name:
            continue
        for line in f.read_text().splitlines():
            r = json.loads(line)
            for role in (r.get("roles") or {}).values():
                if role.get("name") and role["name"] not in ("System", "Operations Steward"):
                    terms.add(role["name"])
                terms.update(a.split("@")[1] for a in role.get("addresses", []) if "@" in a)
            terms.update(c["token"] for c in r.get("canaries", []))
            if (r.get("factors") or {}).get("world"):
                terms.add(r["factors"]["world"])
    for f in (OPERAE / "scenarios").glob("*.yaml"):
        terms.update(m.strip().strip("'\"") for m in re.findall(r"^\s*(?:name|org|organisation|display_name):\s*(.+)$",
                                                                 f.read_text(), re.M))
    return sorted(t for t in terms if len(t) >= 4)


def bench_lexicon():
    """StewardBench principals' full names and organisations, which must not appear in training rows."""
    terms = set()
    for f in ("bench/items.jsonl", "bench/v2/items_v2.jsonl", "bench/validation.jsonl", "bench/v2/validation_v2.jsonl"):
        for line in (ROOT / f).read_text().splitlines():
            p = json.loads(line).get("principal") or {}
            if isinstance(p, str):
                p = ast.literal_eval(p) if p.startswith("{") else {}
            terms.update(v for k, v in p.items() if k in ("name", "org") and isinstance(v, str))
    return sorted(t for t in terms if len(t) >= 4)


def context(text, m):
    s = text[max(0, m.start() - 50):m.end() + 50].replace("\n", " ")
    return s if not SECRETS.search(m.group(0)) else s.replace(m.group(0), m.group(0)[:6] + "...")


def scannable_text(path):
    """(text to scan, exemption note or None). Two narrow exemptions, each recorded in the report:
    a .safetensors file is scanned as its JSON header only, since its body is raw weights whose bytes match the
    patterns at random ('<local>/r'); a tokenizer.json is scanned without its vocabulary and merges only when both equal
    the base model's (they hold ordinary tokens such as 'localhost' and 'the laptop'). Anything else is read
    whole, and a tokenizer whose vocabulary differs from the base's is read whole too."""
    if path.suffix == ".safetensors":
        with open(path, "rb") as f:
            n = struct.unpack("<Q", f.read(8))[0]
            return f.read(n).decode("utf-8", errors="replace"), "safetensors: JSON header only (tensor names, shapes, metadata)"
    if path.name == "tokenizer.json" and BASE_TOKENIZERS:
        tok = json.loads(path.read_text())
        base = json.loads(BASE_TOKENIZERS[0].read_text())["model"]
        pairs = lambda m: [x if isinstance(x, str) else " ".join(x) for x in (m or [])]   # merges as strings or pairs
        model = tok.get("model", {})
        if model.get("vocab") == base["vocab"] and pairs(model.get("merges")) == pairs(base.get("merges")):
            model["vocab"] = model["merges"] = "<identical to the base model's>"
            return (json.dumps(tok, ensure_ascii=False),
                    "tokenizer.json: vocabulary and merges identical to the base model's, not scanned")
    return path.read_text(errors="replace"), None


def scan_file(path, rel, repo, lex_operae, lex_bench):
    text, note = scannable_text(path)
    hits = {"_exemption": note} if note else {}

    def add(cat, m):
        hits.setdefault(cat, []).append({"match": m.group(0) if cat != "secret" else m.group(0)[:6] + "...",
                                         "context": context(text, m)})
    for cat, rx in (("secret", SECRETS), ("host_path", HOST_PATH), ("email", EMAIL), ("real_name", REAL_NAMES),
                    ("seat_name", SEAT_NAMES), ("fleet_name", FLEET), ("fleet_net", FLEET_NET),
                    ("private_ip", PRIVATE_IP)):
        for m in rx.finditer(text):
            add(cat, m)
    if repo in TRAINING and not rel.startswith("generation/") and rel != "README.md":
        for cat, lex in (("operae_name", lex_operae), ("bench_name", lex_bench)):
            for term in lex:
                for m in re.finditer(r"(?<!\w)" + re.escape(term) + r"(?!\w)", text):
                    add(cat, m)
    return hits


FAIL = {"secret", "host_path", "operae_name", "bench_name", "fleet_net", "fleet_name"}


def main():
    lex_operae, lex_bench = operae_lexicon(), bench_lexicon()
    report = {"lexicons": {"operae_terms": len(lex_operae), "bench_terms": len(lex_bench)}, "files": {}, "summary": {}}
    for manifest in sorted(STAGING.glob("*/manifest.sha256")):
        repo = manifest.parent.name
        for line in manifest.read_text().splitlines():
            rel = line.split("  ", 1)[1]
            hits = scan_file(manifest.parent / rel, rel, repo, lex_operae, lex_bench)
            note = hits.pop("_exemption", None)
            if note:
                report.setdefault("exemptions", {})[f"{repo}/{rel}"] = note
            report["files"][f"{repo}/{rel}"] = {c: {"count": len(v), "examples": v[:5]} for c, v in hits.items()}
            for c, v in hits.items():
                report["summary"].setdefault(c, {}).setdefault(repo, 0)
                report["summary"][c][repo] += len(v)
    report["fail_categories"] = sorted(FAIL)
    report["failed"] = {c: r for c, r in report["summary"].items() if c in FAIL}
    REPORT.write_text(json.dumps(report, indent=1, ensure_ascii=False) + "\n")
    print(json.dumps({"lexicons": report["lexicons"], "summary": report["summary"], "failed": report["failed"]}, indent=1))
    return 1 if report["failed"] else 0


if __name__ == "__main__":
    sys.exit(main())
