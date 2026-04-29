#!/usr/bin/env python3
"""
Golden Home Project — GitHub Actions Daily Poster
===================================================
Runs in GitHub Actions (cloud) at noon ET daily.
Reads pre-generated videos from the repo, posts to YouTube + IG.

No Claude API needed. Uses YouTube Data API v3 + Meta Graph API.

Usage:
  python3 github_daily_poster.py \\
    --yt-token /tmp/yt_token.json \\
    --meta-token /tmp/meta_tokens.json \\
    --associate-tag goldenhomep06-20
"""

import argparse
import json
import os
import sys
import time
import requests
from datetime import datetime, timedelta, timezone
from pathlib import Path

# ── Paths (relative to repo root in GitHub Actions checkout)
REPO_ROOT  = Path(__file__).parent.parent
VIDEOS_DIR = REPO_ROOT / "videos" / "transformation"
LOGS_DIR   = Path(__file__).parent / "logs"
LOGS_DIR.mkdir(exist_ok=True)

# Content calendar (April 2026)
APRIL_CALENDAR = [
    {"date": "2026-04-01", "title": "I Transformed My Cluttered Kitchen Counter For $47",
     "products": [{"asin": "B08BHBPQHZ", "name": "Airtight Canister Set (4-piece)", "price": "$18.99"},
                  {"asin": "B07WGWFCTS", "name": "Bamboo Utensil Holder", "price": "$12.99"},
                  {"asin": "B08CHWX4S1", "name": "Paper Towel Holder Stand", "price": "$8.99"},
                  {"asin": "B09NQTD6G8", "name": "Bamboo Cutting Board Organizer", "price": "$16.99"}]},
    {"date": "2026-04-02", "title": "I Used the Wrong Pantry Organizers for 3 Years",
     "products": [{"asin": "B07NQVHKX7", "name": "Pantry Organization Bins (10-pack)", "price": "$32.99"},
                  {"asin": "B08BNHBK9N", "name": "Stackable Can Organizer", "price": "$14.99"},
                  {"asin": "B07J5N6HWJ", "name": "Chalk Label Set (reusable)", "price": "$9.99"},
                  {"asin": "B09K3MQVXL", "name": "Turntable Lazy Susan (2-pack)", "price": "$16.99"}]},
    {"date": "2026-04-04", "title": "My Kitchen Looks Like a Magazine Now — $34 Total", "ig": True,
     "products": [{"asin": "B08S8FMWWP", "name": "Minimalist Soap Dispenser Set (3-piece)", "price": "$19.99"},
                  {"asin": "B07ZBQSV97", "name": "Ceramic Sponge Holder", "price": "$8.99"},
                  {"asin": "B09JQRJ8C4", "name": "Small Countertop Tray Organizer", "price": "$12.99"}]},
    {"date": "2026-04-05", "title": "Room by Room Ep 1: The Cabinet Nobody Looks In",
     "products": [{"asin": "B08B3NWK45", "name": "Bamboo Drawer Organizer (expandable)", "price": "$21.99"},
                  {"asin": "B07D8CTHXF", "name": "Small Bins 2-pack", "price": "$11.99"},
                  {"asin": "B01N3LTFQO", "name": "DYMO Label Maker", "price": "$24.99"}]},
    {"date": "2026-04-07", "title": "I Finally Made My Bedroom Feel Like a Hotel",
     "products": [{"asin": "B07XVFBXWF", "name": "Linen Duvet Cover Set (Queen)", "price": "$54.99"},
                  {"asin": "B08JFV6MXQ", "name": "Throw Pillow Covers 4-pack", "price": "$19.99"},
                  {"asin": "B08KGWF5ZM", "name": "Bedside Tray Organizer", "price": "$16.99"}]},
    {"date": "2026-04-09", "title": "I Tested $25 vs $120 Air Purifiers. Here's the Truth.",
     "products": [{"asin": "B07VXKXR8H", "name": "LEVOIT Air Purifier (small room)", "price": "$24.99"},
                  {"asin": "B083PGLT37", "name": "LEVOIT Core 300 Air Purifier", "price": "$99.99"}]},
    {"date": "2026-04-11", "title": "My Nightstand Was a Disaster. $28 Fixed It.", "ig": True,
     "products": [{"asin": "B09G9FKWG3", "name": "Bedside Charging Station (3-port)", "price": "$19.99"},
                  {"asin": "B07WH4KBQB", "name": "Bamboo Bedside Tray", "price": "$14.99"}]},
    {"date": "2026-04-12", "title": "Room by Room Ep 2: The Junk Drawer Doesn't Have to Exist",
     "products": [{"asin": "B08B3NWK45", "name": "Interlocking Drawer Organizer Set", "price": "$18.99"},
                  {"asin": "B07Y9BKMYF", "name": "Cable Management Box", "price": "$19.99"}]},
    {"date": "2026-04-14", "title": "My Bathroom Went From Rental to Spa for $52",
     "products": [{"asin": "B08CZHVQJ4", "name": "Bamboo Over-Toilet Storage Shelf", "price": "$32.99"},
                  {"asin": "B08S8FMWWP", "name": "Bathroom Accessories Set (4-piece)", "price": "$21.99"}]},
    {"date": "2026-04-16", "title": "The Shower Caddy I Wasted $40 On (And What I Use Now)",
     "products": [{"asin": "B08XZV1H87", "name": "Rust-Proof Corner Shower Shelf (adhesive)", "price": "$22.99"}]},
    {"date": "2026-04-18", "title": "I Made My Living Room Look Twice as Expensive for $67", "ig": True,
     "products": [{"asin": "B09NXGKK3V", "name": "Waffle Knit Throw Blanket", "price": "$24.99"},
                  {"asin": "B08JFV6MXQ", "name": "Velvet Throw Pillow Covers (2-pack)", "price": "$18.99"},
                  {"asin": "B08RNX6Y8D", "name": "Faux Olive Tree with Ceramic Pot", "price": "$28.99"}]},
    {"date": "2026-04-19", "title": "Room by Room Ep 3: My Bathroom Cabinet Is Now Usable",
     "products": [{"asin": "B08CW3M5P4", "name": "Under-Sink Organizer with Adjustable Shelf", "price": "$19.99"},
                  {"asin": "B07D8CTHXF", "name": "Bathroom Storage Bins 3-pack", "price": "$14.99"}]},
    {"date": "2026-04-21", "title": "I Optimized My Morning Routine With 3 Amazon Products",
     "products": [{"asin": "B09N8P9H9K", "name": "Wall-Mounted Key and Phone Holder", "price": "$14.99"},
                  {"asin": "B07NNR4LX4", "name": "Handheld Electric Milk Frother", "price": "$8.99"},
                  {"asin": "B09JQRJ8C4", "name": "Entryway Catch-All Tray Organizer", "price": "$16.99"}]},
    {"date": "2026-04-23", "title": "I Tried Every Desk Organizer Style. This One Won.",
     "products": [{"asin": "B07WLGDRQ5", "name": "Bamboo Modular Desk Organizer Set", "price": "$34.99"}]},
    {"date": "2026-04-25", "title": "My Desk Setup Went From Chaos to Clean in 30 Minutes", "ig": True,
     "products": [{"asin": "B07Y9BKMYF", "name": "Cable Management Box (large)", "price": "$19.99"},
                  {"asin": "B09FBQR8XL", "name": "Monitor Stand with Storage Drawer", "price": "$39.99"},
                  {"asin": "B08F4YK8B7", "name": "Desktop Catch-All Organizer Tray", "price": "$14.99"}]},
    {"date": "2026-04-26", "title": "Room by Room Ep 4: The Bedroom Closet That Finally Makes Sense",
     "products": [{"asin": "B07FFXVDXG", "name": "Velvet Non-Slip Hangers (50-pack)", "price": "$19.99"},
                  {"asin": "B07X5JQPZM", "name": "Closet Shelf Dividers (6-pack)", "price": "$14.99"},
                  {"asin": "B08DC11C79", "name": "Hanging Closet Accessory Organizer", "price": "$16.99"}]},
    # ── Extension: 2026-04-27 → 2026-05-10. Reuses trans_001..trans_014 with
    # fresh hooks, products locked to verified-alive ASINs from the DM registry
    # (LINK / PILLOW / COVER / KETTLE / NIGHTLIGHT / SPONGE / STRIP / VACUUM /
    # PASTE / ROLLER) so every post drives the comment-to-DM funnel. After this
    # window, the cloud Content Engine + Reel Producer should be refilling
    # social/post_queue.json and the poster should switch to consuming that.
    {"date": "2026-04-27", "title": "The Under-Sink Cabinet I Avoided For 4 Years — $32 Fixed It",
     "video": 1,
     "products": [{"asin": "B01M0TS64K", "name": "Simple Houseware 2-Tier Sliding Basket Organizer", "price": "$31.99"}]},
    {"date": "2026-04-28", "title": "I Stopped Sleeping Wrong After I Bought This Pillow", "ig": True,
     "video": 2,
     "products": [{"asin": "B07YL7VD32", "name": "Eli & Elm Side Sleeper Pillow", "price": "$99.00"}]},
    # 2026-04-29: First DM-funnel reel using the new template engine + manual
    # render pipeline (Pexels b-roll + Amazon product shots + edge-tts + ffmpeg).
    # ig=True so it ships to IG today (not just Saturday). caption_override
    # carries the "Comment LINK" CTA so the funnel actually fires.
    {"date": "2026-04-29",
     "title": "I Had Four Years Of Bottles Falling On My Feet Every Morning",
     "ig": True,
     "video_file": "reel_2026-04-29_LINK.mp4",
     "caption_override": (
         "I had four years of bottles falling on my feet every morning.\n\n"
         "The cabinet under the kitchen sink was the place things went to die. "
         "Sponges, dish soap, an entire bottle of expensive olive oil I forgot I owned. "
         "Every morning I reached for paper towels and knocked over six things.\n\n"
         "I got a Simple Houseware 2-tier sliding basket — chrome wire, holds 18 lbs per shelf, "
         "and the front rack slides out independently of the back.\n\n"
         "Now I see everything. Sliding the front out doesn't disturb the back row. "
         "Haven't dropped a bottle in three weeks.\n\n"
         "Comment LINK and I'll DM you the link.\n"
         "Amazon affiliate — I earn a small commission at no extra cost to you.\n\n"
         "#amazonhomefinds #kitchenorganization #smallspacesolutions #undersinkstorage"
     ),
     "products": [{"asin": "B01M0TS64K", "name": "Simple Houseware 2-Tier Sliding Basket Organizer", "price": "$31.99"}]},
    {"date": "2026-04-30", "title": "I Replaced My Plastic Kettle After Reading This",
     "video": 4,
     "products": [{"asin": "B08PP48979", "name": "Cosori Electric Kettle (no plastic contact)", "price": "$39.99"}]},
    {"date": "2026-05-01", "title": "The Hallway Light That Turns Itself On — Saved Our Toes",
     "video": 5,
     "products": [{"asin": "B08RRRX5P5", "name": "LED Motion Sensor Plug-In Night Light", "price": "$12.99"}]},
    {"date": "2026-05-02", "title": "I Tested Every Sponge. Only One Survived.", "ig": True,
     "video": 6,
     "products": [{"asin": "B07ZL2BFMP", "name": "Scrub Daddy Sponge", "price": "$4.49"}]},
    {"date": "2026-05-03", "title": "These LED Strips Made My Bedroom Feel Like a Hotel Suite",
     "video": 7,
     "products": [{"asin": "B099S9DXT7", "name": "Govee RGBIC LED Strip Lights (32.8ft)", "price": "$39.99"}]},
    {"date": "2026-05-04", "title": "Freezer Burn Cost Me $400 Last Year. Not Anymore.",
     "video": 8,
     "products": [{"asin": "B099NTSWD9", "name": "FoodSaver VS2150 Vacuum Sealing System", "price": "$129.99"}]},
    {"date": "2026-05-05", "title": "The $5 Paste That Cleaned My Stovetop in 30 Seconds",
     "video": 9,
     "products": [{"asin": "B00DU5SRIY", "name": "Stardrops The Pink Stuff Cleaning Paste", "price": "$5.97"}]},
    {"date": "2026-05-06", "title": "Pet Hair Was Everywhere — One Roller Fixed It", "ig": True,
     "video": 10,
     "products": [{"asin": "B00BAGTNAQ", "name": "ChomChom Pet Hair Roller", "price": "$24.95"}]},
    {"date": "2026-05-07", "title": "The Under-Sink Reorg That Doubled My Storage",
     "video": 11,
     "products": [{"asin": "B01M0TS64K", "name": "Simple Houseware 2-Tier Sliding Basket Organizer", "price": "$31.99"}]},
    {"date": "2026-05-08", "title": "Side Sleepers: This Is The Pillow That Fixed My Neck",
     "video": 12,
     "products": [{"asin": "B07YL7VD32", "name": "Eli & Elm Side Sleeper Pillow", "price": "$99.00"}]},
    {"date": "2026-05-09", "title": "Why Pet Owners Are Ditching Their Old Sofa Covers", "ig": True,
     "video": 13,
     "products": [{"asin": "B0B4SPP3ZN", "name": "Paulato Stretch Sofa Cover (waterproof)", "price": "$39.99"}]},
    {"date": "2026-05-10", "title": "The Kitchen Swap I Should've Made Years Ago",
     "video": 14,
     "products": [{"asin": "B08PP48979", "name": "Cosori Electric Kettle (no plastic contact)", "price": "$39.99"}]},
]

