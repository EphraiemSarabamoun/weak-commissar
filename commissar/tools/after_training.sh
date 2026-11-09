#!/usr/bin/env bash
# After a fine-tune: poll the run, fetch the adapter, load it into the server's LoRA slot, verify it, run the gates.
#
#   tools/after_training.sh [--version v5] [--label L] [--adapter-dir D] [--holdout F] [--keep-loaded] [RUN_ID]
#   tools/after_training.sh --dry-run DIR [--version ...]     skip polling and download; load DIR, run short gates,
#                                                             then restore the slot (used to test this script)
#
# --version vN sets the defaults: label steward-lora-vN, adapter dir serve/adapter/vN, holdout
# data/steward_sft_vN_holdout.jsonl. RUN_ID defaults to the id in the newest runs/*_train/response.json.
#
# The running server has one LoRA slot, always served as `steward-lora` (serve/settings.py), and it is never
# restarted here. So the new adapter is served as steward-lora while the slot points at its folder, every result
# is filed under the label, and the slot's loaded folder is checked before and after each gate; a gate whose
# slot changed under it is marked invalid. At the end the slot goes back to the folder it held when the script
# started (round 1's v4), unless --keep-loaded (round 2 keeps v5 loaded, the manager's decision of 23:01). The
# slot is always pointed at one adapter folder, never at serve/adapter itself, where two adapter folders make the
# server refuse both. The sha256 of adapter_model.safetensors is recorded with the slot's loaded_dir before and
# after every gate (status file keys gate_<name>, and PROVENANCE.md beside each gate's results).
#
# Gates (v2.2 system prompt throughout), each reported by pod-tell to agent M and the manager as soon as it exists:
#   1. six R5 cells: identity and added-guidance counts (tools/qa/r5_cells_gate.py; R5ft2's launch rule)
#   2. the holdout's rewrite rows: identity, added guidance, the rules and the Sonnet fidelity judge
#      (tools/qa/eval_rewrites.py --judge)
#   3. StewardBench v2 items under v2.2 (bench/v2/stewardbench_v2_2_as.py, results under the label)
# Everything here is free: poll.py and download.py are read-only Adaption calls, model calls go to the local server,
# and the only paid-like calls are the isolated Sonnet judge calls of gates 2 and 3.
set -uo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO"
PY=.venv/bin/python            # the Adaption SDK venv (poll, download)
SYS_PY=python3                 # bench and eval scripts (system site-packages)
URL=http://127.0.0.1:8417
SERVED=steward-lora            # the only LoRA name the running server answers to
STATUS_DIR=<inbox>/post-train2
LOGS="$REPO/bench/rewrite_eval/logs"
POLL_EVERY=${POLL_EVERY:-120}  # seconds between status checks (overridable for tests)
MAX_WAIT=$((6 * 3600))         # stop waiting (not the job) after six hours
TELL_TO=${TELL_TO:-"agent M|the manager agent"}   # pod-tell recipients, |-separated (empty: no messages)

VERSION=v5; LABEL=""; ADAPTER_DIR=""; HOLDOUT=""; KEEP=0; DRY=""; RUN_ID=""
while [ $# -gt 0 ]; do
  case "$1" in
    --version) VERSION="$2"; shift 2 ;;
    --label) LABEL="$2"; shift 2 ;;
    --adapter-dir) ADAPTER_DIR="$2"; shift 2 ;;
    --holdout) HOLDOUT="$2"; shift 2 ;;
    --keep-loaded) KEEP=1; shift ;;
    --dry-run) DRY="$2"; shift 2 ;;
    -*) echo "unknown option $1" >&2; exit 2 ;;
    *) RUN_ID="$1"; shift ;;
  esac
done
LABEL=${LABEL:-steward-lora-$VERSION}
ADAPTER_DIR=$(realpath -m "${ADAPTER_DIR:-$REPO/serve/adapter/$VERSION}")
HOLDOUT=${HOLDOUT:-data/steward_sft_${VERSION}_holdout.jsonl}
STATUS=$STATUS_DIR/after_training_${LABEL}${DRY:+_dryrun}.json
mkdir -p "$LOGS" "$STATUS_DIR"

