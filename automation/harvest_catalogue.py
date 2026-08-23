#!/usr/bin/env python3
"""harvest_catalogue.py — grow the product catalogue from best-seller grids.

Pinterest fell from 8 pins/day to 1: the catalogue held 107 unique products and all of
them were already pinned. Two sources were supposed to prevent that and both stalled.

  * source_dorm.py needs Amazon search + /dp/ verification, and Amazon has been blocking
    /dp/ page loads from this Pi for six straight days (the canary catches it and aborts,
    which is correct — a throttled run must never be mistaken for "no products found").
  * merge_trending.py only sees the 6 products the daily hub rotation happens to pick,
    and those repeat heavily.

Amazon still serves best-seller GRIDS normally, and a grid row is Amazon-native proof the
product exists and is selling, with price/rating/review count attached. So harvest across
MANY category nodes rather than the six the hub rotation uses. Every product still has to
clear the same bar as everywhere else: $5-35, >=4.5 stars, real review depth, no
commodities, no off-brand items.

    python3 automation/harvest_catalogue.py [--dry-run] [--max-nodes N]
"""
from __future__ import annotations

import argparse
import json
import random
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import trending_daily as td  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
REG = ROOT / "social" / "dm_keyword_registry.json"
TAG = "goldenhomep06-20"

# Node IDs read off Amazon's own Best Sellers nav. Deliberately wider than the hub
# rotation so the catalogue keeps growing after the hub categories are exhausted.
NODES = [
    ("Storage & Organization", "home", "https://www.amazon.com/gp/bestsellers/home-garden/3610841/"),
    ("Kitchen & Dining",       "kitchen", "https://www.amazon.com/gp/bestsellers/home-garden/284507/"),
    ("Bath",                   "home", "https://www.amazon.com/gp/bestsellers/home-garden/1063236/"),
    ("Cleaning Supplies",      "home", "https://www.amazon.com/gp/bestsellers/home-garden/10802561/"),
    ("Home Décor",             "home", "https://www.amazon.com/gp/bestsellers/home-garden/1063278/"),
    ("Furniture",              "home", "https://www.amazon.com/gp/bestsellers/home-garden/1063306/"),
    ("Home & Kitchen",         "home", "https://www.amazon.com/gp/bestsellers/home-garden/"),
    ("Kitchen Storage",        "kitchen", "https://www.amazon.com/gp/bestsellers/kitchen/"),
]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--max-nodes", type=int, default=4)
    args = ap.parse_args()

    reg = json.loads(REG.read_text())
    have = {e.get("asin") for e in reg.get("entries", []) + reg.get("vetted", [])}
    before = len(have)

    # Rotate which nodes we hit so repeated runs explore different ground and we stay a
    # light visitor rather than hammering the same pages daily.
    nodes = NODES[:]
    random.shuffle(nodes)
    nodes = nodes[: args.max_nodes]
    print(f"[harvest] scraping {len(nodes)}: {', '.join(n[0] for n in nodes)}")

    raw = td.scrape_bestsellers(nodes)
    print(f"[harvest] {len(raw)} raw rows")
    qualified = td.qualify(raw)
    print(f"[harvest] {len(qualified)} passed the ${int(td.MIN_PRICE)}-${int(td.MAX_PRICE)} / "
          f"{td.MIN_RATING}star / {td.MIN_REVIEWS}+review bar")

    added = []
    for p in qualified:
        asin = p.get("asin")
        if not asin or asin in have:
            continue
        entry = {
            "asin": asin,
            "product_name": p.get("title") or "",
            "categories": [c for c in [p.get("cat_group"), p.get("cat_label")] if c],
            "affiliate_url": f"https://www.amazon.com/dp/{asin}?tag={TAG}",
            "status": "live",
            "verified_at": time.strftime("%Y-%m-%d"),
            "verified_method": "best_seller_grid",
            "verified_price": p.get("price"),
            "verified_stars": str(p.get("rating") or ""),
            "verified_reviews": p.get("reviews"),
            "discovery_source": "harvest_catalogue",
        }
        reg.setdefault("vetted", []).append(entry)
        have.add(asin)
        added.append(entry)

    print(f"[harvest] {len(added)} NEW product(s); catalogue {before} -> {len(have)}")
    for e in added[:10]:
        print(f"   {e['asin']}  {str(e['verified_price']):>8}  {e['verified_stars']}*  "
              f"{e['product_name'][:46]}")
    if args.dry_run:
        print("[harvest] --dry-run, registry not written")
        return 0
    if added:
        REG.write_text(json.dumps(reg, indent=2) + "\n")
        print(f"[harvest] wrote {REG}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
