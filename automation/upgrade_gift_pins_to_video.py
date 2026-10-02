#!/usr/bin/env python3
"""upgrade_gift_pins_to_video.py — give already-queued, unposted gift pins a video.

Gift pins queued on 2026-10-01/02 were built before video_pin.py existed. This builds a
video for each pending one and points the queue entry at it, keeping the still PNG as
the fallback. Pins with no clean clip are left exactly as they were.

    python3 automation/upgrade_gift_pins_to_video.py [--max N]
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "automation"))
import pinterest_pipeline as pp  # noqa: E402
from video_pin import make_video_pin, queries_for  # noqa: E402

QUEUE = ROOT / "social" / "pinterest_queue.json"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--max", type=int, default=20)
    a = ap.parse_args()
    reg = json.loads((ROOT / "social" / "dm_keyword_registry.json").read_text())
    by_asin = {e.get("asin"): e for e in pp.registry_entries(reg)}
    done = 0
    for pin in json.loads(QUEUE.read_text()):
        if done >= a.max:
            break
        if pin.get("posted") or pin.get("media") == "video" or not str(pin.get("id", "")).endswith("-gift"):
            continue
        e = by_asin.get(pin.get("asin")) or {}
        name = e.get("product_name") or pin.get("title", "")
        subject = pp._strip_brand(pp._short_name(name, limit=60))
        _, board_q = pp.board_for(e) if e else ("", "")
        vq = [q for q in dict.fromkeys(queries_for(name) + [f"{pp._product_photo_query(name, board_q)} close up"]) if q]
        mp4 = pp.PINS_DIR / "video" / f"{pin['id']}.mp4"
        print(f"[upgrade] {pin['id']} — {subject}")
        # Search phrase + clean product name. The pin title ran long and got cut mid-phrase
        # ("…Pillowcase Set Reduces"); the price already has its own chip on the video.
        headline = f"{pp._search_phrase(pin['board']).title()}: {pp._strip_brand(pp._short_name(name, limit=40))}"
        if not make_video_pin(vq, subject, headline, pp._short_name(name),
                              str(e.get("verified_price") or ""), pp._search_phrase(pin["board"]), mp4):
            print("  no clean clip — keeping the still")
            continue
        # re-read and patch only this entry, so a concurrent writer is not clobbered
        q = json.loads(QUEUE.read_text())
        for p in q:
            if p.get("id") == pin["id"] and not p.get("posted"):
                p["fallback_image_path"] = p.get("image_path")
                p["image_path"] = str(mp4.relative_to(ROOT))
                p["media"] = "video"
        QUEUE.write_text(json.dumps(q, indent=2))
        done += 1
    print(f"[upgrade] {done} gift pin(s) now video")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
