#!/usr/bin/env bash
# Install path-c-dm systemd user units. Idempotent.
set -euo pipefail

REPO_DIR="$HOME/golden-home-project"
SYSD_DIR="$HOME/.config/systemd/user"
RUNS_DIR="$HOME/.ghp-path-c/runs"

mkdir -p "$SYSD_DIR" "$RUNS_DIR"

cp "$REPO_DIR/pi/path-c-dm/ghp-path-c-dm.service" "$SYSD_DIR/"
cp "$REPO_DIR/pi/path-c-dm/ghp-path-c-dm.timer" "$SYSD_DIR/"

systemctl --user daemon-reload
systemctl --user enable --now ghp-path-c-dm.timer

loginctl enable-linger "$USER" 2>/dev/null || true

echo "OK. Status:"
systemctl --user list-timers ghp-path-c-dm.timer --no-pager
