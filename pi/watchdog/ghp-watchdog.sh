#!/bin/bash
# ghp-watchdog.sh — every 60s pings the things GHP revenue depends on. After
# 2 consecutive failures, fires an ntfy push. After recovery, fires a recovery
# push. Every check is appended to ~/ghp-watchdog/logs/checks.jsonl.
#
# Designed to run as systemd service ghp-watchdog.service (Type=simple, infinite
# loop, Restart=on-failure). Logs to journald via stdout; durable check trail
# lives in the jsonl file so we can backfill the self-review loop from it.
#
# NTFY_TOPIC is read from the existing ~/claude-skill/config/env (READ-ONLY).
# We do not touch that file.

set -u

ENV_FILE="${ENV_FILE:-$HOME/claude-skill/config/env}"
LOG_DIR="${GHP_WATCHDOG_LOG_DIR:-$HOME/ghp-watchdog/logs}"
STATE_DIR="${GHP_WATCHDOG_STATE_DIR:-$HOME/ghp-watchdog/state}"
INTERVAL="${GHP_WATCHDOG_INTERVAL:-60}"
FAIL_THRESHOLD="${GHP_WATCHDOG_FAIL_THRESHOLD:-2}"

mkdir -p "$LOG_DIR" "$STATE_DIR"
LOG_FILE="$LOG_DIR/checks.jsonl"

if [ ! -r "$ENV_FILE" ]; then
  echo "FATAL: env file $ENV_FILE not readable" >&2
  exit 1
fi
NTFY_TOPIC=$(grep '^NTFY_TOPIC=' "$ENV_FILE" | head -1 | cut -d= -f2- | tr -d '"' | tr -d "'")
if [ -z "${NTFY_TOPIC:-}" ]; then
  echo "FATAL: NTFY_TOPIC empty in $ENV_FILE" >&2
  exit 1
fi

# Target list. Each line: "label|url|expect_regex"
# expect_regex matches the HTTP status code body of the response. Meta Graph
# returns 400 for a bare /v21.0/ ping (missing token); we treat any 2xx OR 4xx
# as "the API is reachable" — only 5xx / curl-fail counts as down.
TARGETS=(
  "goldenhomeproject.com|https://goldenhomeproject.com/|^(2..|3..|4..)$"
  "meta_graph_api|https://graph.facebook.com/v21.0/|^(2..|4..)$"
  "ntfy_server|https://ntfy.sh/|^(2..|3..|4..)$"
)

notify() {
  local title="$1" body="$2" priority="${3:-default}"
  curl -sf -m 10 \
    -H "Title: $title" \
    -H "Priority: $priority" \
    -H "Tags: warning,ghp" \
    -d "$body" \
    "https://ntfy.sh/$NTFY_TOPIC" >/dev/null \
    || echo "ntfy push failed for: $title" >&2
}

check_one() {
  local label="$1" url="$2" regex="$3"
  local code
  code=$(curl -sS -o /dev/null -w '%{http_code}' --max-time 10 "$url" 2>/dev/null || echo "000")
  if [[ "$code" =~ $regex ]]; then
    echo "ok|$code"
  else
    echo "fail|$code"
  fi
}

# State file per target tracks consecutive failure count + last_state (up|down).
# Atomic writes so a kill mid-check doesn't corrupt.
get_state() { cat "$STATE_DIR/$1.state" 2>/dev/null || echo "up|0"; }
set_state() {
  local label="$1" state="$2" fails="$3"
  printf '%s|%s' "$state" "$fails" > "$STATE_DIR/$label.state.tmp"
  mv "$STATE_DIR/$label.state.tmp" "$STATE_DIR/$label.state"
}

echo "[ghp-watchdog] starting — interval ${INTERVAL}s, fail threshold $FAIL_THRESHOLD, ${#TARGETS[@]} targets"

# Self-rotation: once the JSONL passes ~20MB, truncate to the last ~10MB so we
# never need an external logrotate config. The self-review loop reads the tail
# anyway, so older history is not useful. Tradeoff: a hard kill mid-rotate
# could lose ~10MB of trailing log; acceptable.
ROTATE_BYTES="${GHP_WATCHDOG_ROTATE_BYTES:-20000000}"
KEEP_BYTES="${GHP_WATCHDOG_KEEP_BYTES:-10000000}"
rotate_if_needed() {
  local size
  size=$(stat -c%s "$LOG_FILE" 2>/dev/null || echo 0)
  if [ "$size" -gt "$ROTATE_BYTES" ]; then
    tail -c "$KEEP_BYTES" "$LOG_FILE" > "$LOG_FILE.tmp" && mv "$LOG_FILE.tmp" "$LOG_FILE"
    echo "[ghp-watchdog] rotated $LOG_FILE: $size → $(stat -c%s "$LOG_FILE") bytes"
  fi
}
ROTATE_EVERY=720  # check every 720 cycles ~= every 12h at 60s interval
cycle=0

while true; do
  ts=$(date -Iseconds)
  if [ $((cycle % ROTATE_EVERY)) -eq 0 ]; then rotate_if_needed; fi
  cycle=$((cycle + 1))
  for entry in "${TARGETS[@]}"; do
    IFS='|' read -r label url regex <<< "$entry"
    result=$(check_one "$label" "$url" "$regex")
    status="${result%%|*}"
    code="${result##*|}"

    # Append durable log line.
    printf '{"t":"%s","label":"%s","url":"%s","http":"%s","status":"%s"}\n' \
      "$ts" "$label" "$url" "$code" "$status" >> "$LOG_FILE"

    prev=$(get_state "$label")
    prev_state="${prev%%|*}"
    prev_fails="${prev##*|}"
    [[ "$prev_fails" =~ ^[0-9]+$ ]] || prev_fails=0

    if [ "$status" = "fail" ]; then
      new_fails=$((prev_fails + 1))
      if [ "$prev_state" = "up" ] && [ "$new_fails" -ge "$FAIL_THRESHOLD" ]; then
        notify "GHP watchdog: $label down" "After $new_fails consecutive failures. HTTP=$code URL=$url" "high"
        set_state "$label" "down" "$new_fails"
      else
        set_state "$label" "$prev_state" "$new_fails"
      fi
    else
      if [ "$prev_state" = "down" ]; then
        notify "GHP watchdog: $label recovered" "HTTP=$code URL=$url"
      fi
      set_state "$label" "up" "0"
    fi
  done
  sleep "$INTERVAL"
done
