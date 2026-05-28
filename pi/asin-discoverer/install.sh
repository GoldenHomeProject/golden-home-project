#!/bin/bash
# install.sh — idempotent installer for the Pi-resident ASIN discoverer.
# Run ONCE on the Pi:
#   bash ~/golden-home-project/pi/asin-discoverer/install.sh
#
# What this does:
#   1. Creates ~/.ghp-asin-discoverer/{venv,runs}
#   2. pip-installs playwright in the venv and downloads chromium
#   3. Copies the systemd .service + .timer to ~/.config/systemd/user/
#   4. Enables + starts the timer (oneshot will fire at next scheduled tick)
#
# Pre-reqs already present on this Pi from the engagement install:
#   - xvfb (apt)
#   - python3 + venv (apt)
#   - Linger enabled for ianmcwherter (loginctl)
#   - golden-home-project repo cloned to ~/golden-home-project

set -euo pipefail

REPO_DIR="${REPO_DIR:-$HOME/golden-home-project}"
APP_DIR="$HOME/.ghp-asin-discoverer"
VENV="$APP_DIR/venv"
RUNS="$APP_DIR/runs"
UNIT_DIR="$HOME/.config/systemd/user"
SRC="$REPO_DIR/pi/asin-discoverer"

echo "[install] dirs"
mkdir -p "$APP_DIR" "$RUNS" "$UNIT_DIR"

if [ ! -x "$VENV/bin/python" ]; then
  echo "[install] creating venv at $VENV"
  python3 -m venv "$VENV"
fi

echo "[install] pip install playwright"
"$VENV/bin/pip" install --upgrade pip >/dev/null
"$VENV/bin/pip" install --upgrade playwright >/dev/null

echo "[install] playwright install chromium (this may take a while first time)"
"$VENV/bin/playwright" install chromium

echo "[install] copying unit files"
cp "$SRC/ghp-asin-discoverer.service" "$UNIT_DIR/"
cp "$SRC/ghp-asin-discoverer.timer"   "$UNIT_DIR/"

echo "[install] systemd reload + enable + start timer"
systemctl --user daemon-reload
systemctl --user enable --now ghp-asin-discoverer.timer

echo
echo "[install] DONE"
echo
echo "Next scheduled run:"
systemctl --user list-timers ghp-asin-discoverer.timer --no-pager || true
echo
echo "To trigger one immediately:  systemctl --user start ghp-asin-discoverer.service"
echo "To tail the run log:         tail -50 $RUNS/last.log"