say() { echo "$(date +%H:%M:%S) $*"; }
fail() { say "FAILED: $1"; write_status "failed" "$1"; tell "$LABEL: FAILED: $1"; restore_slot; exit "${2:-1}"; }

tell() {   # tell MESSAGE : one brief pod message to each recipient (never in a dry run)
  [ -n "$DRY" ] && { say "(dry run, not sent) $1"; return 0; }
  local IFS='|'; for who in $TELL_TO; do [ -n "$who" ] && pod-tell --wake "$who" "agent D: $1" >/dev/null 2>&1; done; return 0
}

write_status() {   # write_status STATE DETAIL [KEY JSON] : merge into one JSON summary the manager and the report read
  "$SYS_PY" - "$1" "$2" "${RUN_ID:-}" "$ADAPTER_DIR" "$STATUS" "${3:-}" "${4:-null}" <<'EOF'
import json, sys, time
state, detail, run_id, adapter, path, key, value = sys.argv[1:8]
try:
    prev = json.load(open(path))
except Exception:
    prev = {}
prev.update(state=state, detail=detail, run_id=run_id, adapter_dir=adapter, updated=time.strftime("%Y-%m-%d %H:%M:%S"))
if key:
    prev[key] = json.loads(value)
json.dump(prev, open(path, "w"), indent=1)
EOF
}

adapter_sha() {   # sha256 of the adapter weights in ADAPTER_DIR (empty if absent)
  sha256sum "$ADAPTER_DIR/adapter_model.safetensors" 2>/dev/null | cut -d' ' -f1
}

slot_dir() {   # the folder the slot has loaded, or empty
  curl -s "$URL/admin/adapter" | "$SYS_PY" -c "import json,sys; print(json.load(sys.stdin).get('loaded_dir') or '')"
}

newest_run_id() {   # the run id recorded by tools/train.py in the newest runs/*_train/response.json
  local f
  f=$(ls -1d runs/*_train 2>/dev/null | sort | tail -1)
  [ -n "$f" ] && [ -f "$f/response.json" ] || return 1
  "$SYS_PY" -c "import json,sys; print(json.load(open(sys.argv[1]))['id'])" "$f/response.json"
}

poll_until_done() {   # poll every POLL_EVERY s; succeeded -> 0, failed or cancelled -> exit 3, timeout -> exit 4
  local waited=0 line status empty=0
  while :; do
    line=$("$PY" tools/poll.py --run-id "$RUN_ID" 2>&1 | grep -E "^run " | tail -1)
    status=$(echo "$line" | sed -n 's/.*status=\([a-z]*\).*/\1/p')
    say "poll: ${line:-no status line}"
    if [ -z "$status" ]; then   # an unknown run id or an API error: give up after three in a row
      empty=$((empty + 1)); [ "$empty" -ge 3 ] && fail "no status for run $RUN_ID after 3 polls (bad id or API error)" 3
    else
      empty=0
    fi
    case "$status" in
      succeeded) return 0 ;;
      failed|cancelled) fail "training run $RUN_ID ended $status: $line" 3 ;;
    esac
    [ "$waited" -ge "$MAX_WAIT" ] && fail "stopped waiting after $MAX_WAIT s; the run continues ($line)" 4
    sleep "$POLL_EVERY"; waited=$((waited + POLL_EVERY))
  done
}

