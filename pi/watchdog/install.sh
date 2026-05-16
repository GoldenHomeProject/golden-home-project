#!/bin/bash
# install.sh — copies watchdog into ~/ghp-watchdog/ and enables the user-mode
# systemd unit. Idempotent: safe to re-run after edits.
#
# Usage (on the Pi):
#   bash pi/watchdog/install.sh
#
# This installs as a USER service (systemctl --user) so it does not need sudo.
# Requires `loginctl enable-linger ianmcwherter` to keep running across logout.

set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
TARGET_DIR="$HOME/ghp-watchdog"
UNIT_DIR="$HOME/.config/systemd/user"

mkdir -p "$TARGET_DIR" "$UNIT_DIR"
install -m 755 "$HERE/ghp-watchdog.sh" "$TARGET_DIR/ghp-watchdog.sh"
install -m 644 "$HERE/ghp-watchdog.service" "$UNIT_DIR/ghp-watchdog.service"

# Linger lets user services run when no shell is logged in.
if ! loginctl show-user "$USER" | grep -q '^Linger=yes'; then
  echo "Enabling linger for $USER (requires sudo)..."
  sudo loginctl enable-linger "$USER"
fi

systemctl --user daemon-reload
systemctl --user enable --now ghp-watchdog.service

echo "Installed. Status:"
systemctl --user --no-pager status ghp-watchdog.service | head -15
