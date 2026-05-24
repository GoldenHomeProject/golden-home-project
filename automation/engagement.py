#!/usr/bin/env python3
"""
GHP Engagement Bot — Pi-resident, Playwright + persistent Chromium profile.

Sister to automation/agents/daily_engagement_chrome.md (the human playbook).
This is the executable form for cron.

Modes:
  --inbox-only   Step 0 only: scan Requests folder + Activity panel, log inbound.
                 No outbound actions. Safe smoke-test mode. DEFAULT.
  --full         Step 0 + outbound (likes/follows/comments) per daily budget.
                 Only enable after --inbox-only has been clean for 5 days.
  --dry-run      Take screenshots, log what WOULD happen, change nothing on IG.

Profile dir:    ~/.config/ghp-chromium (must already be logged into IG)
Log file:       <repo>/social/engagement_log.json
Action budget:  10 follow / 30 like / 5 comment / unlimited DM-reply per day
Abort signals:  any "action blocked" text, 429 response, login wall

Run on Pi via:
  xvfb-run -a ~/.ghp-engagement/venv/bin/python automation/engagement.py --inbox-only
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import random
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
LOG_PATH = REPO_ROOT / "social" / "engagement_log.json"
PROFILE_DIR = Path.home() / ".config" / "ghp-chromium"
CHROMIUM_BIN = "/usr/bin/chromium"

DAILY_CAPS = {"follow": 10, "like": 30, "comment": 5}

# ---------- log helpers ----------

def load_log() -> dict:
    return json.loads(LOG_PATH.read_text())

def save_log(data: dict) -> None:
    LOG_PATH.write_text(json.dumps(data, indent=2))

def today_counts(data: dict, today: str) -> dict:
    counts = {"follow": 0, "like": 0, "comment": 0}
    for a in data.get("actions", []):
        ts = a.get("timestamp") or a.get("date") or ""
        if ts.startswith(today):
            act = a.get("action")
            if act in counts:
                counts[act] += 1
    return counts

def log_action(data: dict, session: str, action: str, target: str, **extra) -> None:
    entry = {
        "timestamp": dt.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
        "action": action,
        "target": target,
        "session": session,
    }
    entry.update(extra)
    data["actions"].append(entry)
    s = data.setdefault("summary", {})
    if action == "follow":
        s["lifetime_follows"] = s.get("lifetime_follows", 0) + 1
    elif action == "like":
        s["lifetime_likes"] = s.get("lifetime_likes", 0) + 1
    elif action == "comment":
        s["lifetime_comments"] = s.get("lifetime_comments", 0) + 1
    elif action.startswith("dm_"):
        s["lifetime_dms"] = s.get("lifetime_dms", 0) + 1
    s["last_session"] = session
    s["last_updated"] = entry["timestamp"]
    s["total_actions"] = s.get("total_actions", 0) + 1
    save_log(data)

def jitter(min_s: float, max_s: float) -> None:
    time.sleep(random.uniform(min_s, max_s))

# ---------- core ----------

def detect_login_wall(page) -> bool:
    """Return True if IG is showing a login form instead of our content."""
    url = page.url
    if "/accounts/login" in url or "/accounts/onetap" in url:
        return True
    # logged-out homepage shows a "Log in" button prominently
    try:
        if page.locator("input[name='username']").count() > 0:
            return True
    except Exception:
        pass
    return False

def detect_action_block(page) -> bool:
    """Return True if IG is showing an action-block dialog."""
    body = ""
    try:
        body = page.locator("body").inner_text(timeout=2000)
    except Exception:
        return False
    needles = ("action blocked", "try again later", "we restrict certain activity")
    bl = body.lower()
    return any(n in bl for n in needles)

def step0_inbox_sweep(page, data: dict, session: str, dry: bool) -> dict:
    """
    Step 0 from daily_engagement_chrome.md:
      - Open Requests folder, list pending request senders
      - Open Activity panel, list new comment/reply targets on OUR posts
    NO outbound actions. NO accepts. Just observe + log so a human (or future
    --full run) can act.
    """
    found = {"requests": [], "activity": []}

    # --- Requests folder ---
    page.goto("https://www.instagram.com/direct/requests/", wait_until="domcontentloaded")
    jitter(3, 5)
    if detect_login_wall(page):
        return {"error": "login_wall_at_requests"}
    try:
        # Request rows are <a href="/direct/t/..."> within the inbox list.
        # Capture sender handles from aria-labels / text. Tolerant scrape.
        anchors = page.locator("a[href*='/direct/t/']").all()
        for a in anchors[:25]:
            txt = (a.inner_text(timeout=1500) or "").strip().split("\n")[0]
            if txt and len(txt) < 50:
                found["requests"].append(txt)
    except Exception as e:
        found["requests_error"] = str(e)

    # --- Activity / Notifications ---
    page.goto("https://www.instagram.com/", wait_until="domcontentloaded")
    jitter(2, 4)
    # Click the heart-shaped notifications button if present
    try:
        page.locator("svg[aria-label='Notifications']").first.click(timeout=3000)
        jitter(2, 4)
        # Each activity row usually contains an <a> with /<handle>/ format
        rows = page.locator("div[role='dialog'] a[href^='/']").all()
        seen = set()
        for r in rows[:30]:
            href = r.get_attribute("href") or ""
            handle = href.strip("/").split("/")[0]
            if handle and handle not in seen and "/" not in handle:
                seen.add(handle)
                found["activity"].append(handle)
    except Exception as e:
        found["activity_error"] = str(e)

    log_action(
        data, session, "inbox_sweep", target="self",
        requests_count=len(found["requests"]),
        activity_count=len(found["activity"]),
        requests=found["requests"][:10],
        activity=found["activity"][:10],
        dry_run=dry,
    )
    return found

# ---------- main ----------

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--inbox-only", action="store_true", default=True)
    parser.add_argument("--full", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--headed", action="store_true",
                        help="Visible window (default headless via xvfb)")
    args = parser.parse_args()

    if args.full:
        args.inbox_only = False

    if not PROFILE_DIR.exists():
        print(f"FATAL: profile dir {PROFILE_DIR} missing. Log in via Pi Connect first.",
              file=sys.stderr)
        return 2

    session = dt.datetime.utcnow().strftime("%Y-%m-%d-%H%M") + "-pi"
    today = dt.date.today().strftime("%Y-%m-%d")

    from playwright.sync_api import sync_playwright

    data = load_log()
    caps_today = today_counts(data, today)
    print(f"[engagement] session={session} caps_today={caps_today}")

    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(
            user_data_dir=str(PROFILE_DIR),
            executable_path=CHROMIUM_BIN,
            headless=False,  # IG fingerprints headless; use xvfb in cron
            viewport={"width": 1280, "height": 900},
            args=["--no-first-run", "--no-default-browser-check"],
        )
        page = ctx.new_page()

        try:
            page.goto("https://www.instagram.com/", wait_until="domcontentloaded")
            jitter(3, 5)

            if detect_login_wall(page):
                print("ABORT: IG shows login wall. Re-auth via Pi Connect.", file=sys.stderr)
                log_action(data, session, "abort", "self", reason="login_wall")
                return 3

            if detect_action_block(page):
                print("ABORT: IG action-block in effect. Halting 24h.", file=sys.stderr)
                log_action(data, session, "abort", "self", reason="action_block")
                data.setdefault("summary", {})["blocked_at"] = dt.datetime.utcnow().isoformat()
                save_log(data)
                return 4

            found = step0_inbox_sweep(page, data, session, args.dry_run)
            print(f"[engagement] requests={len(found.get('requests', []))} "
                  f"activity={len(found.get('activity', []))}")
            for h in found.get("requests", [])[:10]:
                print(f"  REQUEST: {h}")
            for h in found.get("activity", [])[:10]:
                print(f"  ACTIVITY: {h}")

            if args.inbox_only:
                print("[engagement] inbox-only mode — done.")
                return 0

            # Outbound (--full) is intentionally NOT implemented yet.
            # Smoke-test Step 0 for 5 clean days first per the Pi plan,
            # then add discover→engage in a follow-up commit.
            print("FATAL: --full mode not yet implemented. Re-run with --inbox-only.",
                  file=sys.stderr)
            return 5

        finally:
            ctx.close()

if __name__ == "__main__":
    sys.exit(main())
