#!/usr/bin/env python3
"""price_drops.py — find REAL price drops in our own daily best-seller snapshots.

Why this exists (2026-08-08): research on what survived Google's 2026 core updates is
blunt — what gets demoted is content "a competitor could replicate with an AI prompt",
and generic AI roundups of Amazon best-sellers are exactly that. GHP publishes the most
replicable thing on the internet, which is why 13 pages sit unindexed.

The one asset here that ISN'T replicable is data we generated: trending_daily.py has
been scraping Amazon's live best-seller charts every morning and saving price, rating
and review counts to social/trending_picks_<date>.json. That accumulating history lets
us state something no prompt can invent — that a specific product actually cost less
today than it did last week, observed by us, on dated snapshots.

Price drops are also the highest buyer-intent content there is: people buy on deals.

Honesty rules baked in:
  * only report a drop we actually observed in two dated snapshots
  * compare against the MOST RECENT prior price, not the all-time high, so we never
    imply a bigger discount than really happened
  * never present a stale price as current — the newest snapshot is the current price

    python3 automation/price_drops.py [--min-pct 5] [--json]
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import statistics
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SOCIAL = ROOT / "social"
OUT = SOCIAL / "price_drops.json"


def price_val(p) -> float | None:
    m = re.search(r"[\d,]+\.\d{2}", str(p or ""))
    return float(m.group().replace(",", "")) if m else None


def load_history() -> dict[str, list[dict]]:
    """asin -> [{date, price, title, rating, reviews}] ordered oldest..newest."""
    hist: dict[str, list[dict]] = {}
    for path in sorted(SOCIAL.glob("trending_picks_*.json")):
        date = path.stem.replace("trending_picks_", "")
        try:
            data = json.loads(path.read_text())
        except (json.JSONDecodeError, OSError):
            continue
        for pk in (data if isinstance(data, list) else data.get("picks", [])):
            asin = (pk.get("asin") or "").strip()
            pv = price_val(pk.get("price"))
            if not asin or pv is None:
                continue
            hist.setdefault(asin, []).append({
                "date": date, "price": pv,
                "title": pk.get("title") or pk.get("name") or "",
                "rating": pk.get("rating"), "reviews": pk.get("reviews"),
            })
    # 2026-11-24: the 6 daily picks above are a thin history (5 drops found on BF week).
    # chart_scan.py commits the full ~110-product chart to social/chart_now.json every
    # morning, so git already holds a dated daily price history for every chart product.
    seen = {(a, r["date"]) for a, rows in hist.items() for r in rows}
    for date, items in chart_snapshots():
        for it in items:
            asin = (it.get("asin") or "").strip()
            pv = price_val(it.get("price"))
            if not asin or pv is None or (asin, date) in seen:
                continue
            seen.add((asin, date))
            hist.setdefault(asin, []).append({
                "date": date, "price": pv, "title": it.get("name") or "",
                "rating": it.get("rating"), "reviews": it.get("reviews"),
            })
    for rows in hist.values():
        rows.sort(key=lambda r: r["date"])
    return hist


def chart_snapshots(days: int = 45) -> list[tuple[str, list]]:
    """[(date, items)] from the last commit of social/chart_now.json on each day."""
    try:
        log = subprocess.run(["git", "-C", str(ROOT), "log", f"--since={days} days ago",
                              "--format=%H %cs", "--", "social/chart_now.json"],
                             capture_output=True, text=True, timeout=60).stdout.split("\n")
    except (OSError, subprocess.SubprocessError):
        return []
    by_day: dict[str, str] = {}
    for line in log:                       # newest first, so the first per day is the last
        if " " in line:
            sha, day = line.split()
            by_day.setdefault(day, sha)
    out = []
    for day, sha in sorted(by_day.items()):
        try:
            raw = subprocess.run(["git", "-C", str(ROOT), "show", f"{sha}:social/chart_now.json"],
                                 capture_output=True, text=True, timeout=30).stdout
            out.append((day, json.loads(raw).get("items") or []))
        except (OSError, subprocess.SubprocessError, ValueError, AttributeError):
            continue
    return out


def find_drops(hist: dict, min_pct: float) -> list[dict]:
    # 2026-11-24: a product that fell off the chart kept its last price as "now" (the top
    # "drop" was a 11/01 price shown as current on BF week). Only the newest snapshot is now.
    latest = max((r["date"] for rows in hist.values() for r in rows), default="")
    drops = []
    for asin, rows in hist.items():
        if len(rows) < 2 or rows[-1]["date"] != latest:
            continue
        now = rows[-1]
        # With daily data, "vs yesterday" would show a deal for one day only. The reference
        # is the MEDIAN of our own observations over the prior 14 days (a typical price, not
        # the all-time high); with fewer than 3 of those, the most recent prior price.
        cutoff = (dt.date.fromisoformat(latest) - dt.timedelta(days=14)).isoformat()
        prior = [r for r in rows[:-1] if r["date"] >= cutoff]
        if len(prior) >= 3:
            ref, basis = statistics.median(r["price"] for r in prior), "14-day median"
            since = prior[0]["date"]
        elif prior:
            ref, basis, since = prior[-1]["price"], "last seen", prior[-1]["date"]
        else:
            continue                        # nothing in 14 days: too stale to call a drop
        if now["price"] >= ref:
            continue
        pct = (ref - now["price"]) / ref * 100
        if pct < min_pct:
            continue
        drops.append({
            "asin": asin,
            "title": now["title"],
            "rating": now["rating"],
            "reviews": now["reviews"],
            "was": round(ref, 2),
            "now": round(now["price"], 2),
            "pct": round(pct, 1),
            "basis": basis,
            "observed_from": since,
            "observed_to": now["date"],
            "days_tracked": len(rows),
        })
    return sorted(drops, key=lambda d: -d["pct"])


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--min-pct", type=float, default=5.0)
    ap.add_argument("--json", action="store_true", help="write social/price_drops.json")
    args = ap.parse_args()

    hist = load_history()
    tracked = sum(1 for v in hist.values() if len(v) > 1)
    drops = find_drops(hist, args.min_pct)
    print(f"[drops] {len(hist)} ASINs in history, {tracked} seen on 2+ days, "
          f"{len(drops)} dropped >={args.min_pct}%")
    for d in drops[:12]:
        print(f"   -{d['pct']:>5.1f}%  ${d['was']:>7.2f} -> ${d['now']:>7.2f}  "
              f"{d['title'][:52]}  ({d['observed_from']}->{d['observed_to']})")
    if args.json:
        OUT.write_text(json.dumps({"drops": drops, "tracked_asins": tracked}, indent=2) + "\n")
        print(f"[drops] wrote {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
