#!/usr/bin/env python3
"""reddit_post.py — post to Reddit through a real browser on the Pi, ONLY when Ian says so.

What this is
------------
A posting assistant for Ian's own Reddit account. It does what Ian would do by hand —
opens old.reddit.com in a normal logged-in browser, fills in one text post, submits it —
so a post can be sent from the Pi at his direction. It does not use the Reddit API.

What this deliberately is NOT (decided with Ian, 2026-09-24)
------------------------------------------------------------
* NOT scheduled. There is no cron entry and there must never be one. GHP is not posting
  to Reddit; this exists so a post can be made when Ian asks for one.
* NOT a volume tool. One post per invocation, a minimum gap between posts, and a daily
  cap. Posting in bursts is exactly what gets an account banned.
* NOT disguised. No fingerprint spoofing, no fake mouse jitter, no rotating identities.
  It is Ian's account in a normal browser profile; pacing is there to keep it to a sane
  human cadence, not to evade detection.
* NOT a credential handler. It never sees a password. Ian logs in once, by hand, in the
  browser window `--login` opens on the Pi's desktop (reach it with Raspberry Pi
  Connect). The session then lives in the profile directory.

Safety rails, all on by default
-------------------------------
* DRY RUN unless --post is given: fills the form, screenshots it, does not submit.
* --post also requires --confirm r/<subreddit>, spelled out, so a post cannot go to the
  wrong community by typo or by a stale command in shell history.
* Refuses raw affiliate links (Amazon tag=, amzn.to) unless --allow-affiliate. Reddit's
  filters treat them as spam; the default is a link to our own page, disclosed.
* Refuses if the last post was < MIN_GAP_MIN minutes ago, or DAILY_CAP is reached.
* Verifies the submit landed on a /comments/ permalink before recording success.

Usage
-----
  # one-time: open a browser on the Pi desktop and sign in by hand
  automation/run_reddit.sh --login

  # rehearse (default): fill and screenshot, no submit
  automation/run_reddit.sh --subreddit organization --title "..." --body-file draft.md

  # actually post, at Ian's direction
  automation/run_reddit.sh --subreddit organization --title "..." --body-file draft.md \
      --post --confirm r/organization
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PROFILE_DIR = Path.home() / ".config" / "ghp-reddit-chromium"   # separate from Pinterest
# Outside the repo on purpose: the repo is public-facing and these hold Ian's username.
STATE = Path.home() / ".ghp-reddit"
LEDGER = STATE / "reddit_posted.json"
SHOTS = STATE / "shots"
BASE = "https://old.reddit.com"   # plain HTML forms; far steadier than the web-component UI

MIN_GAP_MIN = 60
DAILY_CAP = 2
AFFILIATE_RE = re.compile(r"(?:[?&]tag=[\w-]+-20\b|amzn\.to/|amazon\.[a-z.]+/.*[?&]tag=)", re.I)


def _ledger() -> list:
    try:
        return json.loads(LEDGER.read_text())
    except (OSError, ValueError):
        return []


def _rate_ok(now: datetime) -> str | None:
    posts = [e for e in _ledger() if e.get("status") == "posted"]
    if not posts:
        return None
    last = max(datetime.fromisoformat(e["at"]) for e in posts)
    if now - last < timedelta(minutes=MIN_GAP_MIN):
        return f"last post was {int((now - last).total_seconds() // 60)} min ago; minimum gap is {MIN_GAP_MIN}"
    today = sum(1 for e in posts if e["at"][:10] == now.date().isoformat())
    if today >= DAILY_CAP:
        return f"daily cap of {DAILY_CAP} posts reached"
    return None


def _record(entry: dict) -> None:
    STATE.mkdir(parents=True, exist_ok=True)
    led = _ledger()
    led.append(entry)
    LEDGER.write_text(json.dumps(led, indent=2) + "\n")


def _pause(seconds: float) -> None:
    time.sleep(seconds)


def _logged_in(page) -> str | None:
    """Username if old.reddit shows a signed-in header, else None."""
    user = page.locator("span.user a").first
    try:
        if user.count() and "login" not in (user.get_attribute("href") or ""):
            return (user.inner_text() or "").strip() or None
    except Exception:
        pass
    return None


def _launch(p, headless: bool):
    return p.chromium.launch_persistent_context(
        user_data_dir=str(PROFILE_DIR),
        headless=headless,
        viewport={"width": 1280, "height": 900},
        args=["--no-first-run", "--no-default-browser-check"],
    )


def do_login() -> int:
    from playwright.sync_api import sync_playwright
    PROFILE_DIR.mkdir(parents=True, exist_ok=True)
    print("[reddit] opening a browser on the Pi desktop. Sign in by hand (Raspberry Pi "
          "Connect → Screen sharing). The window closes itself once you are in.")
    with sync_playwright() as p:
        ctx = _launch(p, headless=False)
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        page.goto(f"{BASE}/login", wait_until="domcontentloaded")
        # Poll for the session cookie rather than waiting for a window close: Reddit may
        # bounce the login through www.reddit.com, and closing the window kills the context.
        who = None
        deadline = time.time() + 15 * 60
        while time.time() < deadline:
            try:
                if any(c["name"] == "reddit_session" for c in ctx.cookies()):
                    _pause(3)
                    page.goto(BASE, wait_until="domcontentloaded")
                    who = _logged_in(page)
                    break
            except Exception:
                break   # window closed before sign-in finished
            _pause(5)
        try:
            ctx.close()
        except Exception:
            pass
    print(f"[reddit] signed in as u/{who}" if who else "[reddit] NOT signed in — run --login again")
    return 0 if who else 1


def do_post(a) -> int:
    body = Path(a.body_file).read_text() if a.body_file else (a.body or "")
    title = a.title.strip()
    sub = a.subreddit.strip().removeprefix("r/").strip("/")

    # ---- rails that do not need a browser -----------------------------------
    if not title or not body.strip():
        print("[reddit] REFUSED: title and body are both required"); return 2
    if len(title) > 300:
        print("[reddit] REFUSED: Reddit titles max out at 300 chars"); return 2
    if AFFILIATE_RE.search(title + "\n" + body) and not a.allow_affiliate:
        print("[reddit] REFUSED: raw affiliate link in the post. Reddit's filters treat "
              "these as spam. Link our page instead, or pass --allow-affiliate knowingly.")
        return 2
    if a.post:
        if a.confirm != f"r/{sub}":
            print(f"[reddit] REFUSED: --post needs --confirm r/{sub} spelled out"); return 2
        why = _rate_ok(datetime.now(timezone.utc))
        if why:
            print(f"[reddit] REFUSED: {why}"); return 2

    from playwright.sync_api import sync_playwright
    SHOTS.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    with sync_playwright() as p:
        ctx = _launch(p, headless=False)   # run_reddit.sh wraps this in xvfb
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        try:
            page.goto(f"{BASE}/r/{sub}/submit?selftext=true", wait_until="domcontentloaded")
            _pause(2.5)
            who = _logged_in(page)
            if not who:
                print("[reddit] not signed in — run automation/run_reddit.sh --login first")
                return 3
            if page.locator("textarea[name=title]").count() == 0:
                shot = SHOTS / f"{stamp}-no-form.png"; page.screenshot(path=str(shot))
                print(f"[reddit] no submit form on r/{sub} (private, banned, or text posts "
                      f"disabled). Screenshot: {shot}")
                return 4

            page.locator("textarea[name=title]").fill(title)
            _pause(1.5)
            page.locator("textarea[name=text]").fill(body)
            _pause(2.0)
            shot = SHOTS / f"{stamp}-filled.png"
            page.screenshot(path=str(shot), full_page=True)

            if not a.post:
                print(f"[reddit] DRY RUN as u/{who} → r/{sub}. Form filled, NOT submitted. "
                      f"Screenshot: {shot}")
                _record({"at": datetime.now(timezone.utc).isoformat(), "status": "dry_run",
                         "subreddit": sub, "title": title, "user": who,
                         "screenshot": str(shot)})
                return 0

            page.locator("button[name=submit], button[type=submit]:has-text('submit')").first.click()
            page.wait_for_load_state("domcontentloaded")
            _pause(4.0)
            url = page.url
            done = SHOTS / f"{stamp}-result.png"
            page.screenshot(path=str(done), full_page=True)
            if "/comments/" not in url:
                err = ""
                try:
                    err = page.locator(".error:visible, .status:visible").first.inner_text()[:200]
                except Exception:
                    pass
                print(f"[reddit] submit did NOT land on a post (url={url}). {err} "
                      f"Screenshot: {done}")
                _record({"at": datetime.now(timezone.utc).isoformat(), "status": "failed",
                         "subreddit": sub, "title": title, "user": who, "url": url,
                         "error": err, "screenshot": str(done)})
                return 5
            print(f"[reddit] POSTED as u/{who}: {url}")
            _record({"at": datetime.now(timezone.utc).isoformat(), "status": "posted",
                     "subreddit": sub, "title": title, "user": who, "url": url,
                     "screenshot": str(done)})
            return 0
        finally:
            ctx.close()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--login", action="store_true", help="one-time manual sign-in")
    ap.add_argument("--subreddit")
    ap.add_argument("--title")
    ap.add_argument("--body")
    ap.add_argument("--body-file")
    ap.add_argument("--post", action="store_true", help="actually submit (default: dry run)")
    ap.add_argument("--confirm", default="", help="must equal r/<subreddit> with --post")
    ap.add_argument("--allow-affiliate", action="store_true")
    a = ap.parse_args()
    if a.login:
        return do_login()
    if not a.subreddit or not a.title or not (a.body or a.body_file):
        ap.error("--subreddit, --title and --body/--body-file are required")
    return do_post(a)


if __name__ == "__main__":
    sys.exit(main())
