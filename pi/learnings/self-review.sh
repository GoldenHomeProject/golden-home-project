#!/bin/bash
# self-review.sh — weekly GHP compound-engineering loop.
#
# Mirrors the pattern at ~/claude-skill/learnings/self-review.sh but for GHP:
#   1. Pulls the last 7 days of failures from THREE sources:
#        - GitHub Actions failed runs (via `gh run list` + `gh run view --log`)
#        - The watchdog's checks.jsonl (status=fail lines)
#        - Any *error*.log / *.err.log under the repo
#   2. Feeds them to Claude Opus 4.7 with a tight prompt: identify ≤3 recurring
#      failures, propose ≤20-line patches, point to file:line, explain safety.
#   3. Writes the proposal to pi/learnings/proposals/<date>.md in the repo.
#   4. Commits on branch `learnings/<date>`, opens a PR via `gh pr create`,
#      ntfy-pings the user with the PR URL.
#   5. Appends an entry to pi/learnings/journal.jsonl so future runs can see
#      what's already been tried.
#
# Never auto-applies — the PR is the artifact.

set -u

# Auth: gh token lives encrypted in `pass`, not plaintext on disk. Export as
# GH_TOKEN so gh skips its config file entirely. Git uses credential helper
# git-credential-ghp-pass which reads the same entry.
if command -v pass >/dev/null 2>&1; then
  GH_TOKEN=$(pass show ghp/github_token 2>/dev/null) || true
  export GH_TOKEN
fi

REPO_DIR="${GHP_REPO_DIR:-$HOME/golden-home-project}"
ENV_FILE="${ENV_FILE:-$HOME/claude-skill/config/env}"
DATE=$(date +%Y-%m-%d)
# Suffix branch with epoch when same-day re-run already pushed — prevents
# `branch already exists on remote` collisions during ad-hoc dry-runs.
BRANCH="learnings/$DATE"
PROPOSALS_REL="pi/learnings/proposals"
JOURNAL_REL="pi/learnings/journal.jsonl"
OUT_REL="$PROPOSALS_REL/$DATE.md"

cd "$REPO_DIR" || { echo "FATAL: cannot cd to $REPO_DIR" >&2; exit 1; }
mkdir -p "$PROPOSALS_REL"
touch "$JOURNAL_REL"

# Always work from a fresh main so proposals don't carry stale code.
git fetch --quiet origin main
git checkout --quiet main
git reset --hard --quiet origin/main

# If today's branch already exists on remote (re-run), append epoch suffix.
if git ls-remote --exit-code --heads origin "$BRANCH" >/dev/null 2>&1; then
  BRANCH="learnings/$DATE-$(date +%s)"
  OUT_REL="$PROPOSALS_REL/$DATE-$(date +%H%M%S).md"
fi

# --- Source 1: GitHub Actions failed runs in the last 7 days ----------------
ACTIONS_LOG=""
if command -v gh >/dev/null 2>&1 && gh auth status >/dev/null 2>&1; then
  # Last 25 failed runs, then drill into the first 5 for actual log excerpts.
  FAILED_RUNS=$(gh run list --status failure --limit 25 \
      --json databaseId,name,createdAt,conclusion \
      --jq '[.[] | select(.createdAt > (now - 7*86400 | todate))]' 2>/dev/null || echo "[]")
  ACTIONS_LOG="=== GitHub Actions failures (last 7d) ===\n$FAILED_RUNS\n"

  for run_id in $(echo "$FAILED_RUNS" | jq -r '.[0:5][].databaseId' 2>/dev/null); do
    excerpt=$(gh run view "$run_id" --log-failed 2>/dev/null | tail -n 80 || true)
    ACTIONS_LOG+="\n--- run $run_id (tail) ---\n$excerpt\n"
  done
else
  ACTIONS_LOG="(gh CLI not authenticated — Actions logs skipped)"
fi

