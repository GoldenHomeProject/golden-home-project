#!/usr/bin/env python3
"""
engagement-targets.py — overnight Pi job that produces a ranked engagement
target list for the human (you) to act on in ~2 min/morning.

NO AUTOMATED LIKING. NO AUTOMATED FOLLOWING. NO AUTOMATED COMMENTING.
The script ONLY uses Meta Graph API's sanctioned hashtag search to discover
posts, scores them, and writes a JSON file. The HUMAN does the engagement
from their phone.

Sanctioned endpoints used:
  - GET /ig_hashtag_search?user_id={ig-id}&q={hashtag}
  - GET /{hashtag-id}/recent_media?user_id={ig-id}&fields=...
  - GET /{hashtag-id}/top_media?user_id={ig-id}&fields=...

Output: ~/golden-home-project/social/engagement_targets_YYYY-MM-DD.json
The daily-loop sends a daily summary push, and this file is what to tap-through.
"""

import json
import os
import subprocess
import sys
import time
from datetime import date
from pathlib import Path
from urllib.parse import quote

import urllib.error
import urllib.request

ROOT = Path(os.environ.get("GHP_REPO_DIR", str(Path.home() / "golden-home-project")))
REGISTRY = ROOT / "social" / "dm_keyword_registry.json"
OUTPUT_DIR = ROOT / "social"
GRAPH = "https://graph.facebook.com/v21.0"

# Tight, niche-aligned hashtags only. Wider tags (#home, #lifestyle) pull
# spam + brands and waste the daily target slots.
HASHTAGS = [
    "homeorganization",
    "kitchenorganization",
    "smallspaceliving",
    "organizingtips",
    "amazonfindshome",
    "underbedstorage",
    "cordmanagement",
    "neatfreaks",
]
TARGET_COUNT = 10  # final ranked list size


def log(msg: str) -> None:
    print(f"[engagement-targets] {msg}", flush=True)


def pass_get(name: str) -> str:
    try:
        out = subprocess.check_output(["pass", "show", name], stderr=subprocess.DEVNULL)
        return out.decode().strip()
    except subprocess.CalledProcessError:
        log(f"FATAL: pass entry '{name}' missing.")
        sys.exit(1)


def graph_get(path: str, token: str, params: dict | None = None) -> dict:
    params = dict(params or {})
    params["access_token"] = token
    qs = "&".join(f"{k}={quote(str(v))}" for k, v in params.items())
    url = f"{GRAPH}{path}?{qs}"
    try:
        with urllib.request.urlopen(url, timeout=30) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        log(f"HTTP {e.code} on {path}: {e.read().decode(errors='replace')[:200]}")
        return {}
    except Exception as e:
        log(f"Error on {path}: {e}")
        return {}


def score(post: dict) -> float:
    """Higher = better target for engagement. Tuned for niche-cluster strategy:
       - Smaller accounts (less than ~50k followers proxy: likes < 1000) score higher
       - Recent posts (last 6h) score higher
       - High like:comment ratio = real engagement, not bot traffic"""
    likes = post.get("like_count") or 0
    comments = post.get("comments_count") or 0
    ts = post.get("timestamp", "")

    # Age in hours (best effort)
    age_h = 24.0
    if ts:
        try:
            t = time.mktime(time.strptime(ts[:19], "%Y-%m-%dT%H:%M:%S"))
            age_h = max(0.5, (time.time() - t) / 3600.0)
        except Exception:
            pass

    # Niche-account proxy: too many likes = big account, ignore
    if likes > 5000:
        return -1.0
    if likes < 10:
        return 0.1  # zero-eng, low signal, low priority

    recency = max(0.0, 1.0 - (age_h / 24.0))  # 1.0 at posted-now, 0 at 24h
    engagement = (likes + 3 * comments) / 100.0
    return round(recency * 2.0 + engagement, 3)


def main() -> int:
    token = pass_get("ghp/meta_access_token")
    ig_id = pass_get("ghp/ig_business_account_id")

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    candidates = []
    for tag in HASHTAGS:
        # 1) resolve hashtag → id
        hsr = graph_get("/ig_hashtag_search", token, {"user_id": ig_id, "q": tag})
        data = hsr.get("data") or []
        if not data:
            log(f"#{tag}: no id returned")
            continue
        htag_id = data[0]["id"]

        # 2) pull recent media (last 24h)
        rec = graph_get(
            f"/{htag_id}/recent_media",
            token,
            {
                "user_id": ig_id,
                "fields": "id,permalink,caption,like_count,comments_count,timestamp,media_type",
                "limit": 25,
            },
        )
        for m in rec.get("data") or []:
            m["__hashtag"] = tag
            candidates.append(m)
        time.sleep(0.3)  # gentle to the API

    log(f"Collected {len(candidates)} candidates across {len(HASHTAGS)} hashtags")

    # Dedup by post id
    seen = set()
    deduped = []
    for c in candidates:
        if c["id"] in seen:
            continue
        seen.add(c["id"])
        deduped.append(c)

    # Rank
    ranked = sorted(deduped, key=score, reverse=True)
    top = [c for c in ranked if score(c) > 0][:TARGET_COUNT]

    today = date.today().isoformat()
    out = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "for_date": today,
        "instructions": (
            "Open each permalink on your phone. Spend 5-10 sec reading the "
            "caption + first comments. If it's actually a fit for the GHP "
            "audience: like it, optionally leave ONE genuine comment that "
            "references the post's actual content (no template). Skip "
            "anything that smells like a brand/bot/giveaway. Target time: 2 min."
        ),
        "targets": [
            {
                "rank": i + 1,
                "score": score(c),
                "hashtag": c.get("__hashtag"),
                "permalink": c.get("permalink"),
                "likes": c.get("like_count"),
                "comments": c.get("comments_count"),
                "timestamp": c.get("timestamp"),
                "caption_preview": (c.get("caption") or "")[:140],
            }
            for i, c in enumerate(top)
        ],
    }

    out_file = OUTPUT_DIR / f"engagement_targets_{today}.json"
    out_file.write_text(json.dumps(out, indent=2))
    log(f"Wrote {out_file} ({len(top)} targets)")

    # Also write a "latest" symlink-style copy for the phone link
    latest = OUTPUT_DIR / "engagement_targets_latest.json"
    latest.write_text(json.dumps(out, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
