#!/usr/bin/env python3
"""Drain social/pinterest_queue.json -> publish pins on Pinterest via the Pi's
persistent Chromium profile (Playwright). Sister to send_ig_dm.py: same launch
shape, same persistent profile dir, so Pinterest sees consistent device state.

STATUS: UNTESTED pending a logged-in Pinterest business account on the Pi.
The selectors below target Pinterest's web pin-builder as of 2026-05 but WILL
likely need first-run adjustment (the IG comment-bot needed the same — see
commit 002a4bc). Run with --dry first, watch the run, fix selectors, THEN wire
the cron. Do NOT schedule this until one real --no-dry pin has been verified
in the account.

OWNER ACTION REQUIRED (one-time, I cannot do this — account creation is off
limits to the agent):
  1. Create a Pinterest *business* account for Golden Home Project.
  2. On the Pi, log into it once in the persistent profile:
       chromium --user-data-dir=~/.config/ghp-chromium  (then sign in)
  3. Create the boards named in pinterest_queue.json (or let the script pick
     an existing board on first run).

Usage (on Pi):
    xvfb-run -a ~/.ghp-engagement/venv/bin/python automation/post_pinterest.py --max 2 --dry
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import random
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
QUEUE_PATH = REPO_ROOT / "social" / "pinterest_queue.json"
LOG_PATH = REPO_ROOT / "social" / "pinterest_post_log.json"
PROFILE_DIR = Path.home() / ".config" / "ghp-chromium"
CHROMIUM_BIN = "/usr/bin/chromium"
# Use /pin-builder/ — /pin-creation-tool/ renders a different layout that
# lacks the title field and publish button (board-dropdown-save-button count 0).
PIN_BUILDER_URL = "https://www.pinterest.com/pin-builder/"

# Pinterest tolerates more posting than IG, but a brand-new account should
# ramp slowly to avoid spam flags. Keep this low for the first weeks.
DAILY_DEFAULT = 2


def load_json(p: Path, default):
    if p.exists():
        try:
            return json.loads(p.read_text())
        except Exception:
            return default
    return default


def save_queue(q) -> None:
    QUEUE_PATH.write_text(json.dumps(q, indent=2))


def log_event(action: str, pin_id: str, **extra) -> None:
    log = load_json(LOG_PATH, {"events": []})
    e = {"ts": dt.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
         "action": action, "pin_id": pin_id}
    e.update(extra)
    log["events"].append(e)
    LOG_PATH.write_text(json.dumps(log, indent=2))


def jitter(lo: float, hi: float) -> None:
    time.sleep(random.uniform(lo, hi))


def posted_today(log: dict) -> int:
    today = dt.datetime.utcnow().strftime("%Y-%m-%d")
    return sum(1 for e in log.get("events", [])
               if e.get("action") == "pin_published" and e.get("ts", "").startswith(today))


def detect_login_wall(page) -> bool:
    # Only trust a URL-based redirect. The pin builder shows an inline email
    # field even when logged in, so element-presence checks false-positive.
    return "/login" in page.url or "/signup" in page.url


def detect_block(page) -> bool:
    try:
        body = page.locator("body").inner_text(timeout=2000).lower()
    except Exception:
        return False
    return any(n in body for n in (
        "you've been blocked", "try again later", "unusual activity",
        "temporarily", "spam"))


def publish_pin(pin: dict, dry: bool) -> str:
    from playwright.sync_api import sync_playwright

    img = REPO_ROOT / pin["image_path"]
    if not img.exists():
        return "missing_image"

    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(
            user_data_dir=str(PROFILE_DIR),
            executable_path=CHROMIUM_BIN,
            headless=False,  # xvfb-run provides the display
            viewport={"width": 1280, "height": 900},
            locale="en-US",
        )
        page = ctx.new_page()
        try:
            page.goto(PIN_BUILDER_URL, wait_until="domcontentloaded", timeout=25000)
        except Exception as e:
            ctx.close()
            return f"error:goto:{e}"
        jitter(3, 5)

        if detect_login_wall(page):
            ctx.close()
            return "login_wall"
        if detect_block(page):
            log_event("blocked", pin["id"], where="builder")
            ctx.close()
            return "blocked"

        # --- file upload: Pinterest builder uses a hidden <input type=file> ---
        try:
            page.set_input_files("input[type='file']", str(img), timeout=10000)
        except Exception as e:
            ctx.close()
            return f"upload_failed:{e}"
        jitter(3, 6)

        # First-run onboarding tour ("Great Pins made easy") overlays the
        # builder and silently swallows the publish click. Dismiss it.
        try:
            if page.get_by_text("Great Pins made easy").count():
                page.keyboard.press("Escape")
                jitter(1, 2)
        except Exception:
            pass

        # --- title / description / link fields ---
        # IDs carry a per-draft UUID suffix (pin-draft-title-<uuid>), so match
        # by prefix. Description is a contenteditable div, not a textarea.
        def fill(selectors: list[str], value: str) -> bool:
            for sel in selectors:
                try:
                    loc = page.locator(sel).first
                    if loc.count() and loc.is_visible(timeout=1500):
                        loc.click()
                        loc.fill(value)
                        return True
                except Exception:
                    continue
            return False

        fill(["textarea[id^='pin-draft-title']", "textarea[placeholder*='title' i]"],
             pin["title"])
        jitter(0.5, 1.2)
        fill(["div[contenteditable='true'][aria-label*='Pin is' i]",
              "div[contenteditable='true'][aria-label*='Tell everyone' i]",
              "div[contenteditable='true']"], pin["description"])
        jitter(0.5, 1.2)
        fill(["textarea[id^='pin-draft-link']",
              "textarea[placeholder*='destination' i]",
              "input[placeholder*='link' i]"], pin["link"])
        jitter(1, 2)

        if dry:
            print(f"[DRY] would publish {pin['id']} -> board {pin['board']!r}")
            ctx.close()
            return "dry_run_ok"

        # --- publish to the target board ---
        # The red "Publish" button (board-dropdown-save-button) publishes to the
        # board shown in the dropdown. Switch boards first only when the
        # pre-selected one isn't our target (clicking a board row selects it and
        # closes the dropdown), then click the main Publish button.
        board = pin["board"]
        save_btn = page.locator("[data-test-id='board-dropdown-save-button']").first
        select_btn = page.locator("[data-test-id='board-dropdown-select-button']").first
        try:
            current = select_btn.inner_text(timeout=2000)
        except Exception:
            current = ""
        if board not in current:
            try:
                select_btn.click()
                jitter(1.5, 2.5)
                page.locator(f"[data-test-id='board-row-{board}']").first.click()
                jitter(2, 3)
            except Exception:
                ctx.close()
                return f"board_select_failed:{board}"
        try:
            save_btn.click(timeout=8000)
        except Exception:
            ctx.close()
            return "no_publish_button"
        jitter(4, 7)

        if detect_block(page):
            log_event("blocked", pin["id"], where="after_publish")
            ctx.close()
            return "blocked_after_publish"

        # Confirm the publish landed instead of trusting the click. On success
        # Pinterest shows a "You created a Pin!" modal with a "See your Pin" CTA.
        confirmed = False
        try:
            page.wait_for_selector(
                "text=/you created a pin|see your pin|your pin has been/i",
                timeout=12000)
            confirmed = True
        except Exception:
            confirmed = False

        if not confirmed:
            log_event("publish_unconfirmed", pin["id"], board=board, link=pin["link"])
            ctx.close()
            return "publish_unconfirmed"

        log_event("pin_published", pin["id"], board=board, link=pin["link"])
        ctx.close()
        return "published"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--max", type=int, default=DAILY_DEFAULT)
    ap.add_argument("--dry", action="store_true", default=True,
                    help="dry run (default True until first verified post)")
    ap.add_argument("--no-dry", dest="dry", action="store_false")
    args = ap.parse_args()

    queue = load_json(QUEUE_PATH, [])
    log = load_json(LOG_PATH, {"events": []})
    remaining = max(0, args.max - posted_today(log))
    pending = [p for p in queue if not p.get("posted")]
    if not pending:
        print("[pinterest] queue empty — nothing to post. Run pinterest_pipeline.py to refill.")
        return 0
    if remaining <= 0:
        print(f"[pinterest] daily cap ({args.max}) reached; {len(pending)} still pending.")
        return 0

    done = 0
    for pin in pending[:remaining]:
        result = publish_pin(pin, args.dry)
        print(f"[pinterest] {pin['id']}: {result}")
        if result in ("published",):
            pin["posted"] = True
            pin["posted_at"] = dt.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
            save_queue(queue)
            done += 1
            jitter(20, 45)  # space out real posts
        elif result == "dry_run_ok":
            done += 1
        elif result in ("login_wall",):
            print("  -> Pinterest not logged in on this profile. See OWNER ACTION in the header.")
            return 1
        elif result.startswith("blocked"):
            print("  -> stopping: Pinterest flagged activity. Back off and investigate.")
            return 1
        elif result == "publish_unconfirmed":
            print("  -> stopping: clicked publish but saw no success toast. "
                  "Pin left pending; verify the account before re-running to "
                  "avoid a double-post.")
            return 1
    print(f"[pinterest] {done} pin(s) {'(dry)' if args.dry else 'published'}; "
          f"{len(pending) - (done if not args.dry else 0)} pending.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
