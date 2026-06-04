#!/usr/bin/env python3
"""
dm-funnel.py — Pi-side automated comment->link delivery for @golden_home_project.

Our reels say "comment KEYWORD for the links". True Instagram DMs via the Graph
API are BLOCKED for this app in dev mode (messaging capability requires App
Review: /conversations + private_replies return "(#3) Application does not have
the capability"). So instead of an undeliverable DM, this delivers the affiliate
link as a PUBLIC reply on the commenter's comment — which is fully automated,
needs no extra permissions, and is actually MORE useful (everyone reading the
thread sees the link, not just the one commenter).

Conventions:
  - Reads dm_keyword_registry.json for keyword -> ASIN / direct affiliate_url
  - Reads token + IG id from automation/logs/meta_tokens.json (chmod 600, Pi-local)
  - Only acts on entries with status='live'
  - Idempotent: tracks replied comment_ids in ~/.ghp-dm-funnel/replied_comments.json
  - Reply uses POST /{comment-id}/replies with the real link + FTC disclosure
  - Human-pattern: caps replies/run and jitters between sends
  - Logs to journald + ~/golden-home-project/social/engagement_log.json
"""

import json
import os
import random
import sys
import time
from pathlib import Path
from urllib.parse import quote

import urllib.request
import urllib.error

ROOT = Path(os.environ.get("GHP_REPO_DIR", str(Path.home() / "golden-home-project")))
REGISTRY = ROOT / "social" / "dm_keyword_registry.json"
ENGAGEMENT_LOG = ROOT / "social" / "engagement_log.json"
TOKENS_FILE = ROOT / "automation" / "logs" / "meta_tokens.json"
STATE_DIR = Path.home() / ".ghp-dm-funnel"
REPLIED_FILE = STATE_DIR / "replied_comments.json"
GRAPH = "https://graph.facebook.com/v21.0"
TAG = "goldenhomep06-20"
MAX_REPLIES_PER_RUN = 8  # human-pattern cap; spread across 2-3 runs/day


def log(msg: str) -> None:
    print(f"[dm-funnel] {msg}", flush=True)


def load_tokens() -> tuple[str, str]:
    if not TOKENS_FILE.exists():
        log(f"FATAL: tokens missing at {TOKENS_FILE}")
        sys.exit(1)
    try:
        d = json.loads(TOKENS_FILE.read_text())
        return d["page_access_token"], d["ig_business_account_id"]
    except (json.JSONDecodeError, KeyError) as e:
        log(f"FATAL: tokens file unreadable ({e})")
        sys.exit(1)


def graph_get(path: str, token: str, params: dict | None = None) -> dict:
    params = dict(params or {})
    params["access_token"] = token
    qs = "&".join(f"{k}={quote(str(v))}" for k, v in params.items())
    url = f"{GRAPH}{path}?{qs}"
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        body = e.read().decode(errors="replace")
        log(f"HTTPError {e.code} on GET {path}: {body[:300]}")
        return {}
    except Exception as e:
        log(f"Error on GET {path}: {e}")
        return {}


