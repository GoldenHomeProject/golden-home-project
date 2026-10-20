#!/usr/bin/env python3
"""chart_scan.py — every morning, what is ACTUALLY selling in our categories right now.

Ian, 2026-10-20: "make sure you are posting high quality trending products, or great
products people would use and need". The only trend feed was trending_daily.py: ONE
category a day, 6 picks, and it deliberately skips anything featured before (right for a
blog page, wrong for pins, because it drops the steadiest best-sellers). On 10/20 only 4
of 36 pending pins were on a current chart.

This reads every category chart trending_daily knows plus Amazon's Home & Kitchen
Movers & Shakers (biggest sales-rank gains in 24h, i.e. what is taking off), keeps only
proven products ($5-35, 4.5+ stars, 5k+ reviews, genuinely in-category, no consumables
or health/beauty) and writes social/chart_now.json for the pin generator. 11 page loads
a day from the Pi's home connection, a few seconds apart.

Run (Pi):  xvfb-run -a ~/.ghp-trending/venv/bin/python automation/chart_scan.py
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "automation"))

from category_identity import in_category, off_niche_hit  # noqa: E402
from trending_daily import CATEGORY_ROTATION, qualify, scrape_bestsellers  # noqa: E402

OUT = ROOT / "social" / "chart_now.json"
MOVERS = ("Movers", "home", "https://www.amazon.com/gp/movers-and-shakers/home-garden/")
# Commodities that slip past trending_daily's 60-char head check ("13 Gallon Flextra
# Strength Tall Kitchen Drawstring..." is trash bags): pennies of commission, no pin appeal.
LOW_VALUE = re.compile(r"\b(trash|garbage|drawstring bags?|gallon .*bags?)\b", re.I)


def main() -> int:
    nodes = list(CATEGORY_ROTATION) + [MOVERS]
    items = scrape_bestsellers(nodes)
    keep = []
    for it in qualify(items):
        title, cat = it.get("title") or "", it.get("cat_label") or ""
        if off_niche_hit(title) or LOW_VALUE.search(title):
            continue
        if cat != "Movers" and not in_category(title, cat):
            continue
        keep.append({
            "asin": it["asin"], "name": title, "price": it.get("price"),
            "rating": it.get("rating"), "reviews": it.get("reviews"), "rank": it.get("rank"),
            "category": cat, "source": "movers" if cat == "Movers" else "bestsellers",
        })
    if len(keep) < 5:   # a blocked or broken scrape must not wipe yesterday's good feed
        print(f"[chart-scan] only {len(keep)} qualified of {len(items)} scraped — keeping old file")
        return 1
    now = datetime.now(timezone.utc)
    OUT.write_text(json.dumps({"captured_at": now.isoformat(timespec="seconds"),
                               "items": keep}, indent=1))
    by = {}
    for k in keep:
        by[k["category"]] = by.get(k["category"], 0) + 1
    print(f"[chart-scan] {len(keep)} proven chart products of {len(items)} scraped: {by}")

    def _git(*a):
        return subprocess.run(["git", "-C", str(ROOT), *a], capture_output=True, text=True)
    _git("add", str(OUT))
    if _git("diff", "--staged", "--quiet").returncode:
        _git("-c", "user.name=GHP Ops", "-c", "user.email=goldenhomeprojectllc@gmail.com",
             "commit", "-q", "-m", f"charts: {len(keep)} proven chart products {now:%Y-%m-%d}")
        _git("-c", "rebase.autoStash=true", "pull", "--rebase", "-q", "origin", "main")
        r = _git("push", "-q", "origin", "main")
        print("[chart-scan] pushed" if r.returncode == 0 else f"[chart-scan] push failed {r.stderr[:150]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
