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
import re
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
LOG_PATH = REPO_ROOT / "social" / "engagement_log.json"
PROFILE_DIR = Path.home() / ".config" / "ghp-chromium"
CHROMIUM_BIN = "/usr/bin/chromium"

DAILY_CAPS = {"follow": 10, "like": 30, "comment": 5}
# Per-sweep ceilings — must be < daily caps since we run 2x/day
PER_SWEEP_CAPS = {"follow": 3, "like": 6, "comment": 1}

# Skip patterns (paid-promo bots etc. — see feedback_ig_promo_bot_pattern.md)
SKIP_SUFFIXES = ("._community",)
SKIP_KEYWORDS = ("giveaway", "promo", "alltypes")

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

HANDLE_RE = re.compile(r"^[a-z0-9._]{2,30}$")
AGE_RE = re.compile(r"^\d{1,3}(s|m|h|d|w|mo|y)$|^[A-Z][a-z]{2} \d{1,2}$|^\d{1,2} [A-Z][a-z]{2}$")
OWN_HANDLE = "golden_home_project"
UI_WORDS = {
    "messages", "primary", "general", "requests", "notifications",
    "this month", "today", "yesterday", "earlier", "this week",
    "following", "see all", "view all", "more", "search", "explore",
    "reels", "home", "profile", "inbox", "activity", "settings",
}

def _is_real_handle(s: str) -> bool:
    if not HANDLE_RE.match(s):
        return False
    sl = s.lower()
    if sl == OWN_HANDLE or sl in UI_WORDS:
        return False
    if AGE_RE.match(s):
        return False
    # require at least one letter and not look like a duration
    if not re.search(r"[a-z]", s):
        return False
    return True

def _parse_notifications_text(text: str) -> list[dict]:
    """
    Parse the notifications page innerText. IG renders rows like:
        <handle>
        <action>. <ago>
    Returns list of {handle, action, ago} dicts in display order (newest first).
    """
    lines = [ln.strip() for ln in text.split("\n") if ln.strip()]
    out = []
    i = 0
    while i < len(lines) - 1:
        h = lines[i]
        nxt = lines[i + 1]
        if _is_real_handle(h) and any(
            kw in nxt.lower() for kw in
            ("liked your", "started following", "commented", "mentioned",
             "replied", "tagged", "shared", "posted a thread")
        ):
            out.append({"handle": h, "action": nxt})
            i += 2
        else:
            i += 1
    return out

def _parse_inbox_text(text: str) -> list[str]:
    """
    Thread list innerText looks like:
        Messages
        <handle1>
        <preview snippet>  ·  <ago>
        <handle2>
        ...
    Return unique handle list in display order.
    """
    lines = [ln.strip() for ln in text.split("\n") if ln.strip()]
    seen, out = set(), []
    for ln in lines:
        if _is_real_handle(ln) and ln not in seen:
            seen.add(ln)
            out.append(ln)
    return out

def _known_handles(data: dict) -> set[str]:
    """All handles we've ever logged a follow/like/comment/dm against."""
    s = set()
    for a in data.get("actions", []):
        t = (a.get("target") or "").lstrip("@").lower()
        if t:
            s.add(t)
    return s

def _should_skip_handle(handle: str) -> str | None:
    """Return reason string if handle should be skipped, else None."""
    h = handle.lower()
    if any(h.endswith(s) for s in SKIP_SUFFIXES):
        return "skip_suffix"
    if any(k in h for k in SKIP_KEYWORDS):
        return "skip_keyword"
    return None

