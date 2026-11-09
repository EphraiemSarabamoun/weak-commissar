#!/usr/bin/env bash
# Stop the commissar server: Ctrl-C into its own tmux session (a clean shutdown),
# then end that session. Touches nothing but the session named commissar-serve.
set -euo pipefail
SESSION=commissar-serve
TMUX_BIN=/usr/local/bin/tmux
[ -x "$TMUX_BIN" ] || TMUX_BIN=/usr/bin/tmux
"$TMUX_BIN" has-session -t "=$SESSION" 2>/dev/null || { echo "no $SESSION session"; exit 0; }
"$TMUX_BIN" send-keys -t "=$SESSION:" C-c
sleep 3
"$TMUX_BIN" has-session -t "=$SESSION" 2>/dev/null && "$TMUX_BIN" kill-session -t "=$SESSION"
echo "stopped $SESSION"
