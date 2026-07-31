#!/bin/bash
# refresh_sitemap.sh — rebuild sitemap.xml and push it if it changed.
#
# Runs after the day's content lands (trending 07:10, SEO writer 07:15). Kept as a
# script rather than an inline cron entry because cron treats % as a newline and the
# commit message needs a date — inline quoting broke twice.
set -euo pipefail
cd "$HOME/golden-home-project"

/usr/bin/python3 automation/generate_sitemap.py

git add sitemap.xml
if git diff --staged --quiet; then
  echo "[sitemap] unchanged"
  exit 0
fi

git -c user.name="GHP Ops" -c user.email="goldenhomeprojectllc@gmail.com" \
    commit -q -m "sitemap: refresh $(date -u +%Y-%m-%d)"
for i in 1 2 3 4 5; do
  if git -c rebase.autoStash=true pull --rebase --quiet origin main \
     && git push --quiet origin main; then
    echo "[sitemap] pushed"
    exit 0
  fi
  sleep 5
done
echo "[sitemap] PUSH FAILED — committed locally only"
exit 1
