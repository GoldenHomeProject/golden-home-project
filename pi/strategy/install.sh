#!/bin/bash
# Install GHP daily strategy timer on the Pi (user units).
set -eu

REPO_DIR="${GHP_REPO_DIR:-$HOME/golden-home-project}"
UNIT_DIR="$HOME/.config/systemd/user"
mkdir -p "$UNIT_DIR" "$HOME/.ghp-strategy/runs"

cp "$REPO_DIR/pi/strategy/ghp-daily-strategy.service" "$UNIT_DIR/"
cp "$REPO_DIR/pi/strategy/ghp-daily-strategy.timer"   "$UNIT_DIR/"
chmod +x "$REPO_DIR/pi/strategy/daily-strategy.sh"

systemctl --user daemon-reload
systemctl --user enable --now ghp-daily-strategy.timer

echo "installed. next fires:"
systemctl --user list-timers ghp-daily-strategy.timer --no-pager
