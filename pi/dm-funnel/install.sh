#!/bin/bash
# install.sh — wire dm-funnel into systemd --user
set -euo pipefail

DIR="$HOME/golden-home-project/pi/dm-funnel"
UNITS="$HOME/.config/systemd/user"

mkdir -p "$UNITS"
cp "$DIR/ghp-dm-funnel.service" "$UNITS/"
cp "$DIR/ghp-dm-funnel.timer"   "$UNITS/"

# Sanity-check pass entries exist before enabling
for entry in ghp/meta_access_token ghp/ig_business_account_id; do
  if ! pass show "$entry" >/dev/null 2>&1; then
    echo "MISSING: pass entry '$entry'"
    echo "Insert it with: echo '<value>' | pass insert -e $entry"
    echo "Then re-run this install."
    exit 1
  fi
done

systemctl --user daemon-reload
systemctl --user enable --now ghp-dm-funnel.timer
echo "OK. Check status: systemctl --user status ghp-dm-funnel.timer"
echo "Run once now:      systemctl --user start ghp-dm-funnel.service"
echo "Tail journal:      journalctl --user -u ghp-dm-funnel.service -f"
