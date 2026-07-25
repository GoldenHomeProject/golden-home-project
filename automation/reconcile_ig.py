#!/usr/bin/env python3
"""One-off reconcile: record the 6 IG posts that published but were never written back.

Cause: instagram-poster.yml staged its state with
    git add social/post_queue.json social/posted_archive.json social/failed_posts.json
and `git add` aborts the WHOLE add when any pathspec matches nothing. failed_posts.json
does not exist, so nothing was ever staged -> no commit -> the queue never advanced ->
the same reel (reel_2026-06-16_002) was republished to Instagram every night from
2026-07-19 through 2026-07-24 while every workflow run reported success.

The workflow bug is fixed separately. This repairs the state so the next run picks the
NEXT reel instead of publishing the same one a seventh time.

media_id/timestamp pairs below were read out of the GitHub Actions run logs.
"""
import json
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
QUEUE = ROOT / "social" / "post_queue.json"
ARCHIVE = ROOT / "social" / "posted_archive.json"

NAME = "reel_2026-06-16_002"
MISSED = [
    ("18095595215019449", "2026-07-20T03:28:10Z"),
    ("18063373211740305", "2026-07-20T23:05:55Z"),
    ("18110992469058210", "2026-07-21T23:03:31Z"),
    ("18099472732957681", "2026-07-22T23:10:13Z"),
    ("18130778470554791", "2026-07-23T23:03:37Z"),
    ("18122603191697557", "2026-07-24T23:08:39Z"),
]

for p in (QUEUE, ARCHIVE):
    shutil.copy2(p, p.with_suffix(p.suffix + ".bak-20260725"))

queue = json.loads(QUEUE.read_text())
archive = json.loads(ARCHIVE.read_text())
have = {x.get("media_id") for x in archive}

item = next((i for i in queue if i.get("name") == NAME), None)
if item is None:
    raise SystemExit(f"queue item {NAME} not found — aborting, nothing written")

added = 0
for media_id, ts in MISSED:
    if media_id in have:
        continue
    archive.append({
        "media_id": media_id,
        "posted_at": ts,
        "name": NAME,
        "media_type": item.get("media_type", "REELS"),
        "caption": item.get("caption", ""),
        "video_url": item.get("video_url"),
        "note": "backfilled 2026-07-25 — published to IG but never committed "
                "(instagram-poster.yml git-add pathspec bug); duplicate repost",
    })
    added += 1

item["status"] = "posted"
item["posted_at"] = MISSED[-1][1]
item["posted_media_ids"] = [m for m, _ in MISSED]

QUEUE.write_text(json.dumps(queue, indent=2) + "\n")
ARCHIVE.write_text(json.dumps(archive, indent=2) + "\n")

nxt = next((i.get("name") for i in queue if i.get("status") == "ready"), None)
print(f"archive entries added: {added}  (archive now {len(archive)})")
print(f"{NAME} marked posted; next ready item = {nxt}")
