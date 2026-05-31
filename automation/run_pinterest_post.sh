#!/usr/bin/env bash
# Cron wrapper for the Pinterest poster. Kills any stale Chromium still holding
# the ghp-chromium profile, clears Singleton locks, then runs the poster under
# xvfb (headless display) with the daily cap passed as $1 (default 2).
set -u
REPO="$HOME/golden-home-project"
PY="$HOME/.ghp-engagement/venv/bin/python"
PROFILE="$HOME/.config/ghp-chromium"
MAX="${1:-2}"

for p in $(pgrep -f "config/ghp-chromium"); do
  c=$(cat "/proc/$p/comm" 2>/dev/null)
  case "$c" in chrome*|chromium*) kill "$p" ;; esac
done
sleep 2
rm -f "$PROFILE"/Singleton* 2>/dev/null

cd "$REPO" || exit 1
exec xvfb-run -a "$PY" automation/post_pinterest.py --max "$MAX" --no-dry
