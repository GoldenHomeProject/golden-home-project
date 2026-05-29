#!/usr/bin/env python3
"""GHP Comment Bot — post thoughtful comments on big organizing accounts.

Same Pi Playwright pattern as automation/send_ig_dm.py + automation/
engagement.py: persistent Chromium profile at ~/.config/ghp-chromium,
IG-logged-in as @golden_home_project, real React-trusted events.

Why this exists: the engagement bot (engagement.py) already likes +
follows targeted accounts. That's passive — it puts US into THEIR
notifications. This script puts our comment into THEIR audience's view.
A well-timed thoughtful comment on a 100K+ Reel is the lowest-cost way
to surface @golden_home_project to thousands of organizing-niche viewers
without any new content production.

Cadence: 5 comments/day cap (matches engagement.py DAILY_CAPS.comment).
Targets: curated list at automation/comment_targets.json. Each target =
{handle, niche_summary}. Script picks accounts NOT commented on within
the last 7 days, navigates to their profile, opens the most recent
non-pinned post, generates a Claude-written contextual comment, posts.

Skip patterns reused from engagement.py (paid-promo bot suffixes,
giveaway/promo keywords).

Output:
- Append to social/engagement_log.json under actions[] with
  action='comment_posted' so cadence machinery sees it.
- Don't commit; engagement.service ExecStartPost handles the push.

Run (on Pi):
    xvfb-run -a ~/.ghp-engagement/venv/bin/python \\
      automation/comment_on_targets.py --max 3
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import random
import re
import subprocess
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
LOG_PATH = REPO_ROOT / "social" / "engagement_log.json"
TARGETS_PATH = REPO_ROOT / "automation" / "comment_targets.json"
PROFILE_DIR = Path.home() / ".config" / "ghp-chromium"
CHROMIUM_BIN = "/usr/bin/chromium"

DAILY_CAP = 5
RECOMMENT_DAYS = 7  # don't comment on same handle within this window

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
    if action == "comment_posted":
        s["lifetime_comments_outbound"] = s.get("lifetime_comments_outbound", 0) + 1
    s["last_session"] = session
    s["last_updated"] = entry["timestamp"]
    s["total_actions"] = s.get("total_actions", 0) + 1
    save_log(data)


def jitter(lo: float, hi: float) -> None:
    time.sleep(random.uniform(lo, hi))


def should_skip(handle: str) -> str | None:
    h = handle.lower()
    if any(h.endswith(s) for s in SKIP_SUFFIXES):
        return "skip_suffix"
    if any(k in h for k in SKIP_KEYWORDS):
        return "skip_keyword"
    return None


def recently_commented(data: dict, handle: str) -> bool:
    cutoff = (dt.datetime.utcnow() - dt.timedelta(days=RECOMMENT_DAYS)).isoformat()
    for a in reversed(data.get("actions", [])):
        if (a.get("target") or "").lower() == handle.lower() and \
                a.get("action") == "comment_posted" and \
                a.get("timestamp", "") > cutoff:
            return True
    return False


def todays_comments(data: dict) -> int:
    today = dt.datetime.utcnow().strftime("%Y-%m-%d")
    return sum(1 for a in data.get("actions", [])
               if a.get("action") == "comment_posted" and (a.get("timestamp") or "").startswith(today))


def claude_comment(post_caption: str, post_url: str, target_handle: str) -> str:
    """Ask Claude for a thoughtful, non-spammy comment on this post.

    Goals: read like a peer creator in the same niche. NEVER drop our
    handle, our affiliate link, or anything that smells like outbound
    promo (IG nukes those instantly). The visibility comes from the
    comment having engagement of its own, which then surfaces the
    @golden_home_project handle to viewers who tap the comment author.
    """
    prompt = f"""You are commenting AS @golden_home_project (an organizing
niche affiliate account) on another creator's IG post. The point of the
comment is to be genuinely useful to anyone reading the comments — so
when they tap the commenter to see who said it, they're interested in
the @golden_home_project profile.

Hard rules:
- NEVER mention @golden_home_project, our products, our affiliate links,
  or the word "link in bio". That kills the comment as spam.
- NEVER ask the creator to DM us or follow us.
- DO be specific to THIS post. Reference an actual detail from the caption.
- DO add a useful angle the creator didn't cover, OR ask one good question.
- DO sound like a real organizer who knows the niche.
- Tone: warm, peer-to-peer, NOT customer-to-creator.

Length: 1-2 short sentences MAX. Comments over 25 words look like ads.

Post creator: @{target_handle}
Post URL: {post_url}
Post caption (truncated):
{post_caption[:600]}

