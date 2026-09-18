#!/usr/bin/env python3
"""category_identity.py — does this product actually BELONG in the category we claim?

Why this exists (2026-09-12)
----------------------------
`trending_daily` already had a guard against mislabelled pages, but it checked
provenance rather than identity:

    primary = [p for p in picks if p.get("cat_label") == cat_label]

`cat_label` records which Amazon node a product was scraped from. Amazon's node
taxonomy is loose and best-seller charts bleed, so the Home Storage node genuinely
serves an Owala water bottle and a Stanley tumbler — and the guard passed them,
because they really did come from that node.

The result shipped: `best-storage-bins.html` listed a water bottle, velvet hangers, a
Stanley tumbler and a lunch bag, and the collage pin built from those picks was titled
"4 Storage Bin Picks Under $33" with not one storage bin in it. A pin that lies about
what it is selling is worse than no pin, and a hub that does the same cannot convert.

So: match the product TITLE against terms that define the category. A product that
mentions none of them cannot represent that category, whatever node it came from.

Deliberately conservative. Fewer honest picks beat a mislabelled page — the same
principle that already makes `trending_daily` refuse to publish rather than ship a
page whose identity was borrowed from a neighbouring node.
"""
from __future__ import annotations

import re

# Positive terms per category. Kept narrow on purpose: a term is here only if a
# product mentioning it genuinely belongs on that page.
CATEGORY_TERMS: dict[str, tuple[str, ...]] = {
    "Home Storage": (
        "bin", "basket", "container", "organizer", "organiser", "storage",
        "shelf", "shelves", "shelving", "rack", "drawer", "cube", "tote",
        "caddy", "closet", "hanger", "hook", "under bed", "under-bed",
        "stackable", "cart", "moving bag", "storage bag", "lid box",
    ),
    "Home": (
        "organizer", "organiser", "storage", "bin", "basket", "shelf", "shelves",
        "rack", "drawer", "hook", "caddy", "holder", "dispenser", "tray",
        "closet", "hanger", "cube", "container", "cart", "sorter",
    ),
    "Kitchen": (
        "kitchen", "cook", "pan", "pot", "skillet", "utensil", "knife", "knives",
        "cutting board", "spatula", "whisk", "mixing", "measuring", "colander",
        "strainer", "baking", "bakeware", "food storage", "lid", "blender",
        "grater", "peeler", "can opener", "dish", "mug", "kettle", "tumbler",
        "water bottle", "air fryer", "silicone", "cutlery", "flatware",
        "food container", "pantry", "spice",
    ),
    "Home Décor": (
        "decor", "décor", "wall art", "frame", "vase", "candle", "mirror",
        "lamp", "light", "rug", "pillow", "throw", "curtain", "plant", "planter",
        "garland", "wreath", "sign", "clock", "ornament", "faux",
    ),
    "Bath": (
        "bath", "shower", "toilet", "sink", "vanity", "soap", "towel",
        "bathroom", "tub", "curtain", "liner", "mat", "toothbrush", "razor",
        "caddy", "dispenser",
    ),
    "Cleaning": (
        "clean", "cleaner", "mop", "broom", "vacuum", "duster", "sponge",
        "scrub", "wipe", "detergent", "disinfect", "brush", "squeegee",
        "microfiber", "microfibre", "laundry", "stain", "trash", "bag",
    ),
    "Bedding": (
        "comforter", "duvet", "quilt", "blanket", "bedding", "pillow",
        "mattress", "bed skirt", "coverlet", "throw", "protector", "topper",
        "sham", "insert",
    ),
    # "mattress" and "bedding" were qualifiers here and should not be: node 1063308
    # returns memory-foam mattresses, bed frames and toppers, and every one of them
    # counted as a genuine pick for a page titled "best sheet sets". A sheet set is
    # sheets, pillowcases and the set they come in — nothing you sleep ON.
    "Sheets": (
        "sheet set", "bed sheet", "bedsheet", "pillowcase", "pillow case",
        "fitted sheet", "flat sheet", "duvet cover", "sheets",
    ),
    "Window Treatments": (
        "curtain", "drape", "blind", "shade", "valance", "blackout", "window",
        "rod", "grommet", "sheer",
    ),
    "Bath Linens": (
        "towel", "washcloth", "wash cloth", "bath sheet", "hand towel",
        "bath mat", "robe", "linen", "gsm",
    ),
    # Seasonal Décor is one node that changes what it sells as the calendar turns:
    # Halloween in Sept/Oct, Thanksgiving in Nov, Christmas from Nov into Dec. The
    # terms therefore have to cover the whole year at once, not just the holiday
    # that happens to be next.
    "Seasonal Décor": (
        "halloween", "pumpkin", "spooky", "ghost", "skeleton", "bat", "witch",
        "christmas", "xmas", "holiday", "santa", "snowman", "snowflake",
        "ornament", "stocking", "garland", "wreath", "tinsel", "advent",
        "nativity", "tree skirt", "tree topper", "string lights", "fairy lights",
        "thanksgiving", "harvest", "autumn", "fall decor", "festive",
        "nutcracker", "snow globe", "icicle",
        # NOT bare "decor"/"decoration": they belong to Home Décor, and "decor"
        # matched the brand name "Yarra-Decor" on a bedside lamp. The holiday nouns
        # above already catch "Halloween Decorations" via "halloween".
    ),
}

