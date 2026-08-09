#!/usr/bin/env python3
"""revalidate_vetted.py — re-check every `vetted[]` ASIN against a live /dp/ page and
stamp the result, so downstream consumers can trust `status`.

Why this exists: `build_vetted_entry()` never wrote a `status` field, but
`pinterest_pipeline.py` hard-gates on `status == "live"` (added after the April 2026
dead-ASIN incident). Every auto-discovered product was therefore skipped, the pin
queue drained, and Pinterest went silent for ~29 days. The generator bug is fixed at
the source; this backfills the 24 entries already stranded in the pool.

It does NOT blindly trust the old verification: those entries were checked in mid-June
and listings die. Each one is re-fetched now through the same conservative
`verify_dp()` the discoverer uses (real #productTitle, no robot-check sentinel), on the
Pi's residential IP.

  live  -> status="live"  + refreshed price/stars/reviews, verified_at=today
  gone  -> status="dead"  (kept for the record, permanently excluded from pins)

Usage:  ~/.ghp-asin-discoverer/venv/bin/python automation/revalidate_vetted.py [--dry-run]
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from asin_discoverer import REGISTRY_PATH, UA, verify_dp  # noqa: E402

# Amazon Basics AA batteries: a listing that has existed for years. If THIS
# will not render, the problem is us being blocked, not the catalogue.
CANARY_ASIN = "B00FLYWNYQ"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="report only, write nothing")
    ap.add_argument("--all", action="store_true",
                    help="re-check every vetted entry, not just the unstamped ones")
    args = ap.parse_args()

    reg = json.loads(REGISTRY_PATH.read_text())
    vetted = reg.get("vetted", [])
    targets = [e for e in vetted if args.all or e.get("status") != "live"]
    if not targets:
        print("[revalidate] nothing to check")
        return 0

    print(f"[revalidate] checking {len(targets)} of {len(vetted)} vetted ASIN(s)")
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    live = dead = 0

    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=["--disable-blink-features=AutomationControlled", "--no-sandbox"],
        )
        context = browser.new_context(user_agent=UA, viewport={"width": 1280, "height": 800})
        page = context.new_page()

        # CANARY. verify_dp() cannot tell "this product is gone" apart from "Amazon is
        # bot-walling us" — both just fail to render #productTitle. On 2026-08-09 a
        # throttled Pi reported 5 of 5 live best-seller products as dead, including a
        # control ASIN that has existed for a decade; the page was actually the
        # "Click the button below to continue shopping" interstitial. Marking a good
        # product status="dead" is permanent and silently shrinks the catalogue, so
        # prove we can read a known-good listing BEFORE trusting a single failure.
        if verify_dp(page, CANARY_ASIN) is None:
            print(f"[revalidate] ABORT: control listing {CANARY_ASIN} did not render — "
                  f"Amazon is throttling or blocking us. Refusing to mark anything dead "
                  f"on unreadable pages. Try again later.")
            context.close()
            browser.close()
            return 1

        for entry in targets:
            asin = entry.get("asin")
            if not asin:
                continue
            info = verify_dp(page, asin)
            if info and info.get("title"):
                entry["status"] = "live"
                entry["verified_at"] = today
                entry["verified_method"] = "revalidate_vetted/dp"
                if info.get("price"):
                    entry["verified_price"] = info["price"]
                if info.get("stars"):
                    entry["verified_stars"] = str(info["stars"])
                if info.get("reviews"):
                    entry["verified_reviews"] = info["reviews"]
                live += 1
                print(f"  LIVE {asin}  {entry.get('verified_price','?'):>8}  "
                      f"{(info['title'] or '')[:56]}")
            else:
                entry["status"] = "dead"
                entry["verified_at"] = today
                entry["verified_method"] = "revalidate_vetted/dp"
                dead += 1
                print(f"  DEAD {asin}  {(entry.get('product_name') or '')[:56]}")

        context.close()
        browser.close()

    print(f"\n[revalidate] live={live} dead={dead}")
    if args.dry_run:
        print("[revalidate] --dry-run, registry not written")
        return 0

    REGISTRY_PATH.write_text(json.dumps(reg, indent=2) + "\n")
    print(f"[revalidate] wrote {REGISTRY_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