fetch_adapter() {   # download (free) and copy the unpacked checkpoint into ADAPTER_DIR
  local out ckpt
  if [ -d "$ADAPTER_DIR" ] && [ -n "$(ls -A "$ADAPTER_DIR" 2>/dev/null)" ]; then
    fail "$ADAPTER_DIR already holds files; not overwriting (move them aside first)" 5
  fi
  out=$("$PY" tools/download.py --run-id "$RUN_ID" 2>&1); echo "$out"
  ckpt=$(echo "$out" | sed -n 's/.*extracted [0-9]* entries to \(.*\)$/\1/p' | tail -1)
  [ -n "$ckpt" ] && [ -d "$ckpt" ] || fail "download did not report an extracted checkpoint" 6
  mkdir -p "$ADAPTER_DIR" && cp -r "$ckpt"/. "$ADAPTER_DIR"/
  [ -f "$ADAPTER_DIR/adapter_config.json" ] || fail "no adapter_config.json in $ADAPTER_DIR" 6
  [ -f "$ADAPTER_DIR/adapter_model.safetensors" ] || fail "no adapter_model.safetensors in $ADAPTER_DIR" 6
  say "adapter files in $ADAPTER_DIR"
}

hot_load() {   # hot_load DIR : point the slot at DIR; prints the server's adapter status JSON
  curl -s -X POST "$URL/admin/adapter" -H 'Content-Type: application/json' \
       -d "$("$SYS_PY" -c 'import json,sys; print(json.dumps({"dir": sys.argv[1]}))' "$1")"
}

verify_loaded() {   # verify_loaded JSON DIR : ready, loaded from DIR, keys loaded, no error
  "$SYS_PY" - "$1" "$2" <<'EOF' || return 1
import json, os, sys
s, want = json.loads(sys.argv[1]), os.path.realpath(sys.argv[2])
print(f"adapter: ready={s.get('ready')} loaded_dir={s.get('loaded_dir')} loaded_keys={s.get('loaded_keys')} "
      f"dropped_keys={s.get('dropped_keys')} error={s.get('last_error')}")
ok = (s.get("ready") and s.get("loaded") and not s.get("last_error") and (s.get("loaded_keys") or 0) > 0
      and os.path.realpath(s.get("loaded_dir") or "") == want)
if s.get("dropped_keys"):
    print("WARNING: dropped keys (vision or multi-token-prediction weights the text model does not have)")
sys.exit(0 if ok else 1)
EOF
}

differs_from_base() {   # temperature-0 replies of the slot vs steward-base on two StewardBench items
  "$SYS_PY" - "$SERVED" <<'EOF'
import json, sys
sys.path.insert(0, "bench"); sys.path.insert(0, "bench/v2")
import requests, render, spec_v2
items = spec_v2.common.read_jsonl(spec_v2.ITEMS_FILE)[:2]
tpl = open("bench/v2/steward_prompt_v2_2.txt").read().strip()
same = 0
for it in items:
    outs = []
    for model in ("steward-base", sys.argv[1]):
        body = {"model": model, "temperature": 0, "max_tokens": 120, "messages": [
            {"role": "system", "content": render.steward_system_prompt(it, tpl)},
            {"role": "user", "content": render.steward_user_message(it)}]}
        outs.append(requests.post("http://127.0.0.1:8417/v1/chat/completions", json=body, timeout=600).json()
                    ["choices"][0]["message"]["content"])
    same += outs[0] == outs[1]
    print(f"{it['item_id']}: {'IDENTICAL' if outs[0] == outs[1] else 'differs'}")
sys.exit(1 if same == len(items) else 0)
EOF
}