def follow_back(page, handle: str, data: dict, session: str, dry: bool) -> str:
    """
    Navigate to /<handle>/ and click Follow if button visible and we're not
    already following. Returns: 'followed' | 'already_following' | 'skipped' |
    'blocked' | 'not_found' | 'error:<msg>'.
    Logs the outcome to engagement_log.json.
    """
    reason = _should_skip_handle(handle)
    if reason:
        log_action(data, session, "follow_skip", target=handle, reason=reason)
        return "skipped"

    url = f"https://www.instagram.com/{handle}/"
    try:
        page.goto(url, wait_until="domcontentloaded", timeout=20000)
    except Exception as e:
        log_action(data, session, "follow_error", target=handle, reason=f"goto: {e}")
        return f"error:goto"
    page.wait_for_timeout(random.randint(3500, 6000))

    if detect_action_block(page):
        log_action(data, session, "abort", target=handle, reason="action_block_on_profile")
        return "blocked"

    # Profile not found pages return /accounts/login or /404
    if "/accounts/login" in page.url or "Page Not Found" in (page.title() or ""):
        log_action(data, session, "follow_skip", target=handle, reason="not_found")
        return "not_found"

    # Check current state via the action button on the profile header
    try:
        following_btn = page.get_by_role("button", name="Following", exact=True)
        requested_btn = page.get_by_role("button", name="Requested", exact=True)
        if following_btn.count() > 0 or requested_btn.count() > 0:
            log_action(data, session, "follow_skip", target=handle, reason="already_following")
            return "already_following"

        follow_btn = page.get_by_role("button", name="Follow", exact=True).first
        if follow_btn.count() == 0:
            log_action(data, session, "follow_skip", target=handle, reason="no_follow_button")
            return "error:no_button"

        if dry:
            log_action(data, session, "follow_dry", target=handle, reason="dry_run_only")
            return "followed"  # treat as success for dry-run counting

        follow_btn.click(timeout=5000)
        page.wait_for_timeout(random.randint(2000, 4000))

        # Verify state change
        if detect_action_block(page):
            log_action(data, session, "abort", target=handle, reason="action_block_after_click")
            return "blocked"

        now_following = (
            page.get_by_role("button", name="Following", exact=True).count() > 0
            or page.get_by_role("button", name="Requested", exact=True).count() > 0
        )
        if now_following:
            log_action(data, session, "follow", target=handle, reason="follow_back_untapped_warm")
            return "followed"
        log_action(data, session, "follow_error", target=handle, reason="no_state_change")
        return "error:no_state_change"
    except Exception as e:
        log_action(data, session, "follow_error", target=handle, reason=str(e)[:200])
        return f"error:{type(e).__name__}"

def outbound_follow_round(page, data: dict, session: str, candidates: list[str],
                          dry: bool) -> dict:
    """
    Run follow-back on up to PER_SWEEP_CAPS['follow'] candidates, respecting
    today's remaining daily cap. Returns summary dict.
    """
    today = dt.date.today().strftime("%Y-%m-%d")
    used = today_counts(data, today)
    daily_left = max(0, DAILY_CAPS["follow"] - used["follow"])
    budget = min(PER_SWEEP_CAPS["follow"], daily_left)

    summary = {"attempted": 0, "followed": 0, "skipped": 0,
               "errors": 0, "blocked": False, "results": []}
    if budget <= 0:
        summary["note"] = "no_budget_left_today"
        return summary

    for handle in candidates[:budget * 3]:  # iterate up to 3x budget to find skippables
        if summary["followed"] >= budget:
            break
        summary["attempted"] += 1
        result = follow_back(page, handle, data, session, dry)
        summary["results"].append({"handle": handle, "result": result})
        if result == "followed":
            summary["followed"] += 1
            jitter(60, 120)  # human-pattern pause between follows
        elif result == "blocked":
            summary["blocked"] = True
            break
        elif result.startswith("error"):
            summary["errors"] += 1
            jitter(5, 15)
        else:
            summary["skipped"] += 1
            jitter(5, 15)
    return summary

