#!/usr/bin/env python3
"""generate_howto_pins.py — daily "measure before you buy" how-to pin, brand A/B.

Why: how-to/checklist pins are the format Pinterest users SAVE, and saves drive
distribution; our product pins had 0 saves across 123 pins (2026-10-09). The A/B
templates' how-to layout is a measuring diagram (A width, B depth, C height), so every
how-to here is "measure these 3 numbers before you buy a <type>".

Honesty rules (same as every GHP surface):
- Only products where fit matters AND the listing title states a real dimension. That
  dimension, read off the title by brand_ab.tape_text, is the only product number shown.
- Steps are measuring advice about the reader's own space, never claims about the
  product; no digits in steps, no first-person experience (fabrication gate).
- No product photo at all (typographic), price only as a band, $5-35 and >= 4.5 stars.

Run:  python3 automation/generate_howto_pins.py --max 1
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "automation"))

import brand_ab  # noqa: E402
from affiliate_links import build_affiliate_url, BRAND_TAGS  # noqa: E402
from brand import price_band  # noqa: E402
from content_quality_gate import fabrication_match  # noqa: E402
from pinterest_pipeline import board_for, _search_phrase, _POINTS_AT_PHOTO  # noqa: E402

SOCIAL = ROOT / "social"
PINS_DIR = SOCIAL / "pinterest"
QUEUE_PATH = SOCIAL / "pinterest_queue.json"

# Things that go INTO a cabinet, shelf or closet: the A-arm diagram is a cabinet, so
# curtains, rods and sheets (window/bed measurements) are left out (2026-10-19).
FIT_WORDS = re.compile(r"\b(bins?|baskets?|organi[sz]ers?|shel(f|ves)|racks?|drawers?|cubes?|"
                       r"caddy|caddies|storage|trays?|carts?|hampers?|risers?|turntable|"
                       r"lazy susan)\b", re.I)
NOT_FIT = re.compile(r"\b(curtains?|rods?|sheets?|duvet|comforter|pillow)\b", re.I)
# tape_text results that are a real dimension (not "8 in the pack", "16 oz", "queen size")
REAL_DIM = re.compile(r"(\d x \d|\b\d+(\.\d+)? (in|ft|cm)$|^fits )")


def _price(p) -> float | None:
    m = re.search(r"[\d,]+\.\d{2}", str(p or ""))
    return float(m.group().replace(",", "")) if m else None


def candidates(queue: list[dict]) -> list[dict]:
    """In-policy, fit-sensitive picks with a real title dimension, not how-to'd in 21 days."""
    cutoff = (datetime.now(timezone.utc) - timedelta(days=21)).strftime("%Y-%m-%d")
    recent = {e.get("asin") for e in queue
              if str(e.get("id", "")).startswith("howto-") and str(e.get("id", ""))[6:16] >= cutoff}
    seen, out = set(), []
    for f in sorted(SOCIAL.glob("trending_picks_*.json"), reverse=True)[:10]:
        try:
            picks = json.loads(f.read_text()).get("picks") or []
        except (OSError, json.JSONDecodeError):
            continue
        for p in picks:
            asin, name = p.get("asin"), str(p.get("name") or "")
            if not asin or asin in seen or asin in recent:
                continue
            seen.add(asin)
            price, stars = _price(p.get("price")), float(p.get("rating") or 0)
            tape = brand_ab.tape_text(name)
            if (price and 5 <= price <= 35 and stars >= 4.5 and FIT_WORDS.search(name)
                    and not NOT_FIT.search(name)):
                # Most chart titles state no size; the reader's own measurements are the
                # point, so the product's size shows only when the title gives a real one.
                out.append({**p, "tape": tape if REAL_DIM.search(tape) else ""})
    return out


