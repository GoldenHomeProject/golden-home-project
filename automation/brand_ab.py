#!/usr/bin/env python3
"""brand_ab.py — the two candidate GHP brand directions, rendered for an A/B test.

Ian, 2026-10-17 (via the marketing department): test Direction A ("Measured") against
Direction B ("Golden Hour") and pick the winner by money — revenue first, then sales,
clicks, saves, views. Spec: ~/Developer/marketing/products/ghp/BRAND_REFRESH.md.

Three formats per direction, 1000x1500:
  product(...)   one product on a stock room photo
  howto(...)     photo-free how-to (the save magnet)
  collage(...)   photo-free typographic gift guide (cannot render blank)

Shared rules: price bands only, no exact prices; stock photos only; real dimensions only
(the caller passes a dimension that literally appears in the listing, or a fit statement).
"""
from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

W, H, M = 1000, 1500, 56
FONTS = Path.home() / ".fonts" / "ghp"

# ---- Direction A, "Measured"
PINE, MARIGOLD, PAPER = (29, 58, 49), (240, 178, 59), (251, 248, 242)
SAGE, STONE, BODY = (227, 236, 230), (90, 102, 96), (63, 77, 71)
# ---- Direction B, "Golden Hour"
B_WHITE, B_GOLD, B_INK = (255, 255, 255), (200, 150, 46), (42, 38, 34)
B_META, B_WORD = (94, 85, 75), (138, 100, 23)


def F(name: str, size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(FONTS / name), size)


def _wrap(d, text, f, max_w):
    out, cur = [], ""
    for w in str(text).split():
        t = f"{cur} {w}".strip()
        if d.textlength(t, font=f) <= max_w:
            cur = t
        else:
            if cur:
                out.append(cur)
            cur = w
    if cur:
        out.append(cur)
    return out


def _fit(d, text, font_name, sizes, max_w, max_lines):
    for s in sizes:
        f = F(font_name, s)
        lines = _wrap(d, text, f, max_w)
        if len(lines) <= max_lines:
            return f, lines, s
    return f, lines[:max_lines], s


def _cover(img: Image.Image, w: int, h: int) -> Image.Image:
    sc = max(w / img.width, h / img.height)
    img = img.resize((int(img.width * sc) + 1, int(img.height * sc) + 1), Image.LANCZOS)
    x, y = (img.width - w) // 2, (img.height - h) // 2
    return img.crop((x, y, x + w, y + h))


def _round(img: Image.Image, r: int) -> Image.Image:
    mask = Image.new("L", img.size, 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, img.width, img.height], radius=r, fill=255)
    out = img.convert("RGBA")
    out.putalpha(mask)
    return out


# ============================================================ Direction A pieces
def a_tape(canvas: Image.Image, box, text: str, h: int = 84):
    """Marigold measuring strip: pine ticks along the top 22px, dimension in DM Mono."""
    x0, y0, x1 = box
    shadow = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    ImageDraw.Draw(shadow).rounded_rectangle([x0, y0 + 6, x1, y0 + 6 + h], radius=12,
                                             fill=PINE + (46,))
    canvas.alpha_composite(shadow.filter(ImageFilter.GaussianBlur(9)))
    d = ImageDraw.Draw(canvas)
    d.rounded_rectangle([x0, y0, x1, y0 + h], radius=12, fill=MARIGOLD)
    for i, x in enumerate(range(x0 + 20, x1 - 10, 28)):
        d.rectangle([x, y0, x + 2, y0 + (22 if i % 5 == 0 else 14)], fill=PINE)
    f = F("DMMono-Medium.ttf", 32)
    while d.textlength(text, font=f) > (x1 - x0 - 52) and f.size > 20:
        f = F("DMMono-Medium.ttf", f.size - 2)
    d.text((x0 + 26, y0 + h - 26 - f.size), text, font=f, fill=PINE)


def a_mark(d: ImageDraw.ImageDraw, x: int, y: int, size: int, roof=PINE, sun=MARIGOLD):
    s = size / 64
    P = lambda a, b: (x + a * s, y + b * s)  # noqa: E731
    d.pieslice([P(18, 30), P(46, 58)], 180, 360, fill=sun)          # sun, rising
    d.line([P(6, 34), P(32, 10), P(58, 34)], fill=roof, width=max(2, int(6 * s)), joint="curve")
    d.line([P(10, 46), P(54, 46)], fill=roof, width=max(2, int(6 * s)))


