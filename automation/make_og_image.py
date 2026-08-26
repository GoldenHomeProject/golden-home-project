#!/usr/bin/env python3
"""make_og_image.py — build the site's default social share image.

No page on the site had an og:image. When someone saves one of our pages to Pinterest,
or shares it anywhere, there is no image attached — and an imageless save is effectively
a dead save on a visual platform. Every hub and post now points at this card as a
fallback, so a share always carries something branded and legible.

1200x630 is the standard Open Graph size; Pinterest, Facebook and X all read it.

    python3 automation/make_og_image.py
"""
from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "images" / "og-default.jpg"

W, H = 1200, 630
BG = (10, 10, 10)
GOLD = (212, 167, 69)
CREAM = (240, 236, 228)
MUTED = (168, 164, 160)

FONT_DIRS = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
]


def font(size: int, bold: bool = False):
    path = FONT_DIRS[0] if bold else FONT_DIRS[1]
    try:
        return ImageFont.truetype(path, size)
    except OSError:
        return ImageFont.load_default()


def centred(draw, text, f, y, fill):
    w = draw.textbbox((0, 0), text, font=f)[2]
    draw.text(((W - w) // 2, y), text, font=f, fill=fill)


def main() -> int:
    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)

    # Gold rule top and bottom — matches the site's accent.
    d.rectangle([0, 0, W, 8], fill=GOLD)
    d.rectangle([0, H - 8, W, H], fill=GOLD)

    centred(d, "GOLDEN HOME PROJECT", font(46, bold=True), 150, CREAM)
    centred(d, "Home organization finds that actually work", font(34), 250, MUTED)
    centred(d, "Verified best-sellers · real prices · updated daily", font(28), 320, MUTED)

    # Simple credibility strip — all facts the site genuinely enforces.
    box_y = 410
    d.rounded_rectangle([140, box_y, W - 140, box_y + 90], radius=14,
                        outline=(212, 167, 69, 120), width=2)
    centred(d, "$5–$35   ·   4.5★ and up   ·   thousands of reviews",
            font(26, bold=True), box_y + 30, GOLD)

    centred(d, "goldenhomeproject.com", font(26), H - 70, MUTED)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    img.save(OUT, "JPEG", quality=88, optimize=True)
    print(f"  wrote {OUT} ({OUT.stat().st_size // 1024} KB, {W}x{H})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
