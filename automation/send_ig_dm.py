#!/usr/bin/env python3
"""Send a single cold-outreach DM via the Pi's persistent IG-logged-in
Chromium profile. Sister to automation/engagement.py — same launch shape,
same persistent profile, same UA, so Meta sees consistent device state.

Usage (on Pi):
    xvfb-run -a ~/.ghp-engagement/venv/bin/python automation/send_ig_dm.py \
        --handle organizedbyellis --body-file /tmp/dm_body.txt

Append-only log: writes one entry per attempt to engagement_log.json under
the same actions[] list so the rate-limit / cadence machinery in
engagement.py sees the activity.

Why this exists separately from engagement.py: engagement.py is for the
2x/day passive sweep (inbox + follows + replies). Cold outreach is a
different cadence (≤1/day per target) and a different prompt template, so
it's cleaner to keep them out of one another's blast radius.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import random
import re
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
LOG_PATH = REPO_ROOT / "social" / "engagement_log.json"
PROFILE_DIR = Path.home() / ".config" / "ghp-chromium"
CHROMIUM_BIN = "/usr/bin/chromium"

# Skip patterns reused from engagement.py
SKIP_SUFFIXES = ("._community",)
SKIP_KEYWORDS = ("giveaway", "promo", "alltypes")


def load_log() -> dict:
    return json.loads(LOG_PATH.read_text())


def save_log(d: dict) -> None:
    LOG_PATH.write_text(json.dumps(d, indent=2))


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
    if action.startswith("dm_"):
        s["lifetime_dms"] = s.get("lifetime_dms", 0) + 1
    s["last_session"] = session
    s["last_updated"] = entry["timestamp"]
    s["total_actions"] = s.get("total_actions", 0) + 1
    save_log(data)


def jitter(lo: float, hi: float) -> None:
    time.sleep(random.uniform(lo, hi))


def detect_login_wall(page) -> bool:
    if "/accounts/login" in page.url or "/accounts/onetap" in page.url:
        return True
    try:
        if page.locator("input[name='username']").count() > 0:
            return True
    except Exception:
        pass
    return False


def detect_action_block(page) -> bool:
    try:
        body = page.locator("body").inner_text(timeout=2000).lower()
    except Exception:
        return False
    needles = ("action blocked", "try again later", "we restrict certain activity",
               "can't receive your message")
    return any(n in body for n in needles)


def should_skip(handle: str) -> str | None:
    h = handle.lower()
    if any(h.endswith(s) for s in SKIP_SUFFIXES):
        return "skip_suffix"
    if any(k in h for k in SKIP_KEYWORDS):
        return "skip_keyword"
    return None


def send_dm(handle: str, body: str, session: str, dry: bool) -> str:
    """Open profile, click Message, type body, press Enter. Returns status."""
    from playwright.sync_api import sync_playwright

    reason = should_skip(handle)
    if reason:
        return f"skipped:{reason}"

    data = load_log()
    # Refuse to spam: don't re-DM a handle we've DMed in the last 14 days.
    cutoff = (dt.datetime.utcnow() - dt.timedelta(days=14)).isoformat()
    for a in reversed(data.get("actions", [])):
        if (a.get("target") or "").lower() == handle.lower() and \
                a.get("action", "").startswith("dm_") and a.get("timestamp", "") > cutoff:
            return "already_dmed_in_window"

    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(
            user_data_dir=str(PROFILE_DIR),
            executable_path=CHROMIUM_BIN,
            headless=False,  # xvfb-run gives us a display
            viewport={"width": 1280, "height": 800},
            locale="en-US",
        )
        page = ctx.new_page()

        try:
            page.goto(f"https://www.instagram.com/{handle}/",
                      wait_until="domcontentloaded", timeout=20000)
        except Exception as e:
            ctx.close()
            log_action(data, session, "dm_error", handle, reason=f"goto: {e}")
            return f"error:goto"
        jitter(2, 4)

        if detect_login_wall(page):
            ctx.close()
            return "login_wall"
        if detect_action_block(page):
            log_action(data, session, "dm_blocked", handle, reason="action_block_on_profile")
            ctx.close()
            return "blocked"

        # Click Message button on profile header
        try:
            msg_btn = page.get_by_role("button", name=re.compile(r"^Message$", re.I)).first
            msg_btn.wait_for(state="visible", timeout=8000)
        except Exception as e:
            log_action(data, session, "dm_error", handle, reason=f"no_message_btn: {e}")
            ctx.close()
            return "no_message_btn"

        if dry:
            print(f"[DRY] Would click Message → type {len(body)} chars → send")
            ctx.close()
            return "dry_run_ok"

        try:
            msg_btn.click()
        except Exception as e:
            log_action(data, session, "dm_error", handle, reason=f"msg_click: {e}")
            ctx.close()
            return "msg_click_failed"
        jitter(3, 5)

        # Notification permission popup ("Turn On Notifications" / "Not Now")
        try:
            not_now = page.get_by_role("button", name=re.compile(r"^Not Now$", re.I)).first
            if not_now.is_visible(timeout=1500):
                not_now.click()
                jitter(1, 2)
        except Exception:
            pass

        # Locate message composer — on IG it's a contenteditable
        try:
            composer = page.locator(
                "div[role='textbox'][contenteditable='true'], textarea[placeholder*='Message']"
            ).first
            composer.wait_for(state="visible", timeout=8000)
            composer.click()
            jitter(0.5, 1.0)
        except Exception as e:
            log_action(data, session, "dm_error", handle, reason=f"no_composer: {e}")
            ctx.close()
            return "no_composer"

        # Type body in human chunks (avoid one giant paste — looks more human)
        for chunk in re.findall(r".{1,40}(?:\s|$)", body):
            page.keyboard.type(chunk, delay=random.randint(15, 45))
            jitter(0.05, 0.15)

        jitter(2, 4)

        if detect_action_block(page):
            log_action(data, session, "dm_blocked", handle, reason="action_block_after_typing")
            ctx.close()
            return "blocked_after_typing"

        # Send: Enter key with composer focused
        try:
            page.keyboard.press("Enter")
        except Exception as e:
            log_action(data, session, "dm_error", handle, reason=f"send: {e}")
            ctx.close()
            return "send_failed"

        jitter(3, 5)

        if detect_action_block(page):
            log_action(data, session, "dm_blocked", handle, reason="action_block_after_send")
            ctx.close()
            return "blocked_after_send"

        # Snapshot the thread URL — confirms a message thread was opened
        thread_url = page.url
        log_action(
            data, session, "dm_sent", handle,
            body_chars=len(body),
            thread_url=thread_url,
            template_tag="path_c_v2_affiliate_split",
        )
        ctx.close()
        return "sent"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--handle", required=True)
    ap.add_argument("--body-file", required=True, type=Path)
    ap.add_argument("--dry", action="store_true")
    args = ap.parse_args()

    body = args.body_file.read_text().strip()
    if not body:
        print("ERROR: body file is empty")
        sys.exit(2)

    session = "outreach-" + dt.datetime.utcnow().strftime("%Y-%m-%dT%H%MZ")
    result = send_dm(args.handle, body, session, args.dry)
    print(f"[send_ig_dm] result: {result}")
    sys.exit(0 if result in ("sent", "dry_run_ok", "already_dmed_in_window") else 1)


if __name__ == "__main__":
    main()