PAGES_BASE = "https://goldenhomeproject.com/videos/transformation"
FB_PAGE_ID = "973754055831729"


def amazon(asin, tag):
    return f"https://www.amazon.com/dp/{asin}?tag={tag}"


def today_str():
    return datetime.now().strftime("%Y-%m-%d")


def refresh_yt_token(token_path):
    with open(token_path) as f:
        t = json.load(f)
    required = {"token_uri", "client_id", "client_secret", "refresh_token"}
    missing = required - t.keys()
    if missing:
        raise RuntimeError(f"YT token JSON missing keys: {missing}")
    resp = requests.post(t["token_uri"], data={
        "client_id": t["client_id"], "client_secret": t["client_secret"],
        "refresh_token": t["refresh_token"], "grant_type": "refresh_token",
    }, timeout=30)
    result = resp.json()
    if "access_token" in result:
        t["token"] = result["access_token"]
        t["expiry"] = (datetime.now(timezone.utc) + timedelta(seconds=result.get("expires_in", 3600))).isoformat()
        with open(token_path, "w") as f:
            json.dump(t, f, indent=2)
        return t
    raise RuntimeError(f"Token refresh failed: {result}")


def build_description(title, products, tag):
    lines = [title, "", "🔥 SHOP THESE PRODUCTS:"]
    for i, p in enumerate(products):
        lines.append(f"#{i+1} {p['name']} — {p['price']}")
        lines.append(f"   ➡️ {amazon(p['asin'], tag)}")
    lines += [
        "", "Everything is linked above. Ships fast from Amazon.",
        "🏠 More home finds: goldenhomeproject.com",
        "👉 Follow: @goldenhomeproject",
        "", "⚠️ As an Amazon Associate I earn from qualifying purchases.",
        "", "#amazonfinds #homedecor #homeorganization #roomtransformation #shorts",
    ]
    return "\n".join(lines)


