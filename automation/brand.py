#!/usr/bin/env python3
"""brand.py — the single source of truth for Golden Home Project's visual identity.

Why this exists
---------------
The brand lived as constants copied into collage_pin.py and then again into
product_pin.py. Two copies of a colour and a type scale is a brand that drifts: the
moment one file gains a size or shifts a gold, the pins stop looking like each other,
and nothing fails loudly when that happens.

Every renderer imports from here. Nothing below is duplicated anywhere else.

Mirrored as a Claude Design system project so the visual spec and the code cannot
disagree — see docs/design/ for the previews that are synced.
"""
from __future__ import annotations

from pathlib import Path

from PIL import ImageFont

# ---------------------------------------------------------------- canvas
PIN_W, PIN_H = 1000, 1500          # Pinterest 2:3, the ratio it gives most height to
MARGIN = 60

# ---------------------------------------------------------------- colour roles
# Named by ROLE, not by hue, so a future palette change does not require renaming.
GOLD = (212, 167, 69)     # accent: rules, kicker square, footer domain, number badges
CREAM = (245, 242, 236)   # the text band — a calm zone type can sit on
INK = (18, 18, 18)        # headline
GREY = (120, 118, 114)    # secondary text: "Updated September 2026"
MUTED = (90, 88, 84)      # kicker + supporting caption
WHITE = (255, 255, 255)   # footer, price chips
PLACEHOLDER = (236, 233, 227)   # stands in for a missing photo

# ---------------------------------------------------------------- type scale
# One scale for every surface. Sizes were previously chosen per-file, which is how a
# 25px caption ended up next to a 26px one doing the same job.
TYPE = {
    "headline": 82,     # the line Pinterest ranks and a scroller reads first
    "price": 40,        # highest-converting fact in a $5-35 niche
    "footer": 31,       # goldenhomeproject.com
    "badge": 30,        # collage 01..04
    "caption": 25,      # product name under the gold rule
    "kicker": 24,       # category label, upper-case
    "meta": 21,         # "Updated September 2026"
}

# ---------------------------------------------------------------- layout
BAND = {
    "collage_head": 0.27,     # collage: fixed, the 2x2 grid needs the room
    "product_head_min": 0.20,  # product pin: measured from its own text, clamped
    "product_head_max": 0.40,
    "foot": 0.11,
    "collage_foot": 0.13,
}
RADIUS = {"card": 22, "cell": 20, "chip": 30}

# ---------------------------------------------------------------- fonts
# The Pi has Liberation; CI has Inter/Open Sans. Same string measures ~20% wider in
# one than the other, which is how published text ran off-frame — so every renderer
# MEASURES rather than assuming, and they all start from this same candidate list.
FONT_BOLD = [
    "/usr/share/fonts/truetype/inter/Inter-Bold.ttf",
    "/usr/share/fonts/truetype/open-sans/OpenSans-Bold.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
]
FONT_REG = [
    "/usr/share/fonts/truetype/inter/Inter-Regular.ttf",
    "/usr/share/fonts/truetype/open-sans/OpenSans-Regular.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
]


def font(size: int, bold: bool = True):
    for p in (FONT_BOLD if bold else FONT_REG):
        if Path(p).exists():
            return ImageFont.truetype(p, size)
    return ImageFont.load_default()


def hex_of(rgb: tuple) -> str:
    return "#%02X%02X%02X" % rgb