guarded() {   # guarded NAME OUTDIR CMD... : run one gate; the slot must hold ADAPTER_DIR, same weights, throughout
  local name="$1" outdir="$2"; shift 2
  local before after sha_before sha_after rc record
  before=$(slot_dir); sha_before=$(adapter_sha)
  "$@" > "$LOGS/${LABEL}_${name}.log" 2>&1; rc=$?
  after=$(slot_dir); sha_after=$(adapter_sha)
  record=$("$SYS_PY" -c 'import json,sys; print(json.dumps(dict(zip(("slot_before", "slot_after",
    "adapter_sha256_before", "adapter_sha256_after", "exit", "at"), sys.argv[1:]))))' \
    "$before" "$after" "$sha_before" "$sha_after" "$rc" "$(date '+%Y-%m-%d %H:%M:%S')")
  write_status "gating" "$name exit $rc" "gate_$name" "$record"
  mkdir -p "$outdir"
  printf '# Provenance: %s, gate %s\n\nServed as %s while the LoRA slot held %s (loaded_dir before: %s; after: %s).\nadapter_model.safetensors sha256 before %s, after %s. Exit %s, %s.\n' \
    "$LABEL" "$name" "$SERVED" "$ADAPTER_DIR" "$before" "$after" "$sha_before" "$sha_after" "$rc" \
    "$(date '+%Y-%m-%d %H:%M')" > "$outdir/PROVENANCE.md"
  if [ "$before" != "$ADAPTER_DIR" ] || [ "$after" != "$ADAPTER_DIR" ] || [ "$sha_before" != "$sha_after" ]; then
    say "INVALID: slot or weights changed during $name (slot $before -> $after, sha $sha_before -> $sha_after)"
    write_status "invalid" "slot or weights changed during $name" "invalid_$name" "true"; return 9
  fi
  say "$name exit $rc (slot held $ADAPTER_DIR, sha256 ${sha_before:0:16}..., before and after)"; return "$rc"
}

gate_line() {   # gate_line KIND FILE : the one-line summary of a gate's result for pod-tell
  "$SYS_PY" - "$1" "$2" <<'EOF'
import json, sys
kind, path = sys.argv[1:3]
s = json.load(open(path))
if kind == "r5":
    print(f"6 R5 cells: identical {s['identical']}/6, guidance added {s['guidance_added']}/6 "
          f"(R5ft2 launch rule {'MET' if s['r5ft2_launch_rule_met'] else 'NOT met'})")
elif kind == "rw":
    j = s.get("judge") or {}
    print(f"holdout rewrites ({s['rows']}): identical {s['identical']}, guidance added {s['guidance_added']}, "
          f"all rules {s['passes_all_rules']}, judge acceptable {j.get('acceptable', 'n/a')}/{j.get('judged', 'n/a')}")
else:
    print(f"StewardBench v2.2 macro {100 * s['macro_accuracy']['value']:.1f}% "
          f"[{100 * s['macro_accuracy']['ci95'][0]:.1f}, {100 * s['macro_accuracy']['ci95'][1]:.1f}], "
          f"endorsement {100 * s['forged_approval_endorsement_rate']['value']:.0f}%, "
          f"stay-quiet false alarms {100 * s['false_alarm_rate_stay_quiet']['value']:.0f}%")
EOF
}

run_gates() {   # run_gates FULL|DRY : the three gates; each result is told as soon as it exists
  local limit=() tag rw_dir sb_dir
  [ "$1" = DRY ] && limit=(--limit 2)
  tag="_$(basename "$HOLDOUT" .jsonl | sed 's/^steward_sft_//')"
  [ "$(realpath "$HOLDOUT")" = "$(realpath data/steward_sft_v4_holdout.jsonl)" ] && tag=""
  rw_dir="bench/rewrite_eval/${LABEL}_system${tag}"
  sb_dir="bench/v2/results_v2_2/$LABEL"
  if guarded r5cells "bench/r5_cells/$LABEL" "$SYS_PY" tools/qa/r5_cells_gate.py --model "$SERVED" --label "$LABEL"; then
    tell "$LABEL $(gate_line r5 "bench/r5_cells/$LABEL/summary.json")"
  fi
  if [ "$1" = DRY ]; then
    guarded rewrites "$rw_dir" "$SYS_PY" tools/qa/eval_rewrites.py --model "$SERVED" --label "$LABEL" \
      --holdout "$HOLDOUT" "${limit[@]}" && say "$(gate_line rw "$rw_dir/summary.json")"
    "$SYS_PY" bench/v2/stewardbench_v2_2.py check || return 1
    return 0
  fi
  ( guarded rewrites "$rw_dir" "$SYS_PY" tools/qa/eval_rewrites.py --model "$SERVED" --label "$LABEL" \
      --holdout "$HOLDOUT" --judge && tell "$LABEL $(gate_line rw "$rw_dir/summary.json")" ) &
  local p1=$!
  ( guarded stewardbench "$sb_dir" "$SYS_PY" bench/v2/stewardbench_v2_2_as.py --label "$LABEL" --served "$SERVED" \
      && tell "$LABEL $(gate_line sb "$sb_dir/scores.json")" ) &
  local p2=$!
  wait "$p1"; local r1=$?; wait "$p2"; local r2=$?
  [ "$(slot_dir)" = "$ADAPTER_DIR" ] || { say "INVALID: slot moved during the gates"; return 9; }
  [ "$r1" = 0 ] && [ "$r2" = 0 ] || { say "a gate failed (rewrites $r1, StewardBench $r2)"; return 1; }
}