# Terms that disqualify regardless of a positive hit. These are products that keep
# bleeding in from neighbouring best-seller nodes and are simply not the category.
CATEGORY_EXCLUDE: dict[str, tuple[str, ...]] = {
    "Home Storage": ("water bottle", "tumbler", "lunch bag", "mug", "straw",
                     "ant killer", "insect", "air freshener"),
    "Home": ("water bottle", "tumbler", "lunch bag", "ant killer", "insect trap",
             "ant bait", "fly trap"),
    "Bedding": ("pet bed", "dog bed", "cat bed"),
    "Sheets": ("sheet pan", "baking sheet", "dryer sheet", "sheet mask",
               "mattress topper", "mattress pad", "bed frame", "memory foam"),
    # A shower curtain is not a window treatment. Without this the blackout-curtains
    # page fills up with shower liners, which is a subtler version of the same lie.
    "Window Treatments": ("shower",),
    "Bath Linens": ("blackout", "window curtain"),
}


def _norm(title: str) -> str:
    return re.sub(r"[^a-z0-9 ]+", " ", str(title or "").lower())


def _term_in(term: str, normalised_title: str) -> bool:
    """Whole-word match, not substring.

    Substring matching put a BATHROOM SCALE, a BATHTUB mat and WASHCLOTHS on the
    Halloween list, because the Seasonal Décor term "bat" occurs inside "bathroom"
    and "bathtub". "decor" likewise matched the BRAND name "Yarra-Decor" on a bedside
    lamp. Multi-word terms ("string lights", "bath mat") still match as a phrase, but
    both ends are anchored to word boundaries.
    """
    t = _norm(term).strip()
    if not t:
        return False
    # Allow a trailing plural: "towel" must match "towels", "hanger" must match
    # "hangers". The boundary still holds, so "bat" does NOT match "bathroom" — after
    # "bat" the optional plural matches empty and the lookahead then sees "h".
    return re.search(rf"(?<![a-z0-9]){re.escape(t)}(?:e?s)?(?![a-z0-9])",
                     normalised_title) is not None

def in_category(title: str, cat_label: str) -> bool:
    """True if `title` genuinely reads as a product in `cat_label`.

    Unknown categories return True — this must never silently starve a category it
    has no opinion about. Only categories with an explicit term list are enforced.
    """
    terms = CATEGORY_TERMS.get(cat_label)
    if not terms:
        return True
    t = _norm(title)
    for bad in CATEGORY_EXCLUDE.get(cat_label, ()):
        if _term_in(bad, t):
            return False
    return any(_term_in(term, t) for term in terms)


def filter_in_category(picks: list, cat_label: str, name_key: str = "name") -> list:
    """Keep only picks whose title reads as genuinely in-category."""
    out = []
    for p in picks:
        title = p.get(name_key) or p.get("title") or ""
        if in_category(title, cat_label):
            out.append(p)
    return out


