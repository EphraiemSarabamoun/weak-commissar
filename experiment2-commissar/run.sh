#!/usr/bin/env bash
# The commissar experiment's runner: experiments/prompt-search/run.sh (operae's scripts/run-smoke.sh with the
# interpreter pinned to Python 3.12; castra needs 3.12+ and the GPU host's python3 is 3.10) plus the pins of pins.py.
# Usage: run.sh CASTRA_DIR <castra.arena command and arguments>
#
# Before it loads any credential or starts anything it refuses (exit 2) a castra directory whose engine.py or castra/
# package bytes are not the pinned 8457977 export's, a run whose --subject is not the pinned subject, and a Claude
# CLI that is not the pinned version (Codex c2-verify F4). Once PYTHONPATH is set it checks again that the castra
# Python will import is that directory. Then it loads <local>/.zshrc.secrets without printing it, blanks metered API keys,
# puts castra and operae on PYTHONPATH and hands the rest to operae's scripts/arena.py.
set -euo pipefail
py="$HOME/.local/bin/python3.12"
castra="$1"; shift
exp="$(cd "$(dirname "$0")" && pwd)"
here="$(cd "$exp/../.." && pwd)"
"$py" -I "$exp/pins.py" check-run "$castra" "$@" || exit 2
export PYTHONPATH="$castra:$here"
"$py" "$exp/pins.py" check-import "$castra" || exit 2
set -a
# shellcheck disable=SC1090
source "$HOME/.zshrc.secrets" >/dev/null 2>&1
set +a
unset ANTHROPIC_API_KEY OPENAI_API_KEY
exec "$py" "$here/scripts/arena.py" "$@"