def step0_inbox_sweep(page, data: dict, session: str, dry: bool) -> dict:
    """
    Step 0: surface inbound engagement we haven't reciprocated yet.
      - Requests folder: pending senders we haven't accepted
      - Inbox: recent threads (already-accepted DMs)
      - Notifications: likes/follows/comments on OUR content
    All passive — no outbound actions, no accepts. Output is the warm-prospect
    list a human (or --full mode) can act on.
    """
    found = {"requests": [], "inbox": [], "notifications": []}

    # --- Requests folder ---
    page.goto("https://www.instagram.com/direct/requests/", wait_until="domcontentloaded")
    page.wait_for_timeout(7000)
    if detect_login_wall(page):
        return {"error": "login_wall_at_requests"}
    try:
        tl = page.locator("[aria-label='Thread list']").first
        txt = tl.inner_text(timeout=4000)
        found["requests"] = _parse_inbox_text(txt)
    except Exception as e:
        found["requests_error"] = str(e)

    # --- Main inbox ---
    page.goto("https://www.instagram.com/direct/inbox/", wait_until="domcontentloaded")
    page.wait_for_timeout(7000)
    try:
        tl = page.locator("[aria-label='Thread list']").first
        txt = tl.inner_text(timeout=4000)
        found["inbox"] = _parse_inbox_text(txt)
    except Exception as e:
        found["inbox_error"] = str(e)

    # --- Notifications page ---
    page.goto("https://www.instagram.com/notifications/", wait_until="domcontentloaded")
    page.wait_for_timeout(7000)
    try:
        body = page.locator("body").inner_text(timeout=4000)
        found["notifications"] = _parse_notifications_text(body)
    except Exception as e:
        found["notifications_error"] = str(e)

    # Identify untapped warm prospects (engaged with us, not yet logged)
    known = _known_handles(data)
    notif_handles = [n["handle"] for n in found["notifications"]]
    untapped = [h for h in notif_handles + found["inbox"] + found["requests"]
                if h.lower() not in known]
    # dedupe preserve order
    seen, untapped_unique = set(), []
    for h in untapped:
        if h not in seen:
            seen.add(h)
            untapped_unique.append(h)

    log_action(
        data, session, "inbox_sweep", target="self",
        requests_count=len(found["requests"]),
        inbox_count=len(found["inbox"]),
        notifications_count=len(found["notifications"]),
        requests=found["requests"][:20],
        inbox=found["inbox"][:20],
        notifications=found["notifications"][:30],
        untapped_warm=untapped_unique[:20],
        dry_run=dry,
    )
    found["untapped_warm"] = untapped_unique
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
                  f"inbox={len(found.get('inbox', []))} "
                  f"notifications={len(found.get('notifications', []))} "
                  f"untapped_warm={len(found.get('untapped_warm', []))}")
            for h in found.get("requests", [])[:10]:
                print(f"  REQUEST: {h}")
            for h in found.get("inbox", [])[:10]:
                print(f"  INBOX: {h}")
            for n in found.get("notifications", [])[:15]:
                print(f"  NOTIF: {n['handle']} — {n['action']}")
            for h in found.get("untapped_warm", [])[:10]:
                print(f"  ⚡ UNTAPPED: {h}")

            if args.inbox_only:
                print("[engagement] inbox-only mode — done.")
                return 0

            # --- --full mode: follow-back top untapped_warm prospects ---
            candidates = found.get("untapped_warm", [])
            if not candidates:
                print("[engagement] full mode — no untapped_warm candidates, nothing to do.")
                return 0
            summary = outbound_follow_round(page, data, session, candidates, args.dry_run)
            print(f"[engagement] follow_round attempted={summary['attempted']} "
                  f"followed={summary['followed']} skipped={summary['skipped']} "
                  f"errors={summary['errors']} blocked={summary['blocked']}")
            for r in summary["results"]:
                print(f"  FOLLOW: {r['handle']} → {r['result']}")
            if summary["blocked"]:
                data.setdefault("summary", {})["blocked_at"] = dt.datetime.utcnow().isoformat()
                save_log(data)
                return 4
            return 0

        finally:
            ctx.close()

if __name__ == "__main__":
    sys.exit(main())