def build_pin_comment(products, tag):
    lines = ["📌 SHOP ALL PRODUCTS — Amazon links:\n"]
    symbols = "①②③④⑤"
    for i, p in enumerate(products[:5]):
        lines.append(f"{symbols[i]} {p['name']} — {p['price']}")
        lines.append(f"   🛒 {amazon(p['asin'], tag)}")
    lines += ["", "🏠 goldenhomeproject.com",
              "⚠️ Amazon Associate — qualifying purchases earn commission."]
    return "\n".join(lines)


def post_yt_short(video_path, title, description, pin_comment, yt_token):
    token = yt_token.get("token") or yt_token.get("access_token")
    headers = {"Authorization": f"Bearer {token}"}

    metadata = {
        "snippet": {
            "title": title[:100],
            "description": description,
            "tags": ["amazonfinds", "homedecor", "homeorganization", "roomtransformation", "shorts"],
            "categoryId": "26",
        },
        "status": {"privacyStatus": "public", "selfDeclaredMadeForKids": False},
    }
    init = requests.post(
        "https://www.googleapis.com/upload/youtube/v3/videos?uploadType=resumable&part=snippet,status",
        headers={**headers, "Content-Type": "application/json", "X-Upload-Content-Type": "video/mp4"},
        json=metadata, timeout=30,
    )
    if init.status_code != 200:
        print(f"  [YT] Init failed: {init.status_code} {init.text[:200]}")
        return None

    upload_url = init.headers["Location"]
    file_size = os.path.getsize(video_path)
    with open(video_path, "rb") as f:
        upload = requests.put(
            upload_url, data=f,
            headers={**headers, "Content-Type": "video/mp4", "Content-Length": str(file_size)},
            timeout=300,
        )

    result = upload.json()
    if "id" not in result:
        print(f"  [YT] Upload failed: {result}")
        return None

    video_id = result["id"]
    print(f"  [YT] ✓ https://youtube.com/shorts/{video_id}")

    time.sleep(8)
    cr = requests.post(
        "https://www.googleapis.com/youtube/v3/commentThreads?part=snippet",
        headers={**headers, "Content-Type": "application/json"},
        json={"snippet": {"videoId": video_id,
                          "topLevelComment": {"snippet": {"textOriginal": pin_comment}}}},
        timeout=30,
    )
    if "id" in cr.json():
        print(f"  [YT Comment] ✓ Affiliate links pinned")
    return video_id


