#!/usr/bin/env python3
"""collage_pin.py — build multi-product COLLAGE pins, the format Pinterest saves most.

Why this exists
---------------
Every pin GHP has ever published is a single product on a stock photo. The measured
evidence says that is the weakest format available to us:

  * Pinterest's own guidance: collage Pins are saved **2x more often** than other types.
  * Third-party case studies: collages take ~87% of saves and ~73% of impressions while
    being a minority of the pins tested.
  * For affiliate specifically, a collage "signals value and variety fast" — which is
    exactly the pitch of a $5-35 verified-picks page.

It also matches the only purchase we have ever recorded: on 2026-08-24 six clicks turned
into FOURTEEN items — one household buying a whole bathroom/bedroom set, not one thing.
A collage advertises a set; a single-product pin advertises one thing.

Design follows researched Pinterest structure rather than taste:
  * headline leads with a NUMBER and is specific ("7 Bathroom Finds Under $20"),
    4-8 words, very large, dark on a light band — vague/clever headlines underperform.
  * 2x2 product grid, generous gutters, each cell obviously a separate product.
  * price chip per cell — price is the reason this niche converts.
  * bright and airy. Our old pins were dark and muddy; Pinterest rewards the opposite.

Collage pins link to the HUB (which lists all the products), not to one ASIN — that is
the one case where a hub beats a direct /dp/ link, because the pin promises several
products and the hub is the only URL that can deliver them.
"""
from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageEnhance, ImageFont

PIN_W, PIN_H = 1000, 1500
GOLD = (212, 167, 69)
CREAM = (245, 242, 236)
INK = (18, 18, 18)
GREY = (120, 118, 114)
WHITE = (255, 255, 255)

MARGIN = 60
HEAD_H = int(PIN_H * 0.27)
FOOT_H = int(PIN_H * 0.13)

FONT_CANDIDATES_BOLD = [
    "/usr/share/fonts/truetype/inter/Inter-Bold.ttf",
    "/usr/share/fonts/truetype/open-sans/OpenSans-Bold.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
]
FONT_CANDIDATES_REG = [
    "/usr/share/fonts/truetype/inter/Inter-Regular.ttf",
    "/usr/share/fonts/truetype/open-sans/OpenSans-Regular.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
]


def _font(size: int, bold: bool = True):
    for p in (FONT_CANDIDATES_BOLD if bold else FONT_CANDIDATES_REG):
        if Path(p).exists():
            return ImageFont.truetype(p, size)
    return ImageFont.load_default()


def _fit_lines(text: str, font_px: int, max_w: int, bold=True):
    """Wrap, shrinking until every line fits. Fonts differ per machine, so measure."""
    for size in range(font_px, 30, -4):
        f = _font(size, bold)
        words, lines, cur = text.split(), [], ""
        for w in words:
            t = f"{cur} {w}".strip()
            if f.getlength(t) <= max_w:
                cur = t
            else:
                if cur:
                    lines.append(cur)
                cur = w
        if cur:
            lines.append(cur)
        if lines and max(f.getlength(l) for l in lines) <= max_w and len(lines) <= 3:
            return f, lines
    return f, lines


def _cover(img: Image.Image, w: int, h: int) -> Image.Image:
    iw, ih = img.size
    scale = max(w / iw, h / ih)
    img = img.resize((max(1, int(iw * scale)), max(1, int(ih * scale))), Image.LANCZOS)
    ox, oy = (img.size[0] - w) // 2, (img.size[1] - h) // 2
    return img.crop((ox, oy, ox + w, oy + h))


def _rounded(img: Image.Image, radius: int) -> Image.Image:
    mask = Image.new("L", img.size, 0)
    ImageDraw.Draw(mask).rounded_rectangle([(0, 0), img.size], radius=radius, fill=255)
    out = Image.new("RGBA", img.size, (0, 0, 0, 0))
    out.paste(img, (0, 0), mask)
    return out


