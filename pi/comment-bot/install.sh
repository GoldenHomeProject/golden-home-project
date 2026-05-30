#!/usr/bin/env bash
# Install comment-bot systemd user units on the Pi. Idempotent.
set -euo pipefail

REPO_DIR="$HOME/golden-home-project"
SYSD_DIR="$HOME/.config/systemd/user"
RUNS_DIR="$HOME/.ghp-comment-bot/runs"

mkdir -p "$SYSD_DIR" "$RUNS_DIR"

cp "$REPO_DIR/pi/comment-bot/ghp-comment-bot.service" "$SYSD_DIR/"
cp "$REPO_DIR/pi/comment-bot/ghp-comment-bot.timer" "$SYSD_DIR/"

systemctl --user daemon-reload
systemctl --user enable --now ghp-comment-bot.timer

# Allow linger so the timer fires even when no SSH session is open
loginctl enable-linger "$USER" 2>/dev/null || true

echo "OK. Status:"
systemctl --user list-timers ghp-comment-bot.timer --no-pager