def post_fb_page_video(video_file, title, description, meta_tokens):
    """Post the daily reel as a video to the FB Page via Graph API.
    Uses file_url since GitHub Pages already hosts the .mp4 publicly.
    `video_file` is the bare filename (e.g. trans_003.mp4 or reel_2026-04-29_LINK.mp4)."""
    token = meta_tokens["page_access_token"]
    video_url = f"{PAGES_BASE}/{video_file}"
    api = "https://graph.facebook.com/v21.0"

    resp = requests.post(f"{api}/{FB_PAGE_ID}/videos", data={
        "file_url": video_url,
        "title": title[:255],
        "description": description,
        "access_token": token,
    }, timeout=120)
    result = resp.json()
    if "id" in result:
        post_id = result["id"]
        print(f"  [FB] ✓ Video published: https://facebook.com/{post_id}")
        return post_id
    print(f"  [FB] ✗ {result}")
    return None


def post_ig_reel(video_file, caption, meta_tokens):
    token = meta_tokens["page_access_token"]
    ig_id = meta_tokens["ig_business_account_id"]
    video_url = f"{PAGES_BASE}/{video_file}"
    api = "https://graph.facebook.com/v19.0"

    resp = requests.post(f"{api}/{ig_id}/media", data={
        "media_type": "REELS", "video_url": video_url,
        "caption": caption, "access_token": token,
    }, timeout=30)
    container = resp.json()
    if "id" not in container:
        print(f"  [IG] Container failed: {container}")
        return None

    status_code = None
    for _ in range(18):
        time.sleep(10)
        s = requests.get(f"{api}/{container['id']}",
                         params={"fields": "status_code", "access_token": token},
                         timeout=15).json()
        status_code = s.get("status_code")
        if status_code == "FINISHED":
            break
        if status_code == "ERROR":
            print(f"  [IG] Container processing failed: {s}")
            return None

    if status_code != "FINISHED":
        print(f"  [IG] Container never finished (last status: {status_code})")
        return None

    pub = requests.post(f"{api}/{ig_id}/media_publish",
                        data={"creation_id": container["id"], "access_token": token},
                        timeout=30)
    result = pub.json()
    if "id" in result:
        print(f"  [IG] ✓ Reel published: {result['id']}")
        return result["id"]
    print(f"  [IG] ✗ {result}")
    return None


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--yt-token", required=True)
    parser.add_argument("--meta-token", required=True)
    parser.add_argument("--associate-tag", default="goldenhomep06-20")
    parser.add_argument("--date", default=None, help="Override date (YYYY-MM-DD)")
    args = parser.parse_args()

    today = args.date or today_str()
    is_saturday = datetime.strptime(today, "%Y-%m-%d").weekday() == 5

    print(f"\n{'='*60}")
    print(f"GHP DAILY POSTER (GitHub Actions) — {today}")
    print(f"{'='*60}")

    # Find today's entry
    entry = next((e for e in APRIL_CALENDAR if e["date"] == today), None)
    if not entry:
        # Loud, machine-visible warning so gaps in the content calendar don't hide
        # behind a silent green GitHub Actions run.
        print(f"::warning title=No content scheduled::APRIL_CALENDAR has no entry for {today}. "
              f"Calendar ends {APRIL_CALENDAR[-1]['date']}. Add new entries to extend posting.")
        print(f"  No content scheduled for {today}. Done.")
        # Record the gap so engagement-monitor / humans can see the miss in repo.
        log_path = LOGS_DIR / f"gh_post_{today}.json"
        log_path.write_text(json.dumps({
            "date": today,
            "status": "no_content_scheduled",
            "calendar_last_date": APRIL_CALENDAR[-1]["date"],
        }, indent=2))
        sys.exit(0)

    # Video resolution priority:
    #   1. explicit `video_file` key (any filename, e.g. reel_YYYY-MM-DD_KW.mp4)
    #   2. explicit `video:` integer (recycle existing trans_NNN.mp4)
    #   3. fall back to 1-based position in calendar (legacy mapping)
    if entry.get("video_file"):
        video_file = entry["video_file"]
    else:
        video_index = entry.get("video") or (APRIL_CALENDAR.index(entry) + 1)
        video_file = f"trans_{video_index:03d}.mp4"
    video_path = VIDEOS_DIR / video_file

    title    = entry["title"]
    products = entry.get("products", [])
    tag      = args.associate_tag

    print(f"  Title:   {title}")
    print(f"  Video:   {video_file}")
    print(f"  Products: {len(products)}")

    if not video_path.exists():
        print(f"  ERROR: {video_path} not found. Commit videos to repo first.")
        sys.exit(1)

    yt_token     = refresh_yt_token(args.yt_token)
    with open(args.meta_token) as f:
        meta_tokens = json.load(f)

    # caption_override lets DM-funnel reels ship their hand-crafted captions
    # (with "Comment KEYWORD..." CTA) instead of the legacy product-list description.
    caption_override = entry.get("caption_override")
    description = caption_override or build_description(title, products, tag)
    pin_comment = build_pin_comment(products, tag)
    yt_title    = f"{title} #shorts #amazonfinds #homedecor"

    print(f"\n  Uploading to YouTube...")
    yt_id = post_yt_short(str(video_path), yt_title, description, pin_comment, yt_token)

    # IG ships when entry opts in (`ig: True`). Saturday weekly cadence is the
    # default for the legacy calendar; DM-funnel reels override and post any day.
    ig_id = None
    if entry.get("ig") and (is_saturday or caption_override):
        print(f"\n  Posting to Instagram...")
        if caption_override:
            ig_caption = caption_override
        else:
            ig_caption = (
                f"{title} 🏠✨\n\n"
                + "\n".join(f"{i+1}️⃣ {p['name']} — {p['price']}" for i, p in enumerate(products))
                + "\n\nAll links in bio — goldenhomeproject.com 🔗\n\n"
                + "#amazonfinds #homedecor #homeorganization #roomtransformation"
            )
        ig_id = post_ig_reel(video_file, ig_caption, meta_tokens)

    print(f"\n  Posting to Facebook Page...")
    fb_id = post_fb_page_video(video_file, title, description, meta_tokens)

    log = {"date": today, "title": title, "youtube": yt_id, "instagram": ig_id,
           "facebook": fb_id, "video": video_file}
    log_path = LOGS_DIR / f"gh_post_{today}.json"
    with open(log_path, "w") as f:
        json.dump(log, f, indent=2)

    print(f"\n  Log saved: {log_path}")
    print(f"  YouTube: {'✓ ' + yt_id if yt_id else '✗ failed'}")
    print(f"  Instagram: {'✓' if ig_id else 'skipped' if not is_saturday else '✗ failed'}")
    print(f"  Facebook: {'✓ ' + fb_id if fb_id else '✗ failed'}")


if __name__ == "__main__":
    main()
