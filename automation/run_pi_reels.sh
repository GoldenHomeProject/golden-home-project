#!/usr/bin/env bash
# Pi-side reel renderer — the fallback for GitHub Actions.
#
# Replaces the presenter/LTX-2 job that failed 61 consecutive nights. That job
# depended on a free HuggingFace Space (multimodalart/ltx2-audio-to-video) which
# now raises an internal error for us on every call, with verbose reporting
# disabled so it reports nothing useful. It is not quota and not the request:
# an 8-second render with trimmed audio fails identically to a 12-second one, and
# the Space's own /get_audio_duration endpoint answers fine. We do not control it
# and cannot fix it, so nothing that has to run nightly should depend on it.
#
# This renders the same scripts the GitHub pipeline uses, with the same code, on
# hardware we own. If Actions is down, rate-limited, or the runner image changes
# under us, reels still get made and the poster still has something to publish.
#
# Everything it needs is local: Pexels for real photos, edge-tts for voice,
# ffmpeg for assembly. No GPU, no third-party render service.
set -uo pipefail

REPO="$HOME/golden-home-project"
LOG="$REPO/social/pi_reels_cron.log"

cd "$REPO" || { echo "[pi-reels] repo missing"; exit 1; }

# Real photos need the key; without it reel_producer falls back to branded cards.
# shellcheck disable=SC1091
[ -f "$HOME/.ghp-engagement/pexels.env" ] && . "$HOME/.ghp-engagement/pexels.env"
export PEXELS_API_KEY="${PEXELS_API_KEY:-}"

echo "===== $(date -u +%Y-%m-%dT%H:%M:%SZ) pi reel render ====="

git -c rebase.autoStash=true pull --rebase --quiet origin main || {
    echo "[pi-reels] pull failed — rendering against local state anyway"
}

/usr/bin/python3 automation/reel_producer.py
rc=$?
if [ $rc -ne 0 ]; then
    echo "[pi-reels] reel_producer exited $rc"
fi

# NEVER commit a broken merge. On 2026-09-02 the autostash apply above conflicted,
# left "<<<<<<< Updated upstream" markers inside social/post_queue.json, and this
# script committed and pushed them. The Content Engine then died with a
# JSONDecodeError and Instagram/YouTube generated nothing until it was found by hand.
if grep -rqE "^(<<<<<<< |>>>>>>> )" social/ 2>/dev/null; then
    echo "[pi-reels] ABORT: git conflict markers present in social/ — refusing to commit"
    grep -rlE "^(<<<<<<< |>>>>>>> )" social/ 2>/dev/null | sed "s/^/    /"
    exit 1
fi
# And never commit JSON we cannot parse — the queue is what the posters read.
if ! /usr/bin/python3 -c "import json,sys; json.load(open('social/post_queue.json'))" 2>/dev/null; then
    echo "[pi-reels] ABORT: social/post_queue.json is not valid JSON — refusing to commit"
    exit 1
fi

git add social/reels/ social/post_queue.json AGENT_LOG.md 2>/dev/null
if git diff --staged --quiet; then
    echo "[pi-reels] nothing new to commit"
    exit 0
fi

git -c user.name="GHP Pi Renderer" -c user.email="goldenhomeprojectllc@gmail.com" \
    commit -q -m "pi reel render $(date -u +%Y-%m-%d)"

# Same retry discipline as the workflows: a render that is committed but not
# pushed is a render that never happened.
for i in 1 2 3 4 5; do
    git rebase --abort 2>/dev/null
    if git -c rebase.autoStash=true pull --rebase --quiet origin main \
       && git push --quiet origin main; then
        echo "[pi-reels] pushed"
        exit 0
    fi
    sleep 5
done
echo "[pi-reels] PUSH FAILED after 5 tries — reels are committed locally only"
exit 1
