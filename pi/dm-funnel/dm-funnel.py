#!/usr/bin/env python3
"""
dm-funnel.py — Pi-side audit + backup for Meta-Business-Suite DM automations.

Meta's automated_responses already handle 95% of keyword → DM replies server-side.
This script is the BACKUP: it catches keywords Meta missed, replies to comments
that mention a keyword without a top-level match, and logs every action.

Conventions:
  - Reads dm_keyword_registry.json for keyword → ASIN/affiliate_url mapping
  - Reads META_ACCESS_TOKEN + IG_BUSINESS_ACCOUNT_ID from `pass`
  - Only acts on entries with status='live'
  - Idempotent: tracks replied comment_ids in state/replied_comments.json
  - Comment auto-reply uses POST /{comment-id}/replies
  - Logs to journald + ~/golden-home-project/social/engagement_log.json
"""

import json
import os
import subprocess
import sys
import time
from pathlib import Path
from urllib.parse import quote

import urllib.request
import urllib.error

ROOT = Path(os.environ.get("GHP_REPO_DIR", str(Path.home() / "golden-home-project")))
REGISTRY = ROOT / "social" / "dm_keyword_registry.json"
ENGAGEMENT_LOG = ROOT / "social" / "engagement_log.json"
STATE_DIR = Path.home() / ".ghp-dm-funnel"
REPLIED_FILE = STATE_DIR / "replied_comments.json"
GRAPH = "https://graph.facebook.com/v21.0"


def log(msg: str) -> None:
    print(f"[dm-funnel] {msg}", flush=True)


def pass_get(name: str) -> str:
    try:
        out = subprocess.check_output(["pass", "show", name], stderr=subprocess.DEVNULL)
        return out.decode().strip()
    except subprocess.CalledProcessError:
        log(f"FATAL: pass entry '{name}' missing. Run: echo '<value>' | pass insert -e {name}")
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


def reply_template(keyword: str, entry: dict) -> str:
    """Comment reply pointing to the DM the user is about to receive."""
    return (
        f"Sent you a DM with the link! Check your messages for the {keyword.lower()} "
        f"product. (If you don't see it, make sure your DM requests are open.)"
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

    token = pass_get("ghp/meta_access_token")
    ig_id = pass_get("ghp/ig_business_account_id")

    replied = load_replied()
    log(f"Loaded {len(replied)} previously-replied comment ids")

    # Pull recent media (last 25 posts)
    media = graph_get(f"/{ig_id}/media", token, {"fields": "id,permalink,timestamp", "limit": 25})
    items = media.get("data", [])
    log(f"Auditing {len(items)} recent posts")

    new_replies = 0
    for m in items:
        media_id = m["id"]
        comments = graph_get(
            f"/{media_id}/comments",
            token,
            {"fields": "id,text,username,timestamp", "limit": 50},
        )
        for c in comments.get("data", []):
            cid = c["id"]
            if cid in replied:
                continue
            text = (c.get("text") or "").upper()
            matched = None
            for kw in live_keywords:
                # Word-boundary-ish match: keyword as standalone token
                if kw in text.split() or kw == text.strip():
                    matched = kw
                    break
            if not matched:
                # Don't mark as replied — Meta might process this one later
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
                        "type": "comment_reply",
                        "post": m.get("permalink"),
                        "comment_id": cid,
                        "from": c.get("username"),
                        "keyword": matched,
                        "asin": entry.get("asin"),
                        "via": "pi/dm-funnel",
                    }
                )
                log(f"Replied to @{c.get('username')} keyword={matched}")
            else:
                # Meta might have already replied (its own automation) — mark as
                # replied to avoid duplicate attempts on the same comment id.
                replied.add(cid)

    save_replied(replied)
    log(f"Done. {new_replies} new replies. {len(replied)} total tracked.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