Return ONLY the comment text. No quotes, no explanation, no prefix."""
    try:
        proc = subprocess.run(
            ["claude", "--print"],
            input=prompt,
            text=True,
            capture_output=True,
            timeout=90,
        )
        if proc.returncode != 0:
            print(f"  [claude] rc={proc.returncode} stderr={(proc.stderr or '')[:200]}")
            return ""
        out = (proc.stdout or "").strip()
        # strip quotes if Claude wrapped
        out = out.strip('"\'')
        # one-line first
        out = out.split("\n", 1)[0].strip()
        # cap at 200 chars to be safe
        return out[:200]
    except Exception as e:
        print(f"  [claude] error: {e}")
        return ""


def comment_on_latest(handle: str, niche_hint: str, session: str, data: dict) -> str:
    """Navigate to handle's profile, open most recent post, write + send
    a thoughtful comment. Returns status string."""
    reason = should_skip(handle)
    if reason:
        return f"skipped:{reason}"

    if recently_commented(data, handle):
        return "already_commented_in_window"

    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(
            user_data_dir=str(PROFILE_DIR),
            executable_path=CHROMIUM_BIN,
            headless=False,
            viewport={"width": 1280, "height": 800},
            locale="en-US",
        )
        page = ctx.new_page()

        try:
            page.goto(f"https://www.instagram.com/{handle}/",
                      wait_until="domcontentloaded", timeout=20000)
        except Exception as e:
            ctx.close()
            log_action(data, session, "comment_error", handle, reason=f"goto: {e}")
            return f"error:goto"
        jitter(3, 5)

        # Click the first post tile (skip pinned by index — pinned typically first 1-3)
        try:
            # Posts are <a href="/p/...">
            posts = page.locator("a[href*='/p/']").all()
            if not posts:
                ctx.close()
                log_action(data, session, "comment_error", handle, reason="no_posts_on_profile")
                return "no_posts"
            # pick the 2nd post link to skip a likely pinned one
            target = posts[1] if len(posts) > 1 else posts[0]
            target.click()
            jitter(3, 5)
        except Exception as e:
            ctx.close()
            log_action(data, session, "comment_error", handle, reason=f"post_click: {e}")
            return "post_click_failed"

        post_url = page.url
        if "/p/" not in post_url:
            ctx.close()
            log_action(data, session, "comment_error", handle, reason=f"unexpected_url: {post_url}")
            return "unexpected_url"

        # Read the visible post caption
        try:
            caption_loc = page.locator("article h1, article div[data-testid='post-comment']").first
            caption = caption_loc.inner_text(timeout=3000)
        except Exception:
            try:
                caption = page.locator("article").first.inner_text(timeout=3000)[:1200]
            except Exception:
                caption = ""

        # Generate the comment
        comment_text = claude_comment(caption, post_url, handle)
        if not comment_text:
            ctx.close()
            log_action(data, session, "comment_error", handle, reason="claude_empty")
            return "claude_empty"

        # Find comment box and post
        try:
            box = page.locator("textarea[aria-label*='comment'], textarea[placeholder*='comment']").first
            box.wait_for(state="visible", timeout=6000)
            box.click()
            jitter(0.5, 1.0)
            page.keyboard.type(comment_text, delay=random.randint(15, 45))
            jitter(1, 2)
            # IG enables Post button after typing
            post_btn = page.locator(
                "div[role='button']:has-text('Post'), button:has-text('Post')"
            ).first
            post_btn.click()
            jitter(3, 5)
        except Exception as e:
            ctx.close()
            log_action(data, session, "comment_error", handle, reason=f"comment_post: {e}", text=comment_text)
            return "comment_post_failed"

        # Action-block guard
        try:
            body = page.locator("body").inner_text(timeout=2000).lower()
            if "action blocked" in body or "try again later" in body:
                log_action(data, session, "comment_blocked", handle, text=comment_text)
                ctx.close()
                return "action_blocked"
        except Exception:
            pass

        log_action(
            data, session, "comment_posted", handle,
            post_url=post_url,
            text=comment_text,
            caption_seen=caption[:200],
        )
        ctx.close()
        return "posted"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--max", type=int, default=3,
                    help="Max comments this run (hard-bounded by DAILY_CAP)")
    ap.add_argument("--dry", action="store_true")
    args = ap.parse_args()

    if not TARGETS_PATH.exists():
        print(f"ERROR: {TARGETS_PATH.relative_to(REPO_ROOT)} not found", file=sys.stderr)
        return 1
    targets = json.loads(TARGETS_PATH.read_text())
    if not targets:
        print("No targets configured", file=sys.stderr)
        return 1

    data = load_log()
    used_today = todays_comments(data)
    remaining = max(0, DAILY_CAP - used_today)
    n = min(args.max, remaining)
    if n <= 0:
        print(f"[comment-bot] daily cap reached ({used_today}/{DAILY_CAP}), skipping")
        return 0

    session = "comments-" + dt.datetime.utcnow().strftime("%Y-%m-%dT%H%MZ")

    # Filter targets: skip those commented within RECOMMENT_DAYS, shuffle the rest
    fresh = [t for t in targets if not recently_commented(data, t.get("handle", ""))]
    if not fresh:
        print(f"[comment-bot] all {len(targets)} targets within {RECOMMENT_DAYS}d window; skipping")
        return 0
    random.shuffle(fresh)

    picked = 0
    for t in fresh:
        if picked >= n:
            break
        handle = t.get("handle", "").lstrip("@").strip()
        niche = t.get("niche_summary", "")
        if not handle:
            continue
        print(f"[comment-bot] -> @{handle}")
        if args.dry:
            print("  [DRY] would navigate + comment")
            picked += 1
            continue
        result = comment_on_latest(handle, niche, session, data)
        print(f"  result: {result}")
        if result == "posted":
            picked += 1
        # respect human pacing between comments
        jitter(45, 90)

    print(f"[comment-bot] session done. posted={picked}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