def a_wordmark(d, x, y, color=PINE, size=36):
    a_mark(d, x, y - 4, size + 10, roof=color)
    d.text((x + size + 22, y), "golden home", font=F("Bricolage-ExtraBold.ttf", size), fill=color)


def a_chip(d, right, y, text, fg=PAPER, bg=PINE):
    f = F("DMSans-Bold.ttf", 28)
    tw = d.textlength(text, font=f)
    d.rounded_rectangle([right - tw - 44, y, right, y + 56], radius=28, fill=bg)
    d.text((right - tw - 22, y + 11), text, font=f, fill=fg)


def a_product(headline, kicker, photo: Path | None, tape: str, band: str, out: Path) -> Path:
    c = Image.new("RGBA", (W, H), PAPER + (255,))
    d = ImageDraw.Draw(c)
    d.text((M, 56), kicker.upper(), font=F("DMMono-Medium.ttf", 22), fill=STONE)
    hf, lines, s = _fit(d, headline, "Bricolage-ExtraBold.ttf", range(88, 64, -4), W - 2 * M, 4)
    y = 100
    for ln in lines:
        d.text((M, y), ln, font=hf, fill=PINE)
        y += int(s * 1.02)
    top, bottom = y + 30, H - 140
    if photo and Path(photo).exists():
        ph = _round(_cover(Image.open(photo).convert("RGB"), W - 2 * M, bottom - top), 28)
    else:
        ph = _round(Image.new("RGB", (W - 2 * M, bottom - top), SAGE), 28)
    c.alpha_composite(ph, (M, top))
    a_tape(c, (M + 24, bottom - 84 - 28, W - M - 24), tape)
    d = ImageDraw.Draw(c)
    a_wordmark(d, M, H - 96)
    if band:
        a_chip(d, W - M, H - 104, band)
    out.parent.mkdir(parents=True, exist_ok=True)
    c.convert("RGB").save(out, "PNG", optimize=True)
    return out


