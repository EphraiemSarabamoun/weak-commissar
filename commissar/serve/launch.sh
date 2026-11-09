#!/usr/bin/env bash
# Start the commissar server in its own detached tmux session, commissar-serve.
#
# Refuses when the session already exists, when the GPU has under 12 GiB free
# (the server re-checks before loading), or when the weights are not cached.
# Runs offline from the HF cache. Logs go to serve/logs/server.log.
# Usage: serve/launch.sh [--adapter-dir PATH] [--port N]   (extra args go to server.py)
set -euo pipefail

SERVE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SESSION=commissar-serve
TMUX_BIN=/usr/local/bin/tmux          # 3.6a; /usr/bin/tmux is 3.2a
[ -x "$TMUX_BIN" ] || TMUX_BIN=/usr/bin/tmux
PY="$SERVE_DIR/.venv/bin/python"
MIN_FREE_MIB=$((12 * 1024))

if "$TMUX_BIN" has-session -t "=$SESSION" 2>/dev/null; then
  echo "tmux session $SESSION already exists; not starting a second server" >&2
  exit 1
fi
free_mib=$(nvidia-smi --id=0 --query-gpu=memory.free --format=csv,noheader,nounits | head -1)
if [ "$free_mib" -lt "$MIN_FREE_MIB" ]; then
  echo "only ${free_mib} MiB free on GPU 0; need ${MIN_FREE_MIB}. Not starting (the other GPU tenant is left alone)." >&2
  exit 2
fi
[ -x "$PY" ] || { echo "missing $PY; see serve section of Human.md to build the venv" >&2; exit 1; }

mkdir -p "$SERVE_DIR/logs"
args=""; [ $# -gt 0 ] && args=$(printf ' %q' "$@")
qpy=$(printf %q "$PY"); qdir=$(printf %q "$SERVE_DIR")   # quoted for the tmux shell string
"$TMUX_BIN" new-session -d -s "$SESSION" -c "$SERVE_DIR" \
  "CUDA_DEVICE_ORDER=PCI_BUS_ID HF_HUB_OFFLINE=1 TRANSFORMERS_VERBOSITY=error $qpy $qdir/server.py$args 2>&1 | tee -a $qdir/logs/server.log"
echo "started tmux session $SESSION; wait ~20 s, then: $PY $SERVE_DIR/health.py"
