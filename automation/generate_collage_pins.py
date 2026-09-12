#!/usr/bin/env python3
"""generate_collage_pins.py — daily COLLAGE pins built from a hub's own products.

Collage pins are saved ~2x more often than single-product pins (Pinterest's own
guidance; case studies put them at ~87% of saves). Every GHP pin before this was a
single product, so this is the format we were missing entirely.

The hard rule here: the four products IN the picture must be four products ON the page
the pin links to. A collage assembled from unrelated stock images looks great and lies
about what it is selling, which is worse than not pinning at all. So the cells are built
from the same trending_picks_*.json that generated the hub, and the pin links to that
hub — the one case where a hub beats a direct /dp/ link, because the pin promises
several products and only the hub can deliver them.

Run:  python3 automation/generate_collage_pins.py --max 2
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "automation"))

from collage_pin import build_collage_pin, headline_for, HUB_HEADLINES  # noqa: E402
from category_identity import in_category  # noqa: E402

SOCIAL = ROOT / "social"
PINS_DIR = SOCIAL / "pinterest"
QUEUE_PATH = SOCIAL / "pinterest_queue.json"
SITE = "https://goldenhomeproject.com"

# category label in the picks file -> hub slug that lists those products
CATEGORY_SLUG = {
    "Kitchen": "best-kitchen-gadgets",
    "Home Storage": "best-storage-bins",
    "Home Décor": "best-home-decor-finds",
    "Home": "best-home-organization-products",
    "Bath": "best-bathroom-essentials",
    "Cleaning": "best-cleaning-supplies",
    "Bedding": "best-bedding-essentials",
    "Sheets": "best-sheet-sets",
    "Window Treatments": "best-blackout-curtains",
    "Bath Linens": "best-bath-towels-and-linens",
}


def _price_val(p) -> float | None:
    m = re.search(r"[\d.]+", str(p or ""))
    return float(m.group(0)) if m else None


def cell_image(product: str, out: Path, seed: int) -> bool:
    """Product image for one cell — FLUX, retried, then a people-free stock photo.

    First run of this produced a collage whose cell 01 was a woman rollerblading in a
    park: FLUX was rejected for rendered text and Pexels answered the product name with
    a lifestyle photo. A single bad cell discredits the whole pin, so FLUX gets several
    seeds before we fall back, and the fallback is forced toward object-only imagery.
    """
    try:
        from reel_producer import flux_image
        for attempt in range(3):
            if flux_image(
                f"a single {product[:80]}, centred on a clean bright surface, "
                f"bright airy daylight, minimal uncluttered background, "
                f"product photography, no people",
                product, out, seed=seed + attempt * 911):
                return True
    except Exception as e:
        print(f"    [cell] flux unavailable: {str(e)[:70]}")
    try:
        from pinterest_pipeline import fetch_pexels
        words = [w for w in re.sub(r"[^A-Za-z ]", " ", product).split() if len(w) > 2]
        q = " ".join(words[-3:]) or product
        return fetch_pexels(f"{q} product still life no people", out)
    except Exception as e:
        print(f"    [cell] pexels failed: {str(e)[:70]}")
        return False


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--max", type=int, default=1, help="collage pins to build")
    args = ap.parse_args()

    files = sorted(SOCIAL.glob("trending_picks_*.json"), reverse=True)
    queue = json.loads(QUEUE_PATH.read_text()) if QUEUE_PATH.exists() else []
    if isinstance(queue, dict):
        queue = queue.get("queue", [])
    existing = {p.get("id") for p in queue}
    date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    made = 0

    for f in files:
        if made >= args.max:
            break
        try:
            data = json.loads(f.read_text())
        except (json.JSONDecodeError, OSError):
            continue
        cat = data.get("category") or ""
        slug = CATEGORY_SLUG.get(cat)
        if not slug:
            continue
        hub = ROOT / "blog" / "posts" / f"{slug}.html"
        if not hub.exists():
            print(f"  [skip] {slug}: hub page does not exist — pin would link nowhere")
            continue

        # Identity, not just provenance. The first version of this guard trusted the
        # picks file's own category label, and on 2026-09-12 it built
        # "4 Storage Bin Picks Under $33" out of an Owala water bottle, velvet hangers,
        # a Stanley tumbler and a lunch bag — every one of them genuinely scraped from
        # Amazon's Home Storage node, not one of them a storage bin. A collage that
        # lies about what it is selling is worse than no collage.
        raw = [p for p in (data.get("picks") or []) if p.get("asin")]
        picks = [p for p in raw
                 if in_category(p.get("name") or p.get("title") or "", cat)][:4]
        if len(picks) < 4:
            print(f"  [skip] {slug}: only {len(picks)} of {len(raw)} picks read as "
                  f"genuinely {cat} — refusing to build a mislabelled collage")
            continue
        pin_id = f"collage-{date_str}-{slug}"
        if pin_id in existing:
            continue

        # Only pin products the hub actually lists right now.
        html = hub.read_text(errors="ignore")
        picks = [p for p in picks if p["asin"] in html]
        if len(picks) < 4:
            print(f"  [skip] {slug}: hub no longer lists 4 of these picks")
            continue

        print(f"  [collage] {slug} from {f.name} ({cat})")
        cells = []
        for i, p in enumerate(picks):
            img = PINS_DIR / f"cell-{date_str}-{p['asin']}.jpg"
            name = str(p.get("name") or "")
            if not img.exists():
                cell_image(name, img, seed=4200 + made * 17 + i)
            cells.append({"image": img if img.exists() else None,
                          "price": str(p.get("price") or "")})

        prices = [v for v in (_price_val(p.get("price")) for p in picks) if v]
        headline = headline_for(slug, len(picks), max(prices) if prices else None)
        kicker = HUB_HEADLINES.get(slug, ("", "home"))[1]
        out = PINS_DIR / f"{pin_id}.png"
        build_collage_pin(
            headline, "Verified 4.5 stars and up", cells, out,
            updated=datetime.now(timezone.utc).strftime("Updated %B %Y"),
            kicker=kicker)

        queue.append({
            "id": pin_id,
            "asin": picks[0]["asin"],
            "board": "Home Organization Finds",
            "title": headline,
            "description": (
                f"{headline}. Every pick holds 4.5 stars or higher across thousands of "
                f"ratings, read off Amazon's live best-seller charts. "
                f"Prices shown were accurate when published and change often."),
            "image": str(out.relative_to(ROOT)),
            "link": f"{SITE}/blog/posts/{slug}.html",
            "format": "collage",
        })
        made += 1
        print(f"    wrote {out.name} -> {slug}")

    QUEUE_PATH.write_text(json.dumps(queue, indent=1))
    print(f"[collage] built {made} collage pin(s); queue now {len(queue)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
