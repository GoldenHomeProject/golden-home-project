#!/usr/bin/env python3
"""Create idea-style Pinterest pins that point to a ROUNDUP blog post (not a
single product). This is the teardown mechanic (2026-06-18): winning home-org
accounts pin IDEAS/OUTCOMES -> roundup posts, not brand-name single products.

Reuses pinterest_pipeline's Pexels fetch + pin compositor so the pins match our
look. Appends to the live queue; the poster (2/day) drains them. Each gets a
unique synthetic asin so the dedupe ledger treats them as distinct.
"""
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, "automation")
import pinterest_pipeline as pp  # noqa: E402

ROUNDUP_URL = ("https://goldenhomeproject.com/blog/posts/"
               "2026-06-18-best-kitchen-organizers-cabinet-under-sink-pantry.html")

PINS = [
    {"id": "ru-kitchen-cabinets", "board": "Kitchen Organization Ideas",
     "hook": "Organize Every Cabinet", "pexels": "organized kitchen cabinet interior",
     "title": "7 Kitchen Cabinet Organizing Ideas That Actually Work",
     "desc": "Tired of digging through deep cabinets? These kitchen cabinet and pantry "
             "organizers actually earn their space - real picks, real prices, compared. "
             "#kitchenorganization #homeorganization #amazonfinds"},
    {"id": "ru-kitchen-small", "board": "Home Organization Finds",
     "hook": "Small Kitchen Wins", "pexels": "tidy small kitchen counter clean",
     "title": "Small Kitchen Storage Ideas Under $50 That Actually Fit",
     "desc": "Small kitchen? These under-$50 storage finds reclaim cabinet, drawer and "
             "pantry space without a remodel. Budget to splurge, compared side by side. "
             "#smallkitchen #kitchenstorage #organizationideas"},
    {"id": "ru-kitchen-undersink", "board": "Under-Sink Organization",
     "hook": "Tame the Under-Sink Mess", "pexels": "under sink cabinet organized storage",
     "title": "Under-Sink Organization Ideas to Reclaim That Dead Space",
     "desc": "The under-sink cabinet is the most wasted space in the kitchen. These "
             "organizers work around the pipes and turn it into real storage. "
             "#undersinkorganization #kitchenhacks #homeorganizing"},
]


def main() -> int:
    queue = pp.load_json(pp.QUEUE_PATH, [])
    have = {p.get("asin") for p in queue}
    date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    made = 0
    for spec in PINS:
        asin = spec["id"].upper()
        if asin in have:
            print(f"  [skip] {asin} already queued")
            continue
        bg = pp.PINS_DIR / f"bg-roundup-{spec['id']}.jpg"
        bg_ok = pp.fetch_pexels(spec["pexels"], bg)
        img = pp.compose_pin(bg if bg_ok else None, spec["hook"],
                             spec["title"][:60], "")
        img_path = pp.PINS_DIR / f"pin-roundup-{spec['id']}.png"
        img.save(img_path, "PNG", optimize=True)
        queue.append({
            "id": f"pin-roundup-{spec['id']}",
            "asin": asin,
            "board": spec["board"],
            "title": spec["title"][:100],
            "description": spec["desc"][:500],
            "link": ROUNDUP_URL,
            "image_path": str(img_path.relative_to(pp.ROOT)),
            "image_url": "",
            "queued_at": date_str,
            "source": "roundup_pins",
            "posted": False,
        })
        made += 1
        print(f"  [pin] {asin} board={spec['board']!r} bg={'pexels' if bg_ok else 'gradient'} -> roundup")
    pp.QUEUE_PATH.write_text(json.dumps(queue, indent=2))
    print(f"[roundup-pins] added {made}; queue now {len(queue)} total")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
