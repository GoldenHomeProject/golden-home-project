#!/usr/bin/env bash
# Install the pin-repoint systemd user units on the Pi. Idempotent.
# Before enabling: run the script once with --dry, then --no-dry --max 1 --verify-ui.
set -euo pipefail

REPO_DIR="$HOME/golden-home-project"
SYSD_DIR="$HOME/.config/systemd/user"

mkdir -p "$SYSD_DIR" "$HOME/.ghp-engagement/runs"
cp "$REPO_DIR/pi/pin-repoint/ghp-pin-repoint.service" "$SYSD_DIR/"
cp "$REPO_DIR/pi/pin-repoint/ghp-pin-repoint.timer" "$SYSD_DIR/"

systemctl --user daemon-reload
systemctl --user enable --now ghp-pin-repoint.timer
loginctl enable-linger "$USER" 2>/dev/null || true

systemctl --user list-timers ghp-pin-repoint.timer --no-pager