def write_steps(name: str, phrase: str) -> dict | None:
    try:
        from _claude_api import _load_token_file
        _load_token_file()
    except Exception:
        pass
    prompt = (
        f"Product (Amazon listing title): {name}\nPinterest topic: {phrase}\n\n"
        "Write a 'measure before you buy' Pinterest how-to. Reply with ONLY JSON:\n"
        '{"type": "<generic item type, 2-4 words, lowercase, no brand>",\n'
        ' "steps": ["<A: what WIDTH to measure in the reader\'s own space and how>",\n'
        '           "<B: what DEPTH to measure, incl. the obstacle people forget>",\n'
        '           "<C: what HEIGHT/clearance to measure>"]}\n'
        "Rules: each step 8-16 words, plain second person, about the reader's space only. "
        "No digits or numbers, no brand, no claims about the product, no first-person "
        "experience, no 'this one'/'shown'/'pictured'.")
    try:
        out = subprocess.run(["claude", "-p", "--max-turns", "1"], input=prompt,
                             capture_output=True, text=True, timeout=150).stdout
        d = json.loads(re.search(r"\{.*\}", out, re.S).group())
    except Exception as e:  # noqa: BLE001
        print(f"  [howto] step writing unavailable ({str(e)[:80]})")
        return None
    steps = [re.sub(r"^[ABC][:.)]\s*", "", str(s)).strip() for s in (d.get("steps") or [])][:3]
    typ = str(d.get("type") or "").strip().lower()
    text = " ".join(steps + [typ])
    if (len(steps) != 3 or not typ or len(typ.split()) > 4 or re.search(r"\d", text)
            or fabrication_match(text) or _POINTS_AT_PHOTO.search(text)
            or any(not 5 <= len(s.split()) <= 20 for s in steps)):
        print(f"  [howto] rejected steps: {text[:140]!r}")
        return None
    return {"type": typ, "steps": steps}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--max", type=int, default=1)
    ap.add_argument("--dry", action="store_true", help="render to /tmp/howto, leave the queue alone")
    args = ap.parse_args()
    queue = json.loads(QUEUE_PATH.read_text()) if QUEUE_PATH.exists() else []
    date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    made = 0
    for p in candidates(queue):
        if made >= args.max:
            break
        name, asin = str(p["name"]), p["asin"]
        pin_id = f"howto-{date_str}-{asin}"
        if any(e.get("id") == pin_id for e in queue):
            continue
        board, _q = board_for({"product_name": name})
        phrase = _search_phrase(board)
        got = write_steps(name, phrase)
        if not got:
            continue
        typ, steps, tape = got["type"], got["steps"], p["tape"]
        plural = typ.endswith("s") and not typ.endswith("ss")
        article = "" if plural else ("an " if typ[:1] in "aeiou" else "a ")
        headline = f"Measure these 3 numbers before you buy {article}{typ}"
        kicker = f"{typ} · 2-minute guide"   # the item, not the board (curtains said "bedroom storage")
        band = price_band(str(p.get("price") or ""))
        out = (Path("/tmp/howto") if args.dry else PINS_DIR) / f"{pin_id}.png"
        variant = brand_ab.variant_for(pin_id)   # brand A/B test, see brand_ab.py
        # Both arms get IDENTICAL words (marketing dept, 2026-10-19): only the look differs.
        steps = steps + [f"Check them against the listing: {tape}" if tape
                         else "Then check them against the size on the listing."]
        line = f"Our pick lists {tape}" if tape else "A · B · C — 3 numbers, 2 minutes"
        if variant == "A":
            brand_ab.a_howto(headline, kicker, steps, line, out)
        else:
            brand_ab.b_howto(headline, steps, line, out, kicker=kicker)
        if args.dry:
            made += 1
            print(f"  [dry] {asin} {variant} {typ!r} tape={tape!r} steps={steps}")
            continue
        queue.append({
            "id": pin_id,
            "asin": asin,
            "board": board,
            "title": f"{phrase.title()}: measure these 3 numbers before you buy {article}{typ}"[:100],
            "description": (
                f"Before you buy {article}{typ}, measure the space: width, depth (the part "
                f"people forget) and height. Save this for when you shop. The pick we link "
                f"{'lists ' + tape + ' and ' if tape else ''}is rated {p.get('rating')} stars on Amazon, {band.lower()} "
                f"when we checked; prices change. Amazon affiliate — small commission at no "
                f"extra cost to you.")[:500],
            "image_path": str(out.relative_to(ROOT)),
            "image_url": f"https://goldenhomeproject.com/{out.relative_to(ROOT)}",
            "link": build_affiliate_url(asin, "pinterest", subtag=f"howto_brand{variant}",
                                        tag=BRAND_TAGS[variant]),
            "queued_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "posted": False,
            "source": "generate_howto_pins",
            "format": "howto",
            "variant": variant,
        })
        made += 1
        print(f"  [howto] {asin} {variant} {typ!r} tape={tape!r} -> {out.name}")

    if args.dry:
        return 0
    QUEUE_PATH.write_text(json.dumps(queue, indent=1))
    # Commit + push NOW: the 06:30 daily-loop runs `git reset --hard origin/main`, which
    # erased un-pushed collage entries for a month (2026-10-17).
    if made:
        def _git(*a):
            return subprocess.run(["git", "-C", str(ROOT), *a], capture_output=True, text=True)
        _git("add", str(QUEUE_PATH), *[str(ROOT / e["image_path"]) for e in queue[-made:]])
        _git("-c", "user.name=GHP Ops", "-c", "user.email=goldenhomeprojectllc@gmail.com",
             "commit", "-q", "-m", f"howto: {made} pin(s) {date_str}")
        _git("-c", "rebase.autoStash=true", "pull", "--rebase", "-q", "origin", "main")
        r = _git("push", "-q", "origin", "main")
        print("[howto] queue pushed" if r.returncode == 0 else f"[howto] push failed: {r.stderr[:200]}")
    print(f"[howto] built {made} how-to pin(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
