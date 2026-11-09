"""Arm R5 `rewrite` (prereg/R5.md): A0's episode with the kickoff and the principal's request replaced by the
commissar's frozen rewrite, so the task reaches the agent only through the commissar.

overlay() starts from commissar.py's verified arm `none` (A0, PROBE_V2 included) and changes exactly two texts:
spec.user (the kickoff) and the text of the principal's one opening request in the authenticated chat channel's
mailbox (commissar.chat_channel). The request keeps its sender and identity fields, so the world still marks it
authentic as the principal's (DECISIONS_v0.3 section 4); its content is the commissar's by Ephraiem's design.
Nothing else changes: system text, tool documentation, other messages, state, tools, rules, scoring, events
(including the principal's later message), end conditions and the follow-up.

check_rewrite strips exactly those two texts and the arm's labels and requires commissar.check_overlay to accept
what remains as A0's spec; opening_view builds castra's World for A0 and R5 and requires the opening states to
differ only in that one message's text, shown verbatim by the first chat read.

Usage (castra 8457977 on PYTHONPATH, Python 3.12):
  python3.12 rewrite_arm.py --released data/pilot.jsonl --rewrites steward/rewrite/frozen.jsonl \
      --rewrites-sha256 SHA --out specs/r5-rewrite.jsonl
"""
import argparse
import copy
import hashlib
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import commissar as C  # noqa: E402

ARM = "rewrite"


class RewriteError(C.OverlayError):
    """An R5 spec is not exactly A0's spec with the two rewritten texts."""


def _request_index(base):
    channel, request = C.chat_channel(base)
    box = base["state"]["mail"][channel]
    return channel, next(i for i, m in enumerate(box) if m is request or m == request)


def _check_text(text, what):
    if not isinstance(text, str) or not text.strip():
        raise RewriteError(f"the rewritten {what} is empty")
    if C.MID.search(text) or "{" in text or "}" in text:
        raise RewriteError(f"the rewritten {what} has a message id or a brace")


def overlay(base, bank_commit, row, frozen_sha256, build=None, released=None):
    """(run spec, provenance) for one cell; row is the cell's frozen.jsonl entry, which must carry a rewrite."""
    rw = row["rewrite"]
    if rw is None:
        raise RewriteError(f"{row['key']}: no rewrite (missing coverage)")
    user, request = rw["texts"]["user"], rw["texts"]["request"]
    for text, what, sha in ((user, "kickoff", rw["user_sha256"]), (request, "request", rw["request_sha256"])):
        _check_text(text, what)
        if C.sha256_text(text) != sha:
            raise RewriteError(f"{row['key']}: the frozen {what} does not hash to its sha256")
    inner, prov = C.overlay(base, "none", bank_commit, build=build, released=released)
    spec = copy.deepcopy(inner)
    channel, i = _request_index(base)
    spec["user"] = user
    spec["state"]["mail"][channel][i]["text"] = request
    spec["episode_id"] = f"{C.INSTRUMENT}.{C.base_key(base)}.{ARM}"
    spec["factors"] = {**inner["factors"], "steward": ARM}
    check_rewrite(base, spec, user, request)
    read = opening_view(base, spec, request)
    prov = dict(prov)
    prov.update({"arm": ARM, "search_arm": "R5", "base_arm": "none", "base_arm_spec_sha256": prov["spec_sha256"],
                 "cell": row["key"], "channel": channel,
                 "original_user_sha256": C.sha256_text(base["user"]),
                 "original_request_sha256": C.sha256_text(base["state"]["mail"][channel][i]["text"]),
                 "rewrite_user_sha256": rw["user_sha256"], "rewrite_request_sha256": rw["request_sha256"],
                 "rewrite_generator": row["generator"], "rewrite_response_model": rw["response_model"],
                 "rewrite_attempt": rw["attempt"], "rewrite_seed": rw["seed"], "rewrite_temperature": rw["temperature"],
                 "rewrite_call_sha256": rw["call_sha256"], "rewrites_frozen_file_sha256": frozen_sha256,
                 "opening_read_tool": channel, "opening_read_sha256": C.sha256_text(read),
                 "episode_id": spec["episode_id"], "spec_sha256": C.spec_sha256(spec)})
    return spec, prov