# --- Source 2: watchdog failures from checks.jsonl --------------------------
WATCHDOG_FAILS=""
WD_LOG="$HOME/ghp-watchdog/logs/checks.jsonl"
if [ -s "$WD_LOG" ]; then
  cutoff=$(date -d '7 days ago' -Iseconds 2>/dev/null || date -u -v-7d -Iseconds)
  WATCHDOG_FAILS=$(awk -v cutoff="$cutoff" -F'"' '
    {
      for (i=1;i<=NF;i++) if ($i=="status" && $(i+2)=="fail") { print; next }
    }' "$WD_LOG" | tail -n 200)
fi
[ -z "$WATCHDOG_FAILS" ] && WATCHDOG_FAILS="(no watchdog failures in window)"

# --- Source 3: repo-resident error logs -------------------------------------
REPO_ERRS=$(find "$REPO_DIR" -type f \( -name '*error*.log' -o -name '*.err.log' \) \
  -newermt '7 days ago' 2>/dev/null | head -10 | while read -r f; do
    echo "--- $f (tail) ---"
    tail -n 40 "$f"
  done)
[ -z "$REPO_ERRS" ] && REPO_ERRS="(no recent repo error logs)"

# --- Prior journal so we don't re-propose known dead ends -------------------
JOURNAL_RECENT=$(tail -n 50 "$JOURNAL_REL" 2>/dev/null || true)

# --- Prompt Claude ----------------------------------------------------------
PROMPT=$(cat <<EOF
You are the GHP weekly compound-engineering reviewer. Read the last 7 days of
operational failures from three sources below and identify 1-3 RECURRING
failure modes (single one-offs do not count). For each, propose a minimal
patch (≤20 lines diff), point to the exact file:line in the GHP repo, and
explain why it is safe. Do not propose rewrites or new infrastructure.

Hard constraints:
- Subscription + free tools only. No new paid services. No new API tokens.
- Revenue first. Skip cosmetic refactors.
- If you cannot find ≥1 real recurring failure, return "NO PROPOSALS — week was clean."
- Anything in the journal section was already tried — do not re-propose.

Format (markdown):
## Failure N: <name>
**Evidence:** <1-3 log quotes with source>
**Root cause:** <one sentence>
**Patch:** file:line + ≤20 lines of unified diff in a \`\`\`diff fenced block
**Why safe:** <one sentence>
**Verification:** <one line — how to prove the fix works>

=== GitHub Actions failures (last 7d) ===
$(printf '%b' "$ACTIONS_LOG")

=== Watchdog checks.jsonl failures (last 7d) ===
$WATCHDOG_FAILS

=== Repo error logs ===
$REPO_ERRS

=== Past proposals journal (newest last) ===
$JOURNAL_RECENT
EOF
)

REPORT=$(echo "$PROMPT" | /usr/bin/claude -p --model claude-opus-4-7 2>&1 \
  || echo "claude CLI failed: $?")

cat > "$OUT_REL" <<EOF
# GHP self-review — $DATE

Generated by \`pi/learnings/self-review.sh\` on $(hostname).

$REPORT
EOF

# --- Branch, commit, PR -----------------------------------------------------
git checkout -B "$BRANCH"
git add "$OUT_REL" "$JOURNAL_REL"
PROP_LINES=$(wc -l < "$OUT_REL" | tr -d ' ')

git -c user.name="GHP Self-Review Bot" \
    -c user.email="goldenhomeprojectllc@gmail.com" \
    commit -m "self-review: $DATE ($PROP_LINES-line proposal)" >/dev/null

# Push branch + open PR.
PR_URL=""
if git push --quiet -u origin "$BRANCH" 2>&1; then
  if command -v gh >/dev/null 2>&1 && gh auth status >/dev/null 2>&1; then
    PR_URL=$(gh pr create --title "self-review: $DATE" \
      --body "Auto-generated by \`pi/learnings/self-review.sh\` on the Pi. Review before merging. Proposal: $OUT_REL" \
      --head "$BRANCH" --base main 2>&1 | tail -1 || true)
  fi
fi

# --- Journal entry (atomic, on main) ----------------------------------------
git checkout --quiet main
printf '{"t":"%s","event":"ghp_self_review","branch":"%s","proposal":"%s","pr":"%s","actions_failures":"%s"}\n' \
  "$(date -Iseconds)" "$BRANCH" "$OUT_REL" "$PR_URL" \
  "$(echo "$ACTIONS_LOG" | grep -c databaseId || echo 0)" \
  >> "$JOURNAL_REL"
git add "$JOURNAL_REL"
git -c user.name="GHP Self-Review Bot" \
    -c user.email="goldenhomeprojectllc@gmail.com" \
    commit -m "self-review: journal $DATE" --quiet || true
git push --quiet origin main || true

# --- ntfy ping --------------------------------------------------------------
if [ -r "$ENV_FILE" ]; then
  TOPIC=$(grep '^NTFY_TOPIC=' "$ENV_FILE" | cut -d= -f2- | tr -d "'\"")
  if [ -n "${TOPIC:-}" ]; then
    BODY="Proposal at $OUT_REL"
    [ -n "$PR_URL" ] && BODY="PR: $PR_URL"
    curl -sf -m 10 \
      -H "Title: GHP weekly self-review ready" \
      -H "Tags: brain,ghp" \
      -d "$BODY" \
      "https://ntfy.sh/$TOPIC" >/dev/null || true
  fi
fi

echo "wrote $OUT_REL"
[ -n "$PR_URL" ] && echo "pr: $PR_URL"
