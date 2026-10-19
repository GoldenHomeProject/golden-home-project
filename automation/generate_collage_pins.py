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

from collage_pin import HUB_HEADLINES  # noqa: E402
from brand import price_band  # noqa: E402
import brand_ab  # noqa: E402
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


def tile_types(names: list[str]) -> list[str]:
    """2-4 word generic item type per product ("Fabric storage cube"), no brand.

    Collages went typographic on 2026-10-18: the old image cells were FLUX renders of
    each product, and an AI picture of a specific product implies it is the real item
    (marketing dept). The type line comes ONLY from the listing name; fallback is the
    cleaned name itself."""
    from video_pin import clean_headline
    from pinterest_pipeline import _strip_brand, _short_name
    fallback = [clean_headline(_strip_brand(_short_name(n, limit=40)), limit=30) for n in names]
    prompt = ("For each Amazon product name below, give the generic item type in 2-4 words, "
              "sentence case, no brand, no adjectives that are not in the name. Reply with "
              "ONLY a JSON array of strings, same order.\n" + "\n".join(f"- {n}" for n in names))
    try:
        from _claude_api import _load_token_file
        _load_token_file()
    except Exception:
        pass
    try:
        import subprocess
        out = subprocess.run(["claude", "-p", "--max-turns", "1"], input=prompt,
                             capture_output=True, text=True, timeout=120).stdout
        got = json.loads(re.search(r"\[.*\]", out, re.S).group())
        if len(got) == len(names):
            return [str(t).strip()[:32] or f for t, f in zip(got, fallback)]
    except Exception as e:  # noqa: BLE001
        print(f"    [tiles] type naming unavailable ({str(e)[:60]}); using names")
    return fallback


def tile_why(p: dict) -> str:
    """A verifiable fact only: a size/count from the title, else the rating if well-proven."""
    why = brand_ab.tape_text(str(p.get("name") or ""))
    if why:
        return why
    try:
        if int(str(p.get("reviews") or 0).replace(",", "")) >= 1000 and p.get("rating"):
            return f"{p['rating']} stars on Amazon"
    except ValueError:
        pass
    return ""


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
                 if in_category(p.get("name") or p.get("title") or "", cat)][:6]
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

        picks = picks[:len(picks) // 2 * 2]   # 4 or 6: a 2-column grid with a hole looks broken
        print(f"  [collage] {slug} from {f.name} ({cat})")
        types = tile_types([str(p.get("name") or "") for p in picks])
        tiles = [{"type": t, "why": tile_why(p), "band": price_band(str(p.get("price") or ""))}
                 for t, p in zip(types, picks)]
        prices = [v for v in (_price_val(p.get("price")) for p in picks) if v]
        label = HUB_HEADLINES.get(slug, ("Home Finds", "home"))[0]
        headline = (f"{len(picks)} {label} {price_band(str(max(prices)))}" if prices
                    else f"{len(picks)} {label} Worth Buying")
        kicker = HUB_HEADLINES.get(slug, ("", "home"))[1]
        out = PINS_DIR / f"{pin_id}.png"
        variant = brand_ab.variant_for(pin_id)   # brand A/B test, see brand_ab.py
        if variant == "A":
            brand_ab.a_collage(headline, kicker, tiles, out)
        else:
            brand_ab.b_collage(headline, tiles, out, kicker=kicker)

        # Say only what the picks show (the old line claimed "4.5 stars or higher across
        # thousands of ratings" for every collage without checking).
        rts = [float(p["rating"]) for p in picks if str(p.get("rating") or "").replace(".", "", 1).isdigit()]
        proof = (f"Every pick is rated {min(rts):g} stars or higher. "
                 if len(rts) == len(picks) and min(rts) >= 4.3 else "")
        queue.append({
            "id": pin_id,
            "asin": picks[0]["asin"],
            "board": "Home Organization Finds",
            "title": headline,
            "description": (
                f"{headline}. {proof}Picked from Amazon's live best-seller charts. "
                f"Price ranges were accurate when published and change often."),
            "image_path": str(out.relative_to(ROOT)),   # key every other producer uses
            "link": f"{SITE}/blog/posts/{slug}.html?v={variant}",   # hub retags by arm
            "format": "collage",
            "variant": variant,
        })
        made += 1
        print(f"    wrote {out.name} -> {slug}")

    QUEUE_PATH.write_text(json.dumps(queue, indent=1))
    # Commit + push NOW. This job writes the queue at 06:20 and the 06:30 daily-loop does
    # `git reset --hard origin/main`, which silently erased the entry: only 2 of ~35
    # collages built since 2026-09-12 ever reached Pinterest (found 2026-10-17).
    # pinterest_pipeline.py has always pushed immediately for exactly this reason.
    if made:
        import subprocess
        def _git(*a):
            return subprocess.run(["git", "-C", str(ROOT), *a], capture_output=True, text=True)
        _git("add", str(QUEUE_PATH), *[str(PINS_DIR / f"{p['id']}.png") for p in queue[-made:]
                                        if p.get("format") == "collage"])
        _git("-c", "user.name=GHP Ops", "-c", "user.email=goldenhomeprojectllc@gmail.com",
             "commit", "-q", "-m", f"collage: {made} pin(s) {datetime.now(timezone.utc):%Y-%m-%d}")
        _git("-c", "rebase.autoStash=true", "pull", "--rebase", "-q", "origin", "main")
        r = _git("push", "-q", "origin", "main")
        print("[collage] queue pushed" if r.returncode == 0 else f"[collage] push failed: {r.stderr[:200]}")
    print(f"[collage] built {made} collage pin(s); queue now {len(queue)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
