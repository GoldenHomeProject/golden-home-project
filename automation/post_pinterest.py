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
PIN_BUILDER_URL = "https://www.pinterest.com/pin-creation-tool/"

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
    return "/login" in page.url or "/business/" in page.url or \
        page.locator("input[name='id'], input#email").count() > 0


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

        # --- title / description / link fields ---
        # Selectors are best-effort; verify on first --dry run.
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

        fill(["textarea#pin-draft-title", "textarea[placeholder*='title' i]",
              "input[placeholder*='title' i]"], pin["title"])
        jitter(0.5, 1.2)
        fill(["div[role='textbox'][aria-label*='description' i]",
              "textarea[placeholder*='description' i]",
              "[data-test-id='pin-draft-description'] textarea"], pin["description"])
        jitter(0.5, 1.2)
        fill(["textarea#pin-draft-link", "input[placeholder*='link' i]",
              "input[aria-label*='destination' i]"], pin["link"])
        jitter(1, 2)

        if dry:
            print(f"[DRY] would publish {pin['id']} -> board {pin['board']!r}")
            ctx.close()
            return "dry_run_ok"

        # --- publish button ---
        published = False
        for sel in ["[data-test-id='board-dropdown-save-button']",
                    "button:has-text('Publish')", "button:has-text('Save')"]:
            try:
                btn = page.locator(sel).first
                if btn.count() and btn.is_visible(timeout=2000):
                    btn.click()
                    published = True
                    break
            except Exception:
                continue
        if not published:
            ctx.close()
            return "no_publish_button"
        jitter(4, 7)

        if detect_block(page):
            log_event("blocked", pin["id"], where="after_publish")
            ctx.close()
            return "blocked_after_publish"

        log_event("pin_published", pin["id"], board=pin["board"], link=pin["link"])
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
    print(f"[pinterest] {done} pin(s) {'(dry)' if args.dry else 'published'}; "
          f"{len(pending) - (done if not args.dry else 0)} pending.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
