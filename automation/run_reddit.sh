#!/usr/bin/env bash
# run_reddit.sh — wrapper for reddit_post.py. Manual use ONLY; never add this to cron.
#   --login  opens the browser on the Pi's real desktop (view it via Raspberry Pi Connect)
#   anything else runs headless-ish under xvfb, like the Pinterest poster
set -euo pipefail
cd "$(dirname "$0")/.."
PY="$HOME/.ghp-engagement/venv/bin/python"
PROFILE="$HOME/.config/ghp-reddit-chromium"
pkill -f -- "--user-data-dir=$PROFILE" 2>/dev/null || true
rm -f "$PROFILE"/Singleton{Lock,Cookie,Socket} 2>/dev/null || true
if [[ "${1:-}" == "--login" ]]; then
  export XDG_RUNTIME_DIR="${XDG_RUNTIME_DIR:-/run/user/$(id -u)}"
  export WAYLAND_DISPLAY="${WAYLAND_DISPLAY:-wayland-0}"
  export DISPLAY="${DISPLAY:-:0}"
  exec "$PY" automation/reddit_post.py --login
fi
exec xvfb-run -a "$PY" automation/reddit_post.py "$@"
