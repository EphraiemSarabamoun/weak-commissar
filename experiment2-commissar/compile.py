"""Compile the commissar experiment's run specs from the released operae v0.2 primary block.

The bases are the released pilot tier's 32 primary-block neutral rows (Hugging Face ephraiemsam16/operae-private at
8042921, data/pilot.jsonl; bank operae dc9a0d6). Each released row carries its spec as a JSON string and its
spec_sha256; this script recomputes every hash with castra's spec_sha256, keeps the rows whose factors say primary
block and whose condition is neutral, and, when --run-specs is given, also checks that the same 32 hashes are the
neutral rows the Sonnet v0.2 run of record used (operae prompt-search specs/v02-operae.jsonl), so A0 on Haiku and
that run share their bases byte for byte.

Usage (castra on PYTHONPATH, Python 3.12):
  python3.12 compile.py --released PILOT.jsonl --arm none --out specs/a0.jsonl [--run-specs v02-operae.jsonl]
The imported castra must be the pinned 8457977 export (pins.py checks its engine and package bytes); compile refuses
anything else, and refuses a --castra-commit that is not the pin.
Writes OUT and, beside it, OUT with the suffix .provenance.jsonl (one provenance record per spec; castra v1.2
specs have no provenance field). The prompted arm also needs --messages (a frozen messages file); it is not
compiled tonight.
"""
import argparse
import hashlib
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import commissar as C  # noqa: E402
import authority as AU  # noqa: E402
import pins  # noqa: E402

BANK_COMMIT = "dc9a0d681a6a487f165a0894a5fa0208646288a4"
HUB_COMMIT = "8042921da9941a11a38d4466263a3093f0a81483"
RELEASED_FILE = "data/pilot.jsonl"
RELEASED_FILE_SHA256 = "ea9fd060b6a7fab4bb43eeae2b91ae4d844e7df64f1797e8a2cbb7f525f0cb8e"
N_BASES = 32


def file_sha256(path):
    return hashlib.sha256(pathlib.Path(path).read_bytes()).hexdigest()


def released_bases(path):
    """The released primary-block neutral specs, in file order, each hash-checked against its row's spec_sha256."""
    if file_sha256(path) != RELEASED_FILE_SHA256:
        raise SystemExit(f"{path} is not the released pilot tier (sha256 {RELEASED_FILE_SHA256})")
    out = []
    with open(path) as f:
        rows = [json.loads(line) for line in f]
    for row in rows:
        spec = json.loads(row["spec"]) if isinstance(row["spec"], str) else row["spec"]
        if C.spec_sha256(spec) != row["spec_sha256"]:
            raise SystemExit(f"{row['id']}: the released spec does not hash to its spec_sha256")
        if spec["factors"].get("block") == "primary" and spec["condition"] == "neutral":
            out.append(spec)
    if len(out) != N_BASES:
        raise SystemExit(f"expected {N_BASES} primary-block neutral rows, found {len(out)}")
    return out


def check_run_specs(bases, path):
    """The neutral rows of the Sonnet v0.2 run of record must be exactly these bases, by spec_sha256."""
    with open(path) as f:
        run = {C.spec_sha256(s) for s in map(json.loads, f) if s["condition"] == "neutral"}
    mine = {C.spec_sha256(b) for b in bases}
    if run != mine:
        raise SystemExit(f"the run-of-record neutral specs differ from the released bases: "
                         f"{len(run - mine)} only in the run, {len(mine - run)} only released")


def prompted(bases, path, want_sha256, build, released, arm="prompted"):
    """(spec, provenance) for every base whose world and principal name has a frozen steward message, in base order.
    The file must hash to want_sha256; keys frozen without a message drop both twins (prereg/A1.md D3)."""
    if not path or not want_sha256:
        raise SystemExit("the prompted arm needs --messages and --messages-sha256")
    if file_sha256(path) != want_sha256:
        raise SystemExit(f"{path} is not the frozen messages file (sha256 {want_sha256})")
    with open(path) as f:
        frozen = {r["key"]: r for r in map(json.loads, f)}
    out = []
    for b in bases:
        r = frozen.get(f"{b['factors']['world']}.{b['factors']['principal']}")
        if r is None:
            raise SystemExit(f"{b['episode_id']}: its key is not in the frozen file")
        m = r["message"]
        if m is None:
            continue
        if C.sha256_text(m["text"]) != m["sha256"]:
            raise SystemExit(f"{r['key']}: the frozen text does not hash to its sha256")
        message = {"text": m["text"], "prompt_sha256": m["prompt_sha256"], "generator": r["generator"],
                   "source": "generated", "seed": m["seed"], "temperature": m["temperature"],
                   "attempt": m["attempt"], "frozen_file_sha256": want_sha256}
        out.append(C.overlay(b, arm, BANK_COMMIT, message=message, build=build, released=released))
    return out


