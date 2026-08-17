#!/bin/bash
# run_pinterest_generate.sh — generate pins AND commit them.
#
# The 06:10 cron called pinterest_pipeline.py directly, which only WRITES files. 34 pin
# images had accumulated untracked, so every image_url in the queue pointed at a 404 on
# the live site. Posting itself survived only because post_pinterest.py uploads the local
# file rather than fetching the URL — a lucky accident, not a design.
#
# Same failure family as the IG poster, the trending refresh and the SEO writer: content
# generated, never shipped. On this repo, writing a file is not shipping it.
set -euo pipefail
cd "$HOME/golden-home-project"

set -a
. "$HOME/.ghp-engagement/pexels.env"
[ -f "$HOME/.ghp-secrets/claude.env" ] && . "$HOME/.ghp-secrets/claude.env"
set +a

"$HOME/.ghp-engagement/venv/bin/python" automation/pinterest_pipeline.py --max "${1:-4}"

git add social/pinterest_queue.json social/pinterest/ 2>/dev/null || true
if git diff --staged --quiet; then
  echo "[pin-gen] nothing new to commit"
  exit 0
fi

git -c user.name="GHP Pinterest Bot" -c user.email="goldenhomeprojectllc@gmail.com" \
    commit -q -m "pinterest: queue + pin images $(date -u +%Y-%m-%d)"
for i in 1 2 3 4 5; do
  if git -c rebase.autoStash=true pull --rebase --quiet origin main \
     && git push --quiet origin main; then
    echo "[pin-gen] pushed"
    exit 0
  fi
  sleep 5
done
echo "[pin-gen] PUSH FAILED — images committed locally only"
exit 1