def graph_post(path: str, token: str, payload: dict) -> dict:
    url = f"{GRAPH}{path}"
    data = json.dumps({**payload, "access_token": token}).encode()
    req = urllib.request.Request(
        url, data=data, headers={"Content-Type": "application/json"}, method="POST"
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        body = e.read().decode(errors="replace")
        log(f"HTTPError {e.code} on POST {path}: {body[:300]}")
        return {}
    except Exception as e:
        log(f"Error on POST {path}: {e}")
        return {}


def load_replied() -> set[str]:
    if not REPLIED_FILE.exists():
        return set()
    try:
        return set(json.loads(REPLIED_FILE.read_text()))
    except json.JSONDecodeError:
        return set()


def save_replied(replied: set[str]) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    REPLIED_FILE.write_text(json.dumps(sorted(replied)))


def append_engagement_log(entry: dict) -> None:
    log_data = []
    if ENGAGEMENT_LOG.exists():
        try:
            log_data = json.loads(ENGAGEMENT_LOG.read_text())
            if not isinstance(log_data, list):
                log_data = []
        except json.JSONDecodeError:
            log_data = []
    log_data.append(entry)
    ENGAGEMENT_LOG.write_text(json.dumps(log_data, indent=2))


def affiliate_url(entry: dict) -> str:
    """Direct merchant link if the registry has one (sjv.io Impact links already
    carry attribution); otherwise a tagged Amazon /dp/ link with ascsubtag."""
    direct = entry.get("affiliate_url")
    if direct:
        return direct
    asin = entry["asin"]
    date = time.strftime("%Y%m%d", time.gmtime())
    return f"https://www.amazon.com/dp/{asin}?tag={TAG}&ascsubtag=ghp-igreply-{date}"


def reply_template(keyword: str, entry: dict) -> str:
    """Public comment reply containing the actual affiliate link + FTC disclosure."""
    url = affiliate_url(entry)
    name = entry.get("product_name", "the product").split("(")[0].strip()
    return (
        f"Here you go! {name}: {url} "
        f"#ad — as an Amazon Associate we earn from qualifying purchases. \U0001f3e1"
    )


def main() -> int:
    if not REGISTRY.exists():
        log(f"FATAL: registry missing at {REGISTRY}")
        return 1

    registry = json.loads(REGISTRY.read_text())
    live_keywords = {
        e["keyword"].upper(): e
        for e in registry.get("entries", [])
        if e.get("status") == "live"
    }
    if not live_keywords:
        log("No live keywords in registry. Exiting.")
        return 0

    token, ig_id = load_tokens()

    replied = load_replied()
    log(f"Loaded {len(replied)} previously-replied comment ids")

    # Pull recent media (last 25 posts)
    media = graph_get(f"/{ig_id}/media", token, {"fields": "id,permalink,timestamp", "limit": 25})
    items = media.get("data", [])
    log(f"Auditing {len(items)} recent posts")

    new_replies = 0
    for m in items:
        if new_replies >= MAX_REPLIES_PER_RUN:
            break
        media_id = m["id"]
        comments = graph_get(
            f"/{media_id}/comments",
            token,
            {"fields": "id,text,username,timestamp", "limit": 50},
        )
        for c in comments.get("data", []):
            if new_replies >= MAX_REPLIES_PER_RUN:
                break
            cid = c["id"]
            if cid in replied:
                continue
            text = (c.get("text") or "").upper()
            matched = None
            for kw in live_keywords:
                # Standalone-token match so "PILLOW" fires but "PILLOWCASE" doesn't
                if kw in text.split() or kw == text.strip():
                    matched = kw
                    break
            if not matched:
                continue

            entry = live_keywords[matched]
            reply_text = reply_template(matched, entry)
            result = graph_post(f"/{cid}/replies", token, {"message": reply_text})
            if result.get("id"):
                replied.add(cid)
                new_replies += 1
                append_engagement_log(
                    {
                        "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                        "type": "comment_reply_link",
                        "post": m.get("permalink"),
                        "comment_id": cid,
                        "from": c.get("username"),
                        "keyword": matched,
                        "asin": entry.get("asin"),
                        "link": affiliate_url(entry),
                        "via": "pi/dm-funnel",
                    }
                )
                log(f"Replied to @{c.get('username')} keyword={matched} -> link sent")
                save_replied(replied)  # persist incrementally so a crash can't double-send
                time.sleep(random.uniform(20, 75))  # human-pattern jitter
            else:
                # Reply failed (deleted comment, rate limit, etc.) — DON'T mark
                # replied, so a transient failure retries next run.
                log(f"Reply FAILED for comment {cid} keyword={matched} — will retry next run")

    save_replied(replied)
    log(f"Done. {new_replies} new link replies. {len(replied)} total tracked.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
