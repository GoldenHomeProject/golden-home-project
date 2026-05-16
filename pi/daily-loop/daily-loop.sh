#!/bin/bash
# daily-loop.sh — Pi port of ~/.ghp-loop/daily.sh from the Mac.
#
# DELIBERATELY DISABLED at install time. See pi/daily-loop/README.md for the
# cutover procedure. Running this on the Pi WHILE the Mac launchd job is also
# enabled will cause two parallel commit/push attempts at 06:30 local — race +
# duplicate work. Disable the Mac launchd FIRST.

set -u
export PATH="/usr/local/bin:/usr/bin:/bin:$PATH"

PROJECT_DIR="${GHP_REPO_DIR:-$HOME/golden-home-project}"
LOG_DIR="$HOME/.ghp-loop/logs"
TODAY="$(date +%Y-%m-%d)"
LOG_FILE="${LOG_DIR}/${TODAY}.log"

mkdir -p "$LOG_DIR"

PROMPT='Read CLAUDE_GHP_CEO.md. Run the start-of-session self-eval in writing (micro + macro + tunnel-vision detector). Pick ONE highest-leverage item from social/improvement_queue.md and ship it: edit the files, validate the change, commit, push. If the change requires reaching out to humans (email, blog comments, Reddit replies, DMs) — do it; do not draft and wait. Update social/learnings_log.jsonl with any new prediction or evaluation due today. Mark the queue item [done YYYY-MM-DD commit-sha]. End with a one-paragraph summary: what shipped, what evidence proves it, what the next checkpoint is. If improvement_queue.md is empty AND no learnings_log.jsonl evaluations are due, log "queue exhausted, ending" to social/seo_posts_log.json daily_snapshots and stop. Do not invent busywork. Do not rebuild infrastructure. Do not post new blog content unless explicitly listed in the queue.'

cd "$PROJECT_DIR" || { echo "[$(date)] FATAL: cannot cd to $PROJECT_DIR" >> "$LOG_FILE"; exit 1; }

# Sync first so we don't fight Actions commits.
git fetch --quiet origin main && git checkout --quiet main && git reset --hard --quiet origin/main

echo "===== GHP daily loop start: $(date) (pi) =====" >> "$LOG_FILE"
/usr/bin/claude -p "$PROMPT" --dangerously-skip-permissions --model claude-opus-4-7 >> "$LOG_FILE" 2>&1
echo "===== GHP daily loop end: $(date) (pi) =====" >> "$LOG_FILE"
echo "" >> "$LOG_FILE"
