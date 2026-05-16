#!/bin/bash
# install.sh — wires up the weekly GHP self-review timer as a USER systemd unit.
# Idempotent.
#
# Prereqs (one-time, manual):
#   1. apt install gh    # GitHub CLI for `gh run view` + `gh pr create`
#   2. gh auth login     # device-flow against github.com — needs repo + workflow scopes
#   3. git clone https://github.com/GoldenHomeProject/golden-home-project ~/golden-home-project
#   4. cd ~/golden-home-project && git config user.email goldenhomeprojectllc@gmail.com
#
# Then: bash pi/learnings/install.sh

set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
UNIT_DIR="$HOME/.config/systemd/user"
mkdir -p "$UNIT_DIR"

install -m 644 "$HERE/ghp-self-review.service" "$UNIT_DIR/ghp-self-review.service"
install -m 644 "$HERE/ghp-self-review.timer"   "$UNIT_DIR/ghp-self-review.timer"

systemctl --user daemon-reload
systemctl --user enable --now ghp-self-review.timer

echo "Installed. Timers:"
systemctl --user --no-pager list-timers ghp-self-review.timer
