#!/bin/bash
# install.sh — engagement-targets daily generator
set -euo pipefail

DIR="$HOME/golden-home-project/pi/engagement-targets"
UNITS="$HOME/.config/systemd/user"

mkdir -p "$UNITS"
cp "$DIR/ghp-engagement-targets.service" "$UNITS/"
cp "$DIR/ghp-engagement-targets.timer"   "$UNITS/"

for entry in ghp/meta_access_token ghp/ig_business_account_id; do
  if ! pass show "$entry" >/dev/null 2>&1; then
    echo "MISSING: pass entry '$entry'"
    exit 1
  fi
done

systemctl --user daemon-reload
systemctl --user enable --now ghp-engagement-targets.timer
echo "OK. Tomorrow 06:15 ET the first list lands at:"
echo "  ~/golden-home-project/social/engagement_targets_latest.json"
echo
echo "Run once now: systemctl --user start ghp-engagement-targets.service"
