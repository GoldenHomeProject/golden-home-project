#!/bin/bash
# install.sh — idempotent installer for the Pi-resident daily trending roundup.
# Run ONCE on the Pi:
#   bash ~/golden-home-project/pi/trending/install.sh
#
# What it does:
#   1. Creates ~/.ghp-trending/{venv,runs}
#   2. pip-installs playwright in the venv + downloads chromium
#   3. Copies the systemd .service + .timer to ~/.config/systemd/user/
#   4. Enables + starts the timer (fires next at 11:10 UTC)
#
# Pre-reqs already present from the asin-discoverer/engagement installs:
#   - xvfb (apt), python3 + venv (apt), linger enabled for ianmcwherter
#   - golden-home-project repo cloned to ~/golden-home-project with push creds

set -euo pipefail

REPO_DIR="${REPO_DIR:-$HOME/golden-home-project}"
APP_DIR="$HOME/.ghp-trending"
VENV="$APP_DIR/venv"
RUNS="$APP_DIR/runs"
UNIT_DIR="$HOME/.config/systemd/user"
SRC="$REPO_DIR/pi/trending"

echo "[install] dirs"
mkdir -p "$APP_DIR" "$RUNS" "$UNIT_DIR"

if [ ! -x "$VENV/bin/python" ]; then
  echo "[install] creating venv at $VENV"
  python3 -m venv "$VENV"
fi

echo "[install] pip install playwright"
"$VENV/bin/pip" install --upgrade pip >/dev/null
"$VENV/bin/pip" install --upgrade playwright >/dev/null

echo "[install] playwright install chromium (slow first time)"
"$VENV/bin/playwright" install chromium

echo "[install] copying unit files"
cp "$SRC/ghp-trending.service" "$UNIT_DIR/"
cp "$SRC/ghp-trending.timer"   "$UNIT_DIR/"

echo "[install] systemd reload + enable + start timer"
systemctl --user daemon-reload
systemctl --user enable --now ghp-trending.timer

echo
echo "[install] DONE"
echo "Next run:  systemctl --user list-timers ghp-trending.timer --no-pager"
echo "Run now :  systemctl --user start ghp-trending.service"
echo "Logs    :  tail -60 $RUNS/last.log"