def build_collage_pin(headline: str, subline: str, cells: list, out_path: Path,
                      footer: str = "goldenhomeproject.com",
                      updated: str = "", kicker: str = "") -> Path:
    """cells: list of dicts {"image": Path|None, "price": "$11.99"} — 4 used.

    Layout refined against a template designed in Claude Design (2026-09-10), which
    was better than the first hand-rolled version in three specific ways, all kept:
      * a KICKER label above the headline — a small-caps category line with a gold
        square. Gives the pin a searchable topic before the headline and stops the
        top band feeling empty.
      * LEFT-ALIGNED headline rather than centred — reads as editorial and confident,
        and gives long headlines a stable ragged edge instead of a wobbling centre.
      * GOLD NUMBERED BADGES on each cell (01..04) — reinforces the count promised in
        the headline, which is the thing that makes a number-led headline pay off.
    """
    canvas = Image.new("RGB", (PIN_W, PIN_H), WHITE)
    draw = ImageDraw.Draw(canvas)

    # ---- headline band -------------------------------------------------------
    draw.rectangle([(0, 0), (PIN_W, HEAD_H)], fill=CREAM)
    x0 = MARGIN
    y = 52
    if kicker:
        kf = _font(24)
        draw.rectangle([(x0, y + 4), (x0 + 18, y + 22)], fill=GOLD)
        draw.text((x0 + 32, y), kicker.upper(), font=kf, fill=(90, 88, 84))
        y += 46
    hf, lines = _fit_lines(headline, 86, PIN_W - 2 * MARGIN)
    line_h = int(hf.size * 1.04)
    for ln in lines:
        draw.text((x0, y), ln, font=hf, fill=INK)
        y += line_h
    draw.rectangle([(x0, y + 20), (x0 + 92, y + 25)], fill=GOLD)
    sf = _font(26, bold=False)
    draw.text((x0 + 112, y + 6), subline, font=sf, fill=(90, 88, 84))

    # ---- 2x2 product grid ----------------------------------------------------
    grid_top = HEAD_H + 26
    grid_h = PIN_H - FOOT_H - grid_top - 26
    gutter = 22
    cw = (PIN_W - 2 * MARGIN - gutter) // 2
    ch = (grid_h - gutter) // 2
    chip_f = _font(27)

    for i in range(4):
        cx = MARGIN + (i % 2) * (cw + gutter)
        cy = grid_top + (i // 2) * (ch + gutter)
        cell = cells[i] if i < len(cells) else {}
        src = cell.get("image")
        if src and Path(src).exists():
            im = Image.open(src).convert("RGB")
            im = ImageEnhance.Brightness(im).enhance(1.12)
            im = _cover(im, cw, ch)
        else:
            im = Image.new("RGB", (cw, ch), (236, 233, 227))
        canvas.paste(_rounded(im, 20), (cx, cy), _rounded(im, 20))

        # gold numbered badge, top-left of the cell
        nf = _font(30)
        label = f"{i + 1:02d}"
        draw.rectangle([(cx, cy), (cx + 62, cy + 58)], fill=GOLD)
        draw.text((cx + 31 - nf.getlength(label) / 2, cy + 12), label, font=nf, fill=INK)

        price = str(cell.get("price") or "").strip()
        if price:
            tw = chip_f.getlength(price)
            bx, by = cx + 16, cy + ch - 58
            draw.rounded_rectangle([(bx, by), (bx + tw + 30, by + 42)],
                                   radius=21, fill=WHITE)
            draw.text((bx + 15, by + 7), price, font=chip_f, fill=INK)

    # ---- footer --------------------------------------------------------------
    fy = PIN_H - FOOT_H
    draw.rectangle([(0, fy), (PIN_W, PIN_H)], fill=WHITE)
    ff = _font(31)
    draw.text(((PIN_W - ff.getlength(footer)) / 2, fy + 42), footer, font=ff, fill=GOLD)
    if updated:
        uf = _font(21, bold=False)
        draw.text(((PIN_W - uf.getlength(updated)) / 2, fy + 88), updated,
                  font=uf, fill=GREY)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(out_path, "PNG", optimize=True)
    return out_path


# ---------------------------------------------------------------------------
# Hub-driven collages: the products in the picture must be the products on the
# page the pin links to. Feeding it arbitrary images produces a handsome pin
# that lies about what it is selling.
# ---------------------------------------------------------------------------
HUB_HEADLINES = {
    "best-bathroom-essentials":     ("Bathroom Finds", "bathroom"),
    "best-bath-towels-and-linens":  ("Bath Towel Picks", "bath towels"),
    "best-bedding-essentials":      ("Bedding Essentials", "bedding"),
    "best-blackout-curtains":       ("Blackout Curtain Picks", "blackout curtains"),
    "best-kitchen-gadgets":         ("Kitchen Finds", "kitchen gadgets"),
    "best-storage-bins":            ("Storage Bin Picks", "storage bins"),
    "best-cleaning-supplies":       ("Cleaning Finds", "cleaning supplies"),
    "best-home-decor-finds":        ("Home Decor Finds", "home decor"),
    "best-home-organization-products": ("Organization Finds", "home organization"),
    "best-sheet-sets":              ("Sheet Set Picks", "sheet sets"),
}


def headline_for(slug: str, n: int, max_price: float | None) -> str:
    """Number-led, specific, 4-8 words — the structure Pinterest rewards."""
    label = HUB_HEADLINES.get(slug, ("Home Finds", "home"))[0]
    if max_price:
        return f"{n} {label} Under ${int(max_price) + 1}"
    return f"{n} {label} Worth Buying"