def check_rewrite(base, spec, user, request):
    """Refuse unless spec is A0's spec with exactly the kickoff and the principal's request text replaced by the
    frozen rewrite, and the arm's labels. Returns True."""
    channel, i = _request_index(base)
    if spec.get("user") != user or spec["state"]["mail"][channel][i].get("text") != request:
        raise RewriteError("the kickoff or the request is not the frozen rewrite")
    msg, orig = spec["state"]["mail"][channel][i], base["state"]["mail"][channel][i]
    if {k: v for k, v in msg.items() if k != "text"} != {k: v for k, v in orig.items() if k != "text"}:
        raise RewriteError("the request's sender or identity fields changed")
    stripped = copy.deepcopy(spec)
    stripped["user"] = base["user"]
    stripped["state"]["mail"][channel][i]["text"] = orig["text"]
    stripped["episode_id"] = f"{C.INSTRUMENT}.{C.base_key(base)}.none"
    stripped["factors"] = {**spec["factors"], "steward": "none"}
    C.check_overlay(base, stripped, "none")
    if spec["episode_id"] != f"{C.INSTRUMENT}.{C.base_key(base)}.{ARM}" or spec["factors"].get("steward") != ARM:
        raise RewriteError("the episode id or factors are not this arm's")
    return True


def opening_view(base, spec, request):
    """The first chat read on R5's opening state. Refuses unless castra's World for R5 and for the base differ only
    in the request's text, and the read shows the rewrite verbatim."""
    from castra.arena import engine as E
    wb, ws = E.World(base), E.World(spec)
    channel, i = _request_index(base)
    sb, ss = copy.deepcopy(wb.state), copy.deepcopy(ws.state)
    if ss["mail"][channel][i].get("text") != request:
        raise RewriteError("the world's opening request is not the rewrite")
    ss["mail"][channel][i]["text"] = sb["mail"][channel][i]["text"]
    if ss != sb:
        raise RewriteError("the opening state differs outside the request's text")
    if not ws.authentic("principal", channel):
        raise RewriteError("the world does not mark the principal authentic on the chat channel")
    entry = ws.call(channel, {})
    read = entry["response"]["text"]
    if entry["response"]["is_error"] or json.dumps(request, ensure_ascii=False) not in read:
        raise RewriteError("the opening chat read does not show the rewrite verbatim")
    return read


def main(argv=None):
    import compile as K
    import pins
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--released", required=True)
    p.add_argument("--rewrites", required=True)
    p.add_argument("--rewrites-sha256", required=True)
    p.add_argument("--out", required=True)
    a = p.parse_args(argv)
    if K.file_sha256(a.rewrites) != a.rewrites_sha256:
        raise SystemExit(f"{a.rewrites} is not the frozen rewrites file (sha256 {a.rewrites_sha256})")
    try:
        engine_sha256 = pins.check_imported()
    except pins.PinError as ex:
        raise SystemExit(f"rewrite_arm: refused: {ex}")
    build = {"castra_commit": pins.CASTRA_COMMIT, "engine_sha256": engine_sha256}
    released = {"hub_repo": "ephraiemsam16/operae-private", "hub_commit": K.HUB_COMMIT, "file": K.RELEASED_FILE,
                "file_sha256": K.RELEASED_FILE_SHA256}
    rows = {r["key"]: r for r in map(json.loads, open(a.rewrites))}
    pairs, missing = [], []
    for b in K.released_bases(a.released):
        f = b["factors"]
        row = rows[f"{f['world'][4:7]}.{f['beneficiary']}.{f['principal']}"]
        if row["rewrite"] is None:
            missing.append(row["key"])
            continue
        pairs.append(overlay(b, K.BANK_COMMIT, row, a.rewrites_sha256, build, released))
    out = pathlib.Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("".join(json.dumps(s, sort_keys=True, ensure_ascii=False) + "\n" for s, _ in pairs))
    prov = out.with_suffix(".provenance.jsonl")
    prov.write_text("".join(json.dumps(p_, sort_keys=True) + "\n" for _, p_ in pairs))
    print(f"{out}: {len(pairs)} specs (missing cells: {missing or 'none'}), sha256 "
          f"{hashlib.sha256(out.read_bytes()).hexdigest()}")
    print(f"{prov}: sha256 {hashlib.sha256(prov.read_bytes()).hexdigest()}")


if __name__ == "__main__":
    sys.exit(main())
