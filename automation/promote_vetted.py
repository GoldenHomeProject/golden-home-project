#!/usr/bin/env python3
"""promote_vetted.py — autonomously turn a verified `vetted[]` product into a
LIVE comment->link keyword so the content flywheel can feature it.

Why this exists:
  asin_discoverer.py grows the `vetted[]` pool (real /dp/ASINs with verified
  stars/reviews/price), but nothing fed those products into the content engine.
  content_engine.py only ships keywords that are BOTH (a) status='live' in
  dm_keyword_registry.json AND (b) have at least one copy_library.json variant.
  So a vetted product was dead weight until a human hand-wrote a keyword + script.

What this does, fully unattended (cap 1 per run):
  1. Pick the most-proven vetted product (highest verified_reviews) that can get
     a unique, comment-friendly keyword.
  2. Derive that keyword (prefer a specific home-niche noun in the name/cats).
  3. Promote vetted[] -> entries[] with status='live' + keyword + promoted_at.
  4. Seed ONE gate-compliant copy_library.json variant built from the product's
     REAL verified_stars / verified_reviews / verified_price (so it passes the
     falsifiable-detail rule with TRUE numbers — never invented).
  5. Self-validate the exact script content_engine would emit through
     content_quality_gate.check_script BEFORE writing. If it would fail the gate,
     refuse to promote (we never seed content that can't ship).
  6. With --commit (Pi cron): git pull --rebase --autostash, commit, push.

Integrity rules honored:
  - Never invents an ASIN or a stat; every number comes from the vetted entry.
  - Never overwrites an existing live keyword; near-dups (COVER/COVERS) skipped.
  - FTC disclosure + comment-CTA are added by content_engine, validated here.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
AUTOMATION = ROOT / "automation"
REGISTRY = ROOT / "social" / "dm_keyword_registry.json"
COPY_LIBRARY = ROOT / "social" / "copy_library.json"

sys.path.insert(0, str(AUTOMATION))
import content_engine as ce  # noqa: E402
import content_quality_gate as gate  # noqa: E402

# Specific home-niche nouns, most-specific first. A vetted product's keyword is
# the FIRST of these that appears in its name/categories (and is still free).
PREFERRED_NOUNS = [
    "TURNTABLE", "HANGERS", "ZAPPER", "PITCHER", "TOWELS", "LINER", "CADDY",
    "HAMPER", "ORGANIZER", "CLOSET", "PATIO", "THROW", "BLANKET", "KETTLE",
    "PITCHER", "FILTER", "BASKET", "SHELF", "DRAWER", "RACK", "HOOK", "MIRROR",
    "LAMP", "CART", "BIN", "TRAY", "MAT", "PILLOW", "COVER", "MAT",
]

# Brand / marketing / structural tokens that must never become a keyword if we
# fall back to raw name tokens.
STOPWORDS = {
    "WITH", "AND", "FOR", "THE", "YOUR", "FROM", "PULL", "NON", "SKID", "SLIP",
    "ADHESIVE", "EXPANDABLE", "SLIM", "SPACE", "SAVING", "SMALL", "LARGE",
    "OUTDOOR", "INDOOR", "PIECE", "PIECES", "SET", "SETS", "SOFT", "LINEN",
    "LUXURY", "BABY", "KIDS", "GREEN", "SAGE", "BLUE", "WHITE", "BLACK",
    "FARMHOUSE", "AMAZON", "BASICS", "AMERICAN", "PXRACK", "BAGAIL",
    "VONGRASIG", "MIULEE", "BRITA", "SOLAR", "WATER", "BOHO", "VELVET",
    "TURKISH", "STAINLESS", "STEEL", "NIGHT",
}

# Lowercase descriptors we're happy to use as an adjective in the seeded copy.
GENERIC_CATS = {
    "organization", "storage", "kitchen", "bathroom", "bedroom", "home",
    "best", "cheap", "small", "outdoor", "indoor", "cabinet",
}

PLACE_BY_CAT = {
    "kitchen": "kitchen", "under-sink": "kitchen", "bathroom": "bathroom",
    "closet": "closet", "patio": "patio", "outdoor": "patio",
    "bedroom": "bedroom", "sleep": "bedroom",
}


def _tokens(text: str) -> list[str]:
    return [t.upper() for t in re.split(r"[^A-Za-z]+", text) if len(t) >= 4]


def _near_dup(a: str, b: str) -> bool:
    """True if a and b overlap as a prefix by >=4 chars (COVER ~ COVERS)."""
    a, b = a.upper(), b.upper()
    return a == b or (len(a) >= 4 and len(b) >= 4 and (a.startswith(b) or b.startswith(a)))


def derive_keyword(entry: dict, taken: set[str]) -> str | None:
    name = entry.get("product_name", "")
    cats = " ".join(entry.get("categories", []))
    toks = set(_tokens(name) + _tokens(cats))

    def is_free(kw: str) -> bool:
        return not any(_near_dup(kw, t) for t in taken)

    # 1) Prefer a specific home-niche noun present in the product text.
    for noun in PREFERRED_NOUNS:
        if any(_near_dup(noun, t) for t in toks) and is_free(noun):
            return noun
    # 2) Fall back to the first non-stopword name token.
    for tok in _tokens(name):
        if tok not in STOPWORDS and is_free(tok):
            return tok
    return None


def _place(cats: list[str]) -> str:
    for c in cats:
        if c.lower() in PLACE_BY_CAT:
            return PLACE_BY_CAT[c.lower()]
    return "home"


def _descriptor(cats: list[str]) -> str:
    for c in cats:
        cl = c.lower()
        if cl in GENERIC_CATS or " " in cl:
            continue
        if re.fullmatch(r"[a-z][a-z-]*[a-z]", cl):
            return cl + " "
    return ""


def build_variant(entry: dict, keyword: str) -> dict:
    """Seed ONE wrong_until_right variant from the product's REAL numbers.
    Caption assembled downstream by content_engine must pass every gate rule —
    we validate that before the caller commits anything."""
    cats = entry.get("categories", [])
    place = _place(cats)
    place_cap = place[:1].upper() + place[1:]
    noun = keyword.lower()
    desc = _descriptor(cats)
    stars = entry.get("verified_stars")
    reviews = entry.get("verified_reviews")
    price = entry.get("verified_price", "")
    reviews_fmt = f"{reviews:,}" if isinstance(reviews, int) else str(reviews)

    hook = f"My {place} had been a low-grade mess for longer than I want to admit."
    beat1 = ("I kept meaning to deal with it and kept not dealing with it. "
             "Things piled up, I could never find what I needed, and every time "
             "I opened it I just shut it again.")
    turn = (f"Then I found a {desc}{noun} sitting at {stars} stars across "
            f"{reviews_fmt} reviews, and it finally gave everything a place.")
    result = (f"It runs about {price} and it's the first thing in a while that "
              f"just worked. The {place} actually stays sorted now.")

    scenes = [
        {"n": 1, "duration_sec": 3,
         "visual_prompt": f"first-person POV of a cluttered {place}, things spilling out",
         "on_screen_text": "THIS WAS EVERY DAY",
         "voiceover": f"My {place} had been a mess for longer than I'll admit."},
        {"n": 2, "duration_sec": 4,
         "visual_prompt": f"close-up of disorganized items in the {place}",
         "on_screen_text": "COULD NEVER FIND ANYTHING",
         "voiceover": "I kept meaning to deal with it and kept not dealing with it."},
        {"n": 3, "duration_sec": 4,
         "visual_prompt": "person shutting a door/drawer in frustration",
         "on_screen_text": "SO I GAVE UP",
         "voiceover": "Every time I opened it I just shut it again."},
        {"n": 4, "duration_sec": 5,
         "visual_prompt": f"the {noun} in use, everything organized and visible",
         "on_screen_text": "THEN THIS",
         "voiceover": f"Then I found a {noun} that finally gave everything a place."},
        {"n": 5, "duration_sec": 4,
         "visual_prompt": f"satisfying final shot of the tidy {place}",
         "on_screen_text": "STAYS SORTED NOW",
         "voiceover": f"The {place} actually stays sorted now."},
    ]
    return {
        "hook_category": "wrong_until_right",
        "hook": hook,
        "beat1": beat1,
        "turn": turn,
        "result": result,
        "scenes": scenes,
    }


def validate_variant(variant: dict, keyword: str, entry: dict) -> tuple[bool, list[str]]:
    """Run the EXACT script content_engine would emit through the quality gate."""
    library = ce.load_copy_library()
    hashtags = ce._pick_hashtags(library, entry)
    caption = ce._build_caption(variant, keyword, hashtags, registry_entry=entry)
    script = {
        "caption": caption,
        "hashtags": hashtags,
        "affiliate_strategy": {
            "primary_product": entry["product_name"],
            "amazon_asin": entry["asin"],
        },
    }
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
        json.dump(script, f)
        tmp = Path(f.name)
    try:
        return gate.check_script(tmp)
    finally:
        tmp.unlink(missing_ok=True)


def run_git(args: list[str]) -> tuple[int, str]:
    p = subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True)
    return p.returncode, (p.stdout + p.stderr).strip()


def commit_and_push(keyword: str, asin: str) -> None:
    rc, out = run_git(["pull", "--rebase", "--autostash"])
    if rc != 0:
        print(f"[promote] git pull failed (continuing to commit locally): {out}")
    run_git(["add", str(REGISTRY), str(COPY_LIBRARY)])
    rc, out = run_git(["commit", "-m",
                       f"Auto-promote vetted product {asin} -> live keyword {keyword}"])
    if rc != 0:
        print(f"[promote] nothing to commit / commit failed: {out}")
        return
    rc, out = run_git(["push"])
    print(f"[promote] push: {'ok' if rc == 0 else 'FAILED ' + out}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--commit", action="store_true",
                    help="git pull/commit/push after promoting (Pi cron uses this)")
    ap.add_argument("--dry-run", action="store_true",
                    help="show what would be promoted, write nothing")
    args = ap.parse_args()

    reg = json.loads(REGISTRY.read_text())
    entries = reg.get("entries", [])
    vetted = reg.get("vetted", [])
    if not vetted:
        print("[promote] vetted[] is empty — nothing to promote.")
        return 0

    taken = {e["keyword"].upper() for e in entries if e.get("keyword")}

    # Most-proven first: a high review count is the best signal the product is real
    # and converts. Promote the single best candidate we can name uniquely.
    for entry in sorted(vetted, key=lambda e: e.get("verified_reviews") or 0, reverse=True):
        if not entry.get("asin") or not entry.get("verified_reviews"):
            continue
        keyword = derive_keyword(entry, taken)
        if not keyword:
            print(f"[promote] {entry['asin']}: no unique keyword available, skipping.")
            continue
        variant = build_variant(entry, keyword)
        ok, reasons = validate_variant(variant, keyword, entry)
        if not ok:
            print(f"[promote] {entry['asin']} kw={keyword}: seeded variant FAILS gate "
                  f"{reasons} — skipping (won't seed unshippable content).")
            continue

        print(f"[promote] selected {entry['asin']} -> keyword {keyword} "
              f"({entry.get('verified_stars')}* / {entry['verified_reviews']} reviews)")
        if args.dry_run:
            print("[promote] --dry-run: writing nothing.")
            return 0

        # 1) vetted -> entries (live)
        promoted = dict(entry)
        promoted["keyword"] = keyword
        promoted["status"] = "live"
        promoted["promoted_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        reg["entries"] = entries + [promoted]
        reg["vetted"] = [v for v in vetted if v.get("asin") != entry["asin"]]
        REGISTRY.write_text(json.dumps(reg, indent=2) + "\n")

        # 2) seed the copy_library variant
        lib = json.loads(COPY_LIBRARY.read_text())
        lib.setdefault("variants", {}).setdefault(keyword, []).append(variant)
        COPY_LIBRARY.write_text(json.dumps(lib, indent=2) + "\n")

        print(f"[promote] LIVE: {keyword} -> {entry['asin']} "
              f"(entries now {len(reg['entries'])}, vetted now {len(reg['vetted'])})")

        if args.commit:
            commit_and_push(keyword, entry["asin"])
        return 0

    print("[promote] no promotable vetted product this run.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