# ---------------------------------------------------------------------------
# Off-niche block, shared.
#
# `off_niche_block` in social/seasonal_themes.json listed the products that keep
# drifting into a home-organization account — Bluey bottles, bento boxes, TV mounts,
# drinkware. It was enforced when GENERATING pins, then (2026-09-14) when POSTING
# them, but never when building a HUB PAGE. So the same THERMOS kids' food jar that
# the pin pipeline refuses to publish could still be listed on
# best-home-organization-products.html.
#
# One definition, read from one file, used by every stage. A term that is off-niche
# is off-niche everywhere.
# ---------------------------------------------------------------------------
import json as _json  # noqa: E402
from pathlib import Path as _Path  # noqa: E402

_THEMES = _Path(__file__).resolve().parent.parent / "social" / "seasonal_themes.json"
_OFF_NICHE_CACHE: tuple | None = None


def off_niche_terms() -> tuple:
    global _OFF_NICHE_CACHE
    if _OFF_NICHE_CACHE is None:
        try:
            data = _json.loads(_THEMES.read_text())
            _OFF_NICHE_CACHE = tuple(
                str(t).lower() for t in (data.get("off_niche_block") or []))
        except (OSError, ValueError):
            _OFF_NICHE_CACHE = ()
    return _OFF_NICHE_CACHE


def off_niche_hit(title: str) -> str | None:
    """The blocked term this product matches, or None. Same list everywhere."""
    t = _norm(title)
    for term in off_niche_terms():
        if _norm(term) in t:
            return term
    return None


# ---------------------------------------------------------------------------
# Dead-season copy.
#
# `retired_after` in seasonal_themes.json records the last month a theme may run.
# It was only ever consulted when CHOOSING THEMES to generate against — never
# against the copy we actually wrote, and never at posting time. So in September,
# three weeks after move-in ended, this account was still publishing pins titled
# "Shower Caddy for College Dorm" and "3 Tier Rolling Storage Cart for Dorms", and
# 16 of 87 September posts mentioned dorm or college.
#
# Note the products are usually fine — floating shelves, laundry hampers, storage
# carts are evergreen. It is the ANGLE that expires. So this gates the COPY, not the
# product: the same shelf can be pinned all year, just not as "dorm room decor"
# in September.
#
# A term is dead when it appears in retired_after AND is not part of any theme for
# the current month. Checking months[] rather than only comparing month numbers is
# what makes "christmas" correctly dead in January instead of alive until next
# December.
# ---------------------------------------------------------------------------
from datetime import date as _date  # noqa: E402

_SEASON_CACHE: dict | None = None


def _season_data() -> dict:
    global _SEASON_CACHE
    if _SEASON_CACHE is None:
        try:
            _SEASON_CACHE = _json.loads(_THEMES.read_text())
        except (OSError, ValueError):
            _SEASON_CACHE = {}
    return _SEASON_CACHE


def dead_season_terms(month: int | None = None) -> tuple:
    """Retired terms that are NOT in season this month.

    Dead when BOTH hold:
      * the term is not part of any theme listed for this month, and
      * this month is past the term's retirement month.

    The second test is done modulo 12 so the year wrap works: christmas retires in
    12, and (1 - 12) % 12 == 1 makes it correctly dead in January rather than alive
    for another eleven months. A term is never dead during its own retirement month
    ((m - r) % 12 == 0), which is what keeps "fall decor" alive through November.
    """
    d = _season_data()
    retired = d.get("retired_after") or {}
    if not retired:
        return ()
    m = int(month or _date.today().month)
    live = _norm(" ".join(str(t) for t in (d.get("months") or {}).get(str(m), [])))
    out = []
    for term, last in retired.items():
        if _norm(term) in live:
            continue
        try:
            r = int(last)
        except (TypeError, ValueError):
            continue
        if (m - r) % 12 >= 1:
            out.append(term.lower())
    return tuple(out)


def dead_season_hit(text: str, month: int | None = None) -> str | None:
    """The out-of-season term this copy is targeting, or None."""
    t = _norm(text)
    for term in dead_season_terms(month):
        if _norm(term) in t:
            return term
    return None