RESTORE_DIR=$(slot_dir)   # what the slot served before this script; the rollback state
restore_slot() {   # point the slot back at RESTORE_DIR (or leave it, with --keep-loaded)
  [ "$KEEP" = 1 ] && { say "keeping the slot on $(slot_dir)"; return 0; }
  [ -n "$RESTORE_DIR" ] || return 0
  [ "$(slot_dir)" = "$RESTORE_DIR" ] && return 0
  verify_loaded "$(hot_load "$RESTORE_DIR")" "$RESTORE_DIR" && say "slot restored to $RESTORE_DIR"
}

# ---- main -----------------------------------------------------------------------------------------------------
if [ -n "$DRY" ]; then
  ADAPTER_DIR=$(realpath "$DRY"); RUN_ID="dry-run"; LABEL="dryrun-$LABEL"   # never file test output under the real label
  write_status "dry-run" "loading $ADAPTER_DIR"
  verify_loaded "$(hot_load "$ADAPTER_DIR")" "$ADAPTER_DIR" || fail "dry-run adapter did not load"
  differs_from_base || say "WARNING: the slot's replies are identical to steward-base on both items"
  run_gates DRY || fail "dry-run gates failed"
  restore_slot
  write_status "dry-run ok" "all stages passed on $ADAPTER_DIR"
  exit 0
fi

RUN_ID="${RUN_ID:-$(newest_run_id)}" || true
[ -n "${RUN_ID:-}" ] || fail "no RUN_ID given and no runs/*_train/response.json found" 2
say "label $LABEL, adapter dir $ADAPTER_DIR, holdout $HOLDOUT, slot before: ${RESTORE_DIR:-none}"
write_status "polling" "waiting for training run $RUN_ID"
poll_until_done
write_status "downloading" "run $RUN_ID succeeded"
fetch_adapter
SHA=$(adapter_sha)
write_status "downloaded" "adapter files in $ADAPTER_DIR" "adapter_sha256" "\"$SHA\""
verify_loaded "$(hot_load "$ADAPTER_DIR")" "$ADAPTER_DIR" || fail "adapter did not load from $ADAPTER_DIR" 7
differs_from_base || fail "the adapter's replies are identical to steward-base: it looks inert" 8
write_status "live" "$LABEL served as $SERVED from $ADAPTER_DIR; gates running"
tell "$LABEL (run $RUN_ID) loaded, differs from base; served as $SERVED, slot $ADAPTER_DIR, adapter_model.safetensors sha256 $SHA."
run_gates FULL || fail "gates did not complete cleanly (see $LOGS/${LABEL}_*.log)" 9
"$SYS_PY" tools/qa/compare_round2.py --label "$LABEL" --holdout "$HOLDOUT" > "$LOGS/${LABEL}_gates.log" 2>&1 \
  && say "gates table: bench/gates_${LABEL}.md"
restore_slot
[ "$KEEP" = 1 ] && tell "$LABEL gates done (bench/gates_${LABEL}.md); slot LEFT on $(slot_dir), sha256 $(adapter_sha)."
write_status "done" "gates finished; table in bench/gates_${LABEL}.md; slot on $(slot_dir)"
say "done"
