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
import json
import re
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
    return hist


def find_drops(hist: dict, min_pct: float) -> list[dict]:
    drops = []
    for asin, rows in hist.items():
        if len(rows) < 2:
            continue
        now, prev = rows[-1], rows[-2]
        if now["price"] >= prev["price"]:
            continue
        pct = (prev["price"] - now["price"]) / prev["price"] * 100
        if pct < min_pct:
            continue
        drops.append({
            "asin": asin,
            "title": now["title"],
            "rating": now["rating"],
            "reviews": now["reviews"],
            "was": round(prev["price"], 2),
            "now": round(now["price"], 2),
            "pct": round(pct, 1),
            "observed_from": prev["date"],
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
