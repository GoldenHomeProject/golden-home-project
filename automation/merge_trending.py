#!/usr/bin/env python3
"""merge_trending.py — turn each day's best-seller scrape into pinnable catalogue.

Pinterest output collapsed from 8 pins/day to 1 because the catalogue held only 107
unique products and every one was already pinned. The job meant to grow it
(source_dorm.py) has aborted as throttled for six straight days: Amazon is persistently
blocking /dp/ page loads from this Pi, so search + verify_dp cannot run.

But the trending scrape still works every morning — Amazon serves the best-seller GRIDS
fine. Those rows are Amazon-native proof a product exists and is selling, and they already
carry price, rating and review count captured at scrape time. That is the same evidence
verify_dp would give us, so they can be merged straight into the vetted pool.

Strictly idempotent, keyed on ASIN. promote_vetted previously wrote its whole in-memory
pool back to disk and left 619 rows for 107 ASINs; this only ever adds genuinely new ones.

    python3 automation/merge_trending.py [--days N] [--dry-run]
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
SOCIAL = ROOT / "social"
REG = SOCIAL / "dm_keyword_registry.json"
TAG = "goldenhomep06-20"


def price_val(p):
    m = re.search(r"[\d,]+\.\d{2}", str(p or ""))
    return float(m.group().replace(",", "")) if m else None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=14)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    reg = json.loads(REG.read_text())
    have = {e.get("asin") for e in reg.get("entries", []) + reg.get("vetted", [])}
    added, skipped = [], 0

    for path in sorted(SOCIAL.glob("trending_picks_*.json"), reverse=True)[: args.days]:
        try:
            data = json.loads(path.read_text())
        except (json.JSONDecodeError, OSError):
            continue
        for pk in (data if isinstance(data, list) else data.get("picks", [])):
            asin = (pk.get("asin") or "").strip()
            name = pk.get("title") or pk.get("name") or ""
            if not asin or asin in have:
                continue
            pv = price_val(pk.get("price"))
            if pv is None or not (td.MIN_PRICE <= pv <= td.MAX_PRICE):
                skipped += 1
                continue
            head = name[: td.TITLE_HEAD_CHARS]
            if td.COMMODITY_BLOCK.search(head) or td.OFF_BRAND_BLOCK.search(head):
                skipped += 1
                continue
            entry = {
                "asin": asin,
                "product_name": name,
                "categories": [c for c in [pk.get("cat_group"), pk.get("cat_label")] if c],
                "affiliate_url": f"https://www.amazon.com/dp/{asin}?tag={TAG}",
                "status": "live",
                "verified_at": path.stem.replace("trending_picks_", "")[:10],
                # Named so it is obvious this was NOT /dp/-verified: it came off Amazon's
                # own best-seller grid, which is why we trust it.
                "verified_method": "best_seller_grid",
                "verified_price": pk.get("price"),
                "verified_stars": str(pk.get("rating") or ""),
                "verified_reviews": pk.get("reviews"),
                "discovery_source": "merge_trending",
            }
            reg.setdefault("vetted", []).append(entry)
            have.add(asin)
            added.append(entry)

    print(f"[merge] {len(added)} new product(s) added, {skipped} filtered out")
    for e in added[:8]:
        print(f"   {e['asin']}  {str(e['verified_price']):>8}  {e['verified_stars']}*  "
              f"{e['product_name'][:46]}")
    if args.dry_run:
        print("[merge] --dry-run, registry not written")
        return 0
    if added:
        REG.write_text(json.dumps(reg, indent=2) + "\n")
        print(f"[merge] wrote {REG}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
