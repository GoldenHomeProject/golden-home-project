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
    "Sheets": (
        "sheet", "pillowcase", "pillow case", "bedding", "mattress", "fitted",
        "flat sheet", "bed set",
    ),
    "Window Treatments": (
        "curtain", "drape", "blind", "shade", "valance", "blackout", "window",
        "rod", "grommet", "sheer",
    ),
    "Bath Linens": (
        "towel", "washcloth", "wash cloth", "bath sheet", "hand towel",
        "bath mat", "robe", "linen", "gsm",
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
    "Sheets": ("sheet pan", "baking sheet", "dryer sheet", "sheet mask"),
    # A shower curtain is not a window treatment. Without this the blackout-curtains
    # page fills up with shower liners, which is a subtler version of the same lie.
    "Window Treatments": ("shower",),
    "Bath Linens": ("blackout", "window curtain"),
}


def _norm(title: str) -> str:
    return re.sub(r"[^a-z0-9 ]+", " ", str(title or "").lower())


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
        if _norm(bad) in t:
            return False
    return any(_norm(term) in t for term in terms)


def filter_in_category(picks: list, cat_label: str, name_key: str = "name") -> list:
    """Keep only picks whose title reads as genuinely in-category."""
    out = []
    for p in picks:
        title = p.get(name_key) or p.get("title") or ""
        if in_category(title, cat_label):
            out.append(p)
    return out
