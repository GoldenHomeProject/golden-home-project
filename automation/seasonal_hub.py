#!/usr/bin/env python3
"""seasonal_hub.py — build the dorm hub for the back-to-college window.

Why now (2026-08-11): the Associates account needs 3 qualifying sales by ~2026-09-17 or
it closes. SEO cannot deliver inside that window, and the storefront drew 6 clicks in 30
days. The one thing genuinely in our favour is timing: mid-August is peak dorm move-in,
our category IS dorm organization, and "dorm room essentials", "college dorm checklist",
"dorm organization ideas", "best dorm storage" and "dorm room must haves" are all
confirmed real Google queries.

Buyer intent is the thing we have been missing. A student furnishing a room in August is
about as close to purchase intent as this niche gets.

Products come from the VETTED pool (already verified live, price/rating recorded) rather
than a fresh scrape, so this cannot invent anything and does not depend on Amazon letting
us scrape today. Same bar as everywhere else: $5-35, >=4.5 stars, no commodities.

    python3 automation/seasonal_hub.py [--dry-run]
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import trending_daily as td  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
REGISTRY = ROOT / "social" / "dm_keyword_registry.json"

CATEGORY = "Dorm"
# Things that genuinely belong in a dorm room. Deliberately narrow: a student is not
# buying a patio set or a coat rack for a shared 12x15 room.
DORM_TERMS = re.compile(
    r"\b(dorm|college|shower caddy|closet organizer|hanging organizer|storage bin|"
    r"under bed|bed riser|desk organizer|drawer organizer|floating shelf|shelves|"
    r"hamper|shoe rack|hanger|command)\b", re.I)
# Weak generic words ("laundry", "hook", "cube") dragged in a hallway/kitchen runner rug
# on the first run. A dorm page is judged in one glance, so require a strong signal and
# keep the list narrow rather than padding it.


def type_key(title: str) -> str:
    """Coarse product type, so one page doesn't list two shower caddies."""
    t = title.lower()
    for k in ("shower caddy", "closet organizer", "storage bin", "floating shelf",
              "shelves", "drawer organizer", "desk organizer", "hamper", "shoe rack",
              "hanger", "command", "bed riser", "under bed", "squeegee", "rug",
              "extension cord", "desk lamp", "mattress", "hooks", "cart"):
        if k in t:
            return k
    return t[:18]


def price_val(p):
    m = re.search(r"[\d,]+\.\d{2}", str(p or ""))
    return float(m.group().replace(",", "")) if m else None


def stars_val(s):
    m = re.search(r"\d+(?:\.\d+)?", str(s or ""))
    return float(m.group()) if m else None


def reviews_val(r):
    if isinstance(r, int):
        return r
    m = re.search(r"[\d,]+", str(r or ""))
    return int(m.group().replace(",", "")) if m else 0


def pick_products(limit: int) -> list[dict]:
    reg = json.loads(REGISTRY.read_text())
    pool = [e for e in (reg.get("entries", []) + reg.get("vetted", []))
            if e.get("status") == "live"]
    out, seen = [], set()
    for e in pool:
        asin, name = e.get("asin"), (e.get("product_name") or "")
        cats = [c.lower() for c in (e.get("categories") or [])]
        # Products sourced by source_dorm.py carry a "dorm" category. Their titles often
        # don't say "dorm" at all (an extension cord, a Twin XL mattress pad, a desk lamp)
        # yet they're exactly what a move-in list needs, so trust the sourcing intent as
        # well as the title.
        is_dorm = ("dorm" in cats or "college" in cats) or bool(DORM_TERMS.search(name))
        if not asin or asin in seen or not is_dorm:
            continue
        pv, st = price_val(e.get("verified_price")), stars_val(e.get("verified_stars"))
        if pv is None or not (td.MIN_PRICE <= pv <= td.MAX_PRICE):
            continue
        if st is not None and st < td.MIN_RATING:
            continue
        head = name[:td.TITLE_HEAD_CHARS]
        if td.COMMODITY_BLOCK.search(head) or td.OFF_BRAND_BLOCK.search(head):
            continue
        tk = type_key(name)
        if tk in seen:
            continue          # already have this kind of thing on the page
        seen.add(asin)
        seen.add(tk)
        out.append({
            "asin": asin, "title": name, "price": e.get("verified_price"),
            "price_val": pv, "rating": st, "reviews": reviews_val(e.get("verified_reviews")),
            "cat_label": CATEGORY, "cat_group": "home",
        })
    # Cheapest first: impulse price points convert fastest, which is what a 30-day
    # deadline needs.
    out.sort(key=lambda p: (p["price_val"], -p["reviews"]))
    return out[:limit]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    td.EVERGREEN[CATEGORY] = ("best-dorm-room-essentials", "dorm room essentials")
    picks = pick_products(10)
    if len(picks) < 3:
        print(f"[dorm] only {len(picks)} qualifying products — not publishing a thin page")
        return 0

    today = datetime.now(timezone.utc).date()
    slug, html, record = td.build_post(picks, today, CATEGORY)
    print(f"[dorm] {len(picks)} picks for {slug}")
    for p in picks:
        print(f"   {p['asin']}  {str(p['price']):>8}  {str(p['rating']):>4}*  {p['title'][:52]}")
    if args.dry_run:
        print("[dorm] --dry-run, nothing written")
        return 0

    (td.BLOG_POSTS / f"{slug}.html").write_text(html)
    (td.PICKS_DIR / f"trending_picks_{today.isoformat()}_dorm.json").write_text(
        json.dumps(record, indent=2) + "\n")
    td.insert_index_card(slug, f"Dorm Room Essentials: {len(picks)} Picks Under ${int(td.MAX_PRICE)}",
                         "The cheap, high-rated organizers that actually fit a dorm room.",
                         today.isoformat())
    print(f"[dorm] wrote blog/posts/{slug}.html")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
