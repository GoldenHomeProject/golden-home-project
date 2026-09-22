#!/usr/bin/env python3
"""product_pin.py — the single-product pin, rebuilt in the collage's design language.

Why this exists
---------------
Most of what GHP publishes is a single-product pin, and it was the one format that
never got a design pass. It set the headline, the product name and the price CENTRED
on top of the photo behind a gradient scrim. On a real pin that meant the headline
landed across pillows, a hanging lamp, dangling cords and a wall outlet — three text
sizes stacked in the middle of a busy image with nothing to separate them from it.

The collage pin, which did get a design pass (2026-09-10), is visibly better for one
structural reason: **the text never sits on the photo.** It owns a band of its own.
Everything else — the kicker with its gold square, the left-aligned editorial headline,
the gold rule, the clean footer — follows from having that zone.

So this applies the same rules to one product:

  * A CREAM HEADER BAND holds all the type. Guaranteed contrast, no scrim needed, and
    no chance of a word landing on a lamp.
  * LEFT-ALIGNED headline. Reads as editorial and gives long product names a stable
    ragged edge instead of a wobbling centre.
  * The PHOTO is a rounded card below the band, cropped to fill, brightened. It is the
    product's job to be interesting; it does not also have to be a text background.
  * The PRICE is a chip on the photo — the single highest-converting fact we have in a
    $5-35 niche, and it stays legible because it sits in a solid pill.
  * FOOTER matches the collage exactly, so a viewer who sees both recognises the brand.
"""
from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageEnhance

from collage_pin import (PIN_W, PIN_H, GOLD, CREAM, INK, GREY, WHITE,
                         MARGIN, _font, _fit_lines, _cover, _rounded)

# The header band is MEASURED, not fixed. A fixed 34% left ~300px of empty cream under
# a two-line headline, which reads as an unfinished layout. The band is now sized to its
# own content and the photo takes whatever is left, so a one-line headline gets a bigger
# picture and a three-line one still breathes.
HEAD_MIN = int(PIN_H * 0.20)
HEAD_MAX = int(PIN_H * 0.40)
FOOT_H = int(PIN_H * 0.11)


def render_product_pin(headline: str, product_name: str, price: str,
                       photo: Path | None, kicker: str = "", updated: str = "",
                       footer: str = "goldenhomeproject.com") -> Image.Image:
    canvas = Image.new("RGB", (PIN_W, PIN_H), WHITE)
    draw = ImageDraw.Draw(canvas)

    # ---- measure the type block before drawing anything ----------------------
    hf, lines = _fit_lines(headline, 82, PIN_W - 2 * MARGIN)
    lines = lines[:3]
    line_h = int(hf.size * 1.05)
    block = 54                                   # top padding
    block += 46 if kicker else 0                 # kicker row
    block += line_h * len(lines)                 # headline
    block += 23 + 30                             # gold rule + supporting line
    head_h = max(HEAD_MIN, min(HEAD_MAX, block + 40))   # + bottom padding

    # ---- header band: every piece of type lives here -------------------------
    draw.rectangle([(0, 0), (PIN_W, head_h)], fill=CREAM)
    x0, y = MARGIN, 54

    if kicker:
        kf = _font(24)
        draw.rectangle([(x0, y + 4), (x0 + 18, y + 22)], fill=GOLD)
        draw.text((x0 + 32, y), kicker.upper()[:34], font=kf, fill=(90, 88, 84))
        y += 46

    for ln in lines:
        draw.text((x0, y), ln, font=hf, fill=INK)
        y += line_h

    # gold rule + the product's own name, small, as the supporting line
    draw.rectangle([(x0, y + 18), (x0 + 92, y + 23)], fill=GOLD)
    if product_name:
        sf = _font(25, bold=False)
        # one line only — this is a caption, not the headline
        name = product_name
        while name and sf.getlength(name) > PIN_W - 2 * MARGIN - 120:
            name = name[:-1]
        if name != product_name:
            name = name.rstrip(" ,-–") + "…"
        draw.text((x0 + 112, y + 4), name, font=sf, fill=(90, 88, 84))

    # ---- photo card ----------------------------------------------------------
    card_top = head_h + 24
    card_h = PIN_H - FOOT_H - card_top - 24
    card_w = PIN_W - 2 * MARGIN
    if photo and Path(photo).exists():
        im = Image.open(photo).convert("RGB")
        # Our pins were consistently dark and muddy; Pinterest rewards bright and airy.
        im = ImageEnhance.Brightness(im).enhance(1.14)
        im = ImageEnhance.Contrast(im).enhance(1.05)
        im = _cover(im, card_w, card_h)
    else:
        im = Image.new("RGB", (card_w, card_h), (236, 233, 227))
    rounded = _rounded(im, 22)
    canvas.paste(rounded, (MARGIN, card_top), rounded)

    # price chip, bottom-left of the photo
    if price:
        pf = _font(40)
        tw = pf.getlength(price)
        bx, by = MARGIN + 26, card_top + card_h - 84
        draw.rounded_rectangle([(bx, by), (bx + tw + 44, by + 60)], radius=30, fill=WHITE)
        draw.text((bx + 22, by + 8), price, font=pf, fill=INK)

    # ---- footer, identical to the collage so the brand reads as one -----------
    fy = PIN_H - FOOT_H
    draw.rectangle([(0, fy), (PIN_W, PIN_H)], fill=WHITE)
    ff = _font(31)
    draw.text(((PIN_W - ff.getlength(footer)) / 2, fy + 34), footer, font=ff, fill=GOLD)
    if updated:
        uf = _font(21, bold=False)
        draw.text(((PIN_W - uf.getlength(updated)) / 2, fy + 78), updated,
                  font=uf, fill=GREY)

    return canvas


def build_product_pin(headline: str, product_name: str, price: str,
                      photo: Path | None, out_path: Path,
                      kicker: str = "", updated: str = "",
                      footer: str = "goldenhomeproject.com") -> Path:
    """Render and save. Thin wrapper so callers that want a file keep working."""
    img = render_product_pin(headline, product_name, price, photo,
                             kicker=kicker, updated=updated, footer=footer)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(out_path, "PNG", optimize=True)
    return out_path