def a_howto(headline, kicker, steps: list[str], tape: str, out: Path,
            footer: str = "Save this before you shop.") -> Path:
    """Tape across the top, a lettered A/B/C measuring diagram, three lettered steps."""
    c = Image.new("RGBA", (W, H), PAPER + (255,))
    a_tape(c, (0 - 12, 0 - 12, W + 12), tape, h=96)
    d = ImageDraw.Draw(c)
    d.text((M, 130), kicker.upper(), font=F("DMMono-Medium.ttf", 22), fill=STONE)
    hf, lines, s = _fit(d, headline, "Bricolage-ExtraBold.ttf", range(80, 56, -4), W - 2 * M, 3)
    y = 172
    for ln in lines:
        d.text((M, y), ln, font=hf, fill=PINE)
        y += int(s * 1.02)
    # diagram: a cabinet in Sage with A (width), B (depth), C (height) callouts
    gy, gx0, gx1, gh = y + 92, M + 120, W - M - 120, 360   # room above for the A callout
    d.rounded_rectangle([gx0, gy, gx1, gy + gh], radius=18, fill=SAGE, outline=PINE, width=5)
    d.rectangle([gx0 + 30, gy + gh * 0.55, gx1 - 30, gy + gh * 0.55 + 10], fill=PINE)
    d.rounded_rectangle([gx0 + 60, gy + 40, gx0 + 200, gy + gh * 0.55 - 10], radius=8, fill=PAPER, outline=PINE, width=3)
    lab = F("Bricolage-ExtraBold.ttf", 40)

    def tag(x, y, letter):
        d.ellipse([x - 30, y - 30, x + 30, y + 30], fill=MARIGOLD)
        d.text((x - d.textlength(letter, font=lab) / 2, y - 26), letter, font=lab, fill=PINE)
    d.line([(gx0, gy - 26), (gx1, gy - 26)], fill=PINE, width=4)
    tag((gx0 + gx1) // 2, gy - 26, "A")
    d.line([(gx1 + 40, gy), (gx1 + 40, gy + gh)], fill=PINE, width=4)
    tag(gx1 + 40, gy + gh // 2, "C")
    d.line([(gx0 - 60, gy + gh - 20), (gx0 - 10, gy + gh - 70)], fill=PINE, width=4)
    tag(gx0 - 60, gy + gh - 20, "B")
    y = gy + gh + 50
    sf = F("DMSans-Regular.ttf", 30)
    for letter, step in zip("ABC", steps[:3]):
        d.ellipse([M, y, M + 52, y + 52], fill=MARIGOLD)
        d.text((M + 26 - d.textlength(letter, font=F("DMSans-Bold.ttf", 30)) / 2, y + 8), letter,
               font=F("DMSans-Bold.ttf", 30), fill=PINE)
        ly = y + 6
        for ln in _wrap(d, step, sf, W - 2 * M - 80)[:3]:
            d.text((M + 76, ly), ln, font=sf, fill=BODY)
            ly += 40
        y = max(y + 74, ly + 22)
    d.text((M, H - 92), footer, font=F("DMSans-Bold.ttf", 30), fill=PINE)
    a_mark(d, W - M - 56, H - 104, 56)
    out.parent.mkdir(parents=True, exist_ok=True)
    c.convert("RGB").save(out, "PNG", optimize=True)
    return out


def a_collage(headline, kicker, tiles: list[dict], out: Path) -> Path:
    """Pine ground, 2x3 typographic tiles (number, type, why, price band)."""
    c = Image.new("RGB", (W, H), PINE)
    d = ImageDraw.Draw(c)
    d.text((M, 64), kicker.upper(), font=F("DMMono-Medium.ttf", 22), fill=MARIGOLD)
    hf, lines, s = _fit(d, headline, "Bricolage-ExtraBold.ttf", range(84, 56, -4), W - 2 * M, 3)
    y = 106
    for ln in lines:
        d.text((M, y), ln, font=hf, fill=PAPER)
        y += int(s * 1.02)
    gy = y + 34
    gap, cols = 20, 2
    rows = max(2, (min(len(tiles), 6) + 1) // 2)   # 4-6 tiles, no empty row
    tw = (W - 2 * M - gap) // cols
    th = (H - 140 - gy - gap * (rows - 1)) // rows
    if th > 330:   # 4 tiles: no tall empty cards; centre the grid instead
        gy += (th - 330) * rows // 2
        th = 330
    fills = [MARIGOLD, PAPER, SAGE, MARIGOLD, PAPER, SAGE]
    for i, t in enumerate(tiles[:6]):
        cx = M + (i % cols) * (tw + gap)
        cy = gy + (i // cols) * (th + gap)
        d.rounded_rectangle([cx, cy, cx + tw, cy + th], radius=22, fill=fills[i])
        d.text((cx + 26, cy + 18), f"{i + 1:02d}", font=F("Bricolage-ExtraBold.ttf", 52), fill=PINE)
        ty = cy + 90
        for ln in _wrap(d, t.get("type", ""), F("DMSans-Bold.ttf", 32), tw - 52)[:2]:
            d.text((cx + 26, ty), ln, font=F("DMSans-Bold.ttf", 32), fill=PINE)
            ty += 38
        for ln in _wrap(d, t.get("why", ""), F("DMSans-Regular.ttf", 24), tw - 52)[:2]:
            d.text((cx + 26, ty + 4), ln, font=F("DMSans-Regular.ttf", 24), fill=BODY)
            ty += 30
        if t.get("band"):
            d.text((cx + 26, cy + th - 48), t["band"].upper(), font=F("DMMono-Medium.ttf", 24), fill=PINE)
    a_wordmark(d, M, H - 96, color=PAPER)
    out.parent.mkdir(parents=True, exist_ok=True)
    c.save(out, "PNG", optimize=True)
    return out


# ============================================================ Direction B pieces
def b_wordmark(d, y):
    f = F("Fraunces-MediumItalic.ttf", 34)
    t = "Golden Home"
    d.text(((W - d.textlength(t, font=f)) / 2, y), t, font=f, fill=B_WORD)


def b_product(headline, photo: Path | None, meta: str, out: Path) -> Path:
    c = Image.new("RGB", (W, H), B_WHITE)
    if photo and Path(photo).exists():
        c.paste(_cover(Image.open(photo).convert("RGB"), W, 1000), (0, 0))
    d = ImageDraw.Draw(c)
    d.rectangle([M, 1050, M + 72, 1054], fill=B_GOLD)
    hf, lines, s = _fit(d, headline, "Fraunces-SemiBold.ttf", range(72, 48, -4), W - 2 * M, 3)
    y = 1076
    for ln in lines:
        d.text((M, y), ln, font=hf, fill=B_INK)
        y += int(s * 1.12)
    mf = F("WorkSans-Regular.ttf", 26)
    for ln in _wrap(d, meta, mf, W - 2 * M)[:2]:
        d.text((M, y + 12), ln, font=mf, fill=B_META)
        y += 34
    b_wordmark(d, H - 70)
    out.parent.mkdir(parents=True, exist_ok=True)
    c.save(out, "PNG", optimize=True)
    return out


def b_howto(headline, steps: list[str], meta: str, out: Path) -> Path:
    """Typographic: white ground, serif headline, numbered steps separated by gold rules."""
    c = Image.new("RGB", (W, H), B_WHITE)
    d = ImageDraw.Draw(c)
    d.rectangle([M, 120, M + 72, 124], fill=B_GOLD)
    hf, lines, s = _fit(d, headline, "Fraunces-SemiBold.ttf", range(76, 52, -4), W - 2 * M, 3)
    y = 150
    for ln in lines:
        d.text((M, y), ln, font=hf, fill=B_INK)
        y += int(s * 1.12)
    d.text((M, y + 10), meta, font=F("WorkSans-Regular.ttf", 26), fill=B_META)
    y += 90
    nf, sf = F("Fraunces-SemiBold.ttf", 64), F("WorkSans-Regular.ttf", 32)
    avail = H - 150 - y
    per = avail // max(1, len(steps[:4]))
    for i, step in enumerate(steps[:4], 1):
        d.line([(M, y), (W - M, y)], fill=B_GOLD, width=2)
        d.text((M, y + 24), str(i), font=nf, fill=B_GOLD)
        ly = y + 34
        for ln in _wrap(d, step, sf, W - 2 * M - 110)[:3]:
            d.text((M + 100, ly), ln, font=sf, fill=B_INK)
            ly += 44
        y += per
    b_wordmark(d, H - 70)
    out.parent.mkdir(parents=True, exist_ok=True)
    c.save(out, "PNG", optimize=True)
    return out


def b_collage(headline, tiles: list[dict], out: Path) -> Path:
    """Typographic gift guide: white ground, serif numerals, gold hairline grid."""
    c = Image.new("RGB", (W, H), B_WHITE)
    d = ImageDraw.Draw(c)
    d.rectangle([M, 100, M + 72, 104], fill=B_GOLD)
    hf, lines, s = _fit(d, headline, "Fraunces-SemiBold.ttf", range(76, 52, -4), W - 2 * M, 3)
    y = 130
    for ln in lines:
        d.text((M, y), ln, font=hf, fill=B_INK)
        y += int(s * 1.12)
    gy = y + 40
    cols = 2
    rows = max(2, (min(len(tiles), 6) + 1) // 2)
    tw = (W - 2 * M) // cols
    th = (H - 140 - gy) // rows
    if th > 330:
        gy += (th - 330) * rows // 2
        th = 330
    for r in range(rows + 1):
        d.line([(M, gy + r * th), (W - M, gy + r * th)], fill=B_GOLD, width=2)
    d.line([(M + tw, gy), (M + tw, gy + rows * th)], fill=B_GOLD, width=2)
    for i, t in enumerate(tiles[:6]):
        cx = M + (i % cols) * tw + 24
        cy = gy + (i // cols) * th + 22
        d.text((cx, cy), f"{i + 1}", font=F("Fraunces-SemiBold.ttf", 56), fill=B_GOLD)
        ty = cy + 74
        for ln in _wrap(d, t.get("type", ""), F("Fraunces-SemiBold.ttf", 32), tw - 48)[:2]:
            d.text((cx, ty), ln, font=F("Fraunces-SemiBold.ttf", 32), fill=B_INK)
            ty += 38
        for ln in _wrap(d, t.get("why", ""), F("WorkSans-Regular.ttf", 23), tw - 48)[:2]:
            d.text((cx, ty + 4), ln, font=F("WorkSans-Regular.ttf", 23), fill=B_META)
            ty += 29
        if t.get("band"):
            d.text((cx, gy + (i // cols + 1) * th - 44), t["band"], font=F("WorkSans-SemiBold.ttf", 24), fill=B_WORD)
    b_wordmark(d, H - 70)
    out.parent.mkdir(parents=True, exist_ok=True)
    c.save(out, "PNG", optimize=True)
    return out


if __name__ == "__main__":
    import sys
    o = Path(sys.argv[1] if len(sys.argv) > 1 else "/tmp/ab")
    photo = Path(sys.argv[2]) if len(sys.argv) > 2 else None
    a_product("The cabinet you avoid opening, fixed", "under sink organization", photo,
              "11.4 in wide · clears the drain pipe", "Under $25", o / "A_product.png")
    b_product("The cabinet you avoid opening, fixed", photo,
              "11.4 in wide · clears the drain pipe · under $25", o / "B_product.png")
    steps = ["Measure the width between the cabinet doors, not the cabinet.",
             "Measure depth to the drain pipe, the real limit for any bin.",
             "Measure shelf-to-ceiling height so tall bottles still stand."]
    a_howto("Measure these 3 numbers before you buy an under-sink organizer",
            "under sink organization", steps, "A · B · C — 3 numbers, 2 minutes", o / "A_howto.png")
    b_howto("Measure these 3 numbers before you buy an under-sink organizer", steps,
            "Under-sink organization · 2 minutes", o / "B_howto.png")
    tiles = [{"type": "Stainless travel mug", "why": "Leak-proof lid for the commute", "band": "Under $25"},
             {"type": "Fleece throw blanket", "why": "Couch-sized and machine washable", "band": "Under $25"},
             {"type": "Satin pillowcases", "why": "A small upgrade they won't buy themselves", "band": "Under $10"},
             {"type": "Candle warmer lamp", "why": "Flameless glow for a desk or nightstand", "band": "Under $25"},
             {"type": "Picture frame set", "why": "Gallery-wall starter, standard 8x10", "band": "Under $25"},
             {"type": "Hair towel wrap", "why": "Quick-dry, two in the pack", "band": "Under $10"}]
    a_collage("6 gifts under $25 they'll use every day", "gift guide", tiles, o / "A_collage.png")
    b_collage("Six gifts under $25 they'll use every day", tiles, o / "B_collage.png")
    print("ok")


# ============================================================ test plumbing
import hashlib as _hashlib
import re as _re


def variant_for(pin_id: str) -> str:
    """Deterministic 50/50 split by pin id: same day, boards and product mix for both arms."""
    return "A" if int(_hashlib.sha1(pin_id.encode()).hexdigest(), 16) % 2 == 0 else "B"


_SIZE = _re.compile(r"\b(Twin XL|Twin|Full|Queen|King|California King)\b", _re.I)
_DIM = _re.compile(r"(\d+(?:\.\d+)?)\s?(?:\"|''|in\b|inch(?:es)?\b|ft\b|cm\b)", _re.I)
_XBY = _re.compile(r"\b(\d+(?:\.\d+)?)\s?[xX×]\s?(\d+(?:\.\d+)?)\b")
_PACK = _re.compile(r"\b(\d+)[\s-]?(?:Pack|Pcs|Pieces|Piece|Count|Set of \d+)\b", _re.I)


def tape_text(name: str) -> str:
    """The tape's line, built ONLY from numbers/sizes that appear in the listing title.
    Never guesses: no dimension in the title -> a fit statement from the title, or none."""
    n = str(name or "")
    m = _re.search(r"(?:fits|fit)\s+(?:up\s+to\s+)?(\d+(?:\.\d+)?)\s?(?:\"|in\b|inch(?:es)?\b)\s*(?:deep)?", n, _re.I)
    if m:   # "Fits Up to 15 Inch Deep Pocket" -> a fit statement, not a bare number
        return f"fits mattresses up to {m.group(1)} in deep"
    m = _XBY.search(n)
    if m:
        return f"{m.group(1)} x {m.group(2)} in"
    m = _DIM.search(n)
    if m:
        unit = "in" if not _re.search(r"ft|cm", m.group(0), _re.I) else m.group(0).split()[-1].strip(".")
        return f"{m.group(1)} {unit}"
    m = _re.search(r"\b(\d+(?:\.\d+)?)\s?(oz|ounce|qt|quart|cup|cups|lb|lbs)\b", n, _re.I)
    if m:
        return f"{m.group(1)} {m.group(2).lower()}"
    m = _SIZE.search(n)
    if m:   # a bed size describes the product's size, not what it "fits"
        return f"{m.group(1).lower()} size"
    m = _PACK.search(n)
    if m:
        return f"{m.group(1)} in the pack"
    return ""
