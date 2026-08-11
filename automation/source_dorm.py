#!/usr/bin/env python3
"""source_dorm.py — add REAL, verified dorm products to the vetted pool.

The dorm hub could only find 3 qualifying products because the vetted pool was built for
general home organization. Amazon has no dorm best-seller node we can read, so we source
the way a shopper would: search the terms students actually use, take the top organic
result, and verify the listing renders before trusting it.

Paced and canary-guarded because Amazon throttles /s?k= hardest — and a throttled run
must never be mistaken for "no products found".
"""
from __future__ import annotations

import json
import random
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from asin_discoverer import REGISTRY_PATH, UA, search_amazon, verify_dp  # noqa: E402

CANARY = "B00FLYWNYQ"
QUERIES = [
    "dorm room organizer",
    "college dorm storage bins",
    "dorm desk organizer",
    "under bed storage dorm",
    "dorm closet organizer hanging",
    "shower caddy college dorm",
]
MIN_PRICE, MAX_PRICE, MIN_STARS, MIN_REVIEWS = 5.0, 35.0, 4.5, 500


def val(pat, s):
    m = re.search(pat, str(s or ""))
    return m.group() if m else None


def main() -> int:
    from playwright.sync_api import sync_playwright
    reg = json.loads(REGISTRY_PATH.read_text())
    have = {e.get("asin") for e in reg.get("entries", []) + reg.get("vetted", [])}
    added = []

    with sync_playwright() as p:
        b = p.chromium.launch(headless=True,
                              args=["--disable-blink-features=AutomationControlled", "--no-sandbox"])
        ctx = b.new_context(user_agent=UA, viewport={"width": 1280, "height": 900}, locale="en-US")
        page = ctx.new_page()

        if verify_dp(page, CANARY) is None:
            print("[dorm-src] ABORT: control listing will not render — we are throttled.")
            b.close()
            return 1

        for q in QUERIES:
            time.sleep(random.uniform(6, 12))
            hit = search_amazon(page, q)
            if not hit or not hit.get("asin"):
                print(f"  [miss] {q}")
                continue
            asin = hit["asin"]
            if asin in have:
                print(f"  [dupe] {q} -> {asin}")
                continue
            info = verify_dp(page, asin)
            if not info or not info.get("title"):
                print(f"  [unverified] {q} -> {asin}")
                continue
            price = info.get("price") or hit.get("price")
            pv = val(r"[\d,]+\.\d{2}", price)
            stars = info.get("stars") or hit.get("stars")
            reviews = info.get("reviews") or hit.get("reviews") or 0
            pvf = float(pv.replace(",", "")) if pv else None
            if pvf is None or not (MIN_PRICE <= pvf <= MAX_PRICE):
                print(f"  [price] {asin} {price} outside range — {info['title'][:40]}")
                continue
            if stars and float(stars) < MIN_STARS:
                print(f"  [stars] {asin} {stars} — {info['title'][:40]}")
                continue
            if int(reviews or 0) < MIN_REVIEWS:
                print(f"  [thin]  {asin} {reviews} reviews — {info['title'][:40]}")
                continue
            entry = {
                "asin": asin,
                "product_name": info["title"],
                "categories": ["dorm", "college", "organization"],
                "affiliate_url": f"https://www.amazon.com/dp/{asin}?tag=goldenhomep06-20",
                "status": "live",
                "verified_at": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
                "verified_method": "source_dorm/search+dp",
                "verified_price": price,
                "verified_stars": str(stars or ""),
                "verified_reviews": int(reviews or 0),
                "discovery_source": "back_to_college_2026",
            }
            reg.setdefault("vetted", []).append(entry)
            have.add(asin)
            added.append(entry)
            print(f"  ADDED {asin}  {price:>8}  {stars}*  {int(reviews):>7} rev  {info['title'][:44]}")

        ctx.close()
        b.close()

    if added:
        REGISTRY_PATH.write_text(json.dumps(reg, indent=2) + "\n")
    print(f"\n[dorm-src] added {len(added)} verified dorm product(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