def authority(bases, a, build, released):
    """(spec, provenance) for the wish or endorsed arm (authority.py): the principal's frozen line on every base, and
    for endorsed also the steward's frozen A1L message, on the keys that have one and are not excluded."""
    if not a.lines or file_sha256(a.lines) != a.lines_sha256:
        raise SystemExit(f"{a.lines} is not the frozen principal lines file (sha256 {a.lines_sha256})")
    lines = json.loads(pathlib.Path(a.lines).read_text())
    line = lines["wish"] if a.arm == "wish" else lines["endorse"]
    drop = set(a.exclude_keys)
    if a.arm == "wish":
        return [AU.overlay(b, "wish", BANK_COMMIT, line, build=build, released=released) for b in bases
                if f"{b['factors']['world'][4:7]}.{b['factors']['principal']}" not in drop]
    steward = {s["episode_id"].split(".")[1] + "." + s["factors"]["principal"]: (s, p) for s, p in
               prompted(bases, a.messages, a.messages_sha256, build, released, arm="loyal")}
    out = []
    for b in bases:
        key = f"{b['factors']['world'][4:7]}.{b['factors']['principal']}"
        if key in drop or key not in steward:
            continue
        sprov = steward[key][1]
        d = steward[key][0]["events"][0]["do"][0]["deliver"]
        message = {"text": d["text"].replace("{{", "{").replace("}}", "}"), "prompt_sha256": sprov["prompt_sha256"],
                   "generator": sprov["generator"], "source": sprov["message_source"],
                   **{k: sprov[k] for k in ("seed", "temperature", "attempt", "frozen_file_sha256") if k in sprov}}
        out.append(AU.overlay(b, "endorsed", BANK_COMMIT, line, message=message, build=build, released=released))
    return out


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--released", required=True)
    p.add_argument("--arm", choices=C.ARMS + AU.ARMS, required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--run-specs")
    p.add_argument("--castra-commit", help="optional; must name the pinned commit (pins.CASTRA_COMMIT)")
    p.add_argument("--messages", help="the frozen steward messages (prompted arm only)")
    p.add_argument("--messages-sha256", help="the frozen file's sha256, which must match (prompted arm only)")
    p.add_argument("--lines", help="the frozen principal lines (wish and endorsed arms)")
    p.add_argument("--lines-sha256", help="the frozen lines file's sha256, which must match")
    p.add_argument("--exclude-keys", nargs="*", default=[], help="world.principal keys left out by pre-registration")
    a = p.parse_args(argv)
    # The castra this process imports must be the pinned export, by its bytes (Codex c2-verify F4): a commit label
    # proves nothing about the directory on PYTHONPATH. The provenance then names the pin it was checked against.
    if a.castra_commit and not pins.CASTRA_COMMIT.startswith(a.castra_commit):
        raise SystemExit(f"compile: refused: --castra-commit {a.castra_commit} is not the pinned {pins.CASTRA_COMMIT}")
    try:
        engine_sha256 = pins.check_imported()
    except pins.PinError as ex:
        raise SystemExit(f"compile: refused: {ex}")
    build = {"castra_commit": pins.CASTRA_COMMIT, "engine_sha256": engine_sha256}
    released = {"hub_repo": "ephraiemsam16/operae-private", "hub_commit": HUB_COMMIT, "file": RELEASED_FILE,
                "file_sha256": RELEASED_FILE_SHA256}
    bases = released_bases(a.released)
    if a.run_specs:
        check_run_specs(bases, a.run_specs)
    if a.arm in AU.ARMS:
        pairs = authority(bases, a, build, released)
    elif a.arm in C.STEWARD_ARMS:
        pairs = prompted(bases, a.messages, a.messages_sha256, build, released, arm=a.arm)
    else:
        pairs = [C.overlay(b, a.arm, BANK_COMMIT, build=build, released=released) for b in bases]
    out = pathlib.Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("".join(json.dumps(s, sort_keys=True, ensure_ascii=False) + "\n" for s, _ in pairs))
    prov = out.with_suffix(".provenance.jsonl")
    prov.write_text("".join(json.dumps(p, sort_keys=True) + "\n" for _, p in pairs))
    print(f"{out}: {len(pairs)} specs, arm {a.arm}, engine {build['engine_sha256'][:12]}, sha256 {file_sha256(out)}")
    print(f"{prov}: sha256 {file_sha256(prov)}")


if __name__ == "__main__":
    sys.exit(main())
