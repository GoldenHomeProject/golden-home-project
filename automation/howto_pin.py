#!/usr/bin/env python3
"""howto_pin.py — a how-to / checklist pin in the brand system (no photo needed).

Why: Pinterest saves how-to and checklist graphics far more than single product photos,
and saves drive distribution. Ours had 0 saves across 123 pins (2026-10-09). This renders
a numbered tip card: kicker, headline, 3-5 steps with gold number badges, and a product
callout at the bottom that the pin links to.

    render_howto(headline, kicker, steps, callout, price, out_path)
"""
from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).parent))
from brand import (PIN_W, PIN_H, GOLD, CREAM, INK, MUTED, WHITE, MARGIN, TYPE,  # noqa: E402
                   price_band, font as _font)


def _wrap(draw, text, f, max_w):
    words, lines, cur = text.split(), [], ""
    for w in words:
        t = (cur + " " + w).strip()
        if draw.textlength(t, font=f) <= max_w:
            cur = t
        else:
            lines.append(cur); cur = w
    if cur:
        lines.append(cur)
    return lines


def render_howto(headline: str, kicker: str, steps: list[str], callout: str, price: str,
                 out_path: Path, footer: str = "goldenhomeproject.com") -> Path:
    img = Image.new("RGB", (PIN_W, PIN_H), CREAM)
    d = ImageDraw.Draw(img)
    x0, y = MARGIN, 70
    kf = _font(TYPE["kicker"])
    d.rectangle([(x0, y + 4), (x0 + 18, y + 22)], fill=GOLD)
    d.text((x0 + 32, y), kicker.upper(), font=kf, fill=MUTED)
    y += 56
    # headline: shrink to fit 3 lines
    for size in range(84, 50, -4):
        hf = _font(size)
        hl = _wrap(d, headline, hf, PIN_W - 2 * MARGIN)
        if len(hl) <= 3:
            break
    for ln in hl:
        d.text((x0, y), ln, font=hf, fill=INK)
        y += int(size * 1.08)
    y += 18
    d.rectangle([(x0, y), (x0 + 92, y + 6)], fill=GOLD)
    y += 46

    # steps: white cards with a gold number badge
    foot_h = 250
    avail = PIN_H - foot_h - y - 20
    card_gap = 18
    sf = _font(36, bold=False)
    bodies = [_wrap(d, s, sf, PIN_W - 2 * MARGIN - 130) for s in steps]
    line_h = 46
    heights = [max(110, 40 + line_h * len(b)) for b in bodies]
    scale = min(1.0, (avail - card_gap * (len(steps) - 1)) / sum(heights))
    if scale < 1.0:   # tighten type if it would not fit
        sf = _font(31, bold=False); line_h = 40
        bodies = [_wrap(d, s, sf, PIN_W - 2 * MARGIN - 130) for s in steps]
        heights = [max(96, 34 + line_h * len(b)) for b in bodies]
    nf = _font(40)
    # Fill the column: share any leftover height between the cards (taller cards read
    # calmer than a stack with an empty band under it), capped so 2-step pins stay sane.
    spare = avail - sum(heights) - card_gap * (len(steps) - 1)
    if spare > 0:
        grow = min(spare // len(steps), 70)
        heights = [h + grow for h in heights]
        y += max(0, (spare - grow * len(steps)) // 2)
    for i, (body, h) in enumerate(zip(bodies, heights), 1):
        d.rounded_rectangle([(x0, y), (PIN_W - MARGIN, y + h)], radius=22, fill=WHITE)
        cx, cy = x0 + 56, y + h // 2
        d.ellipse([(cx - 32, cy - 32), (cx + 32, cy + 32)], fill=GOLD)
        num = str(i)
        d.text((cx - d.textlength(num, font=nf) / 2, cy - 24), num, font=nf, fill=WHITE)
        ty = y + (h - line_h * len(body)) // 2
        for ln in body:
            d.text((x0 + 118, ty), ln, font=sf, fill=INK)
            ty += line_h
        y += h + card_gap

    # product callout band
    fy = PIN_H - foot_h
    d.rectangle([(0, fy), (PIN_W, PIN_H)], fill=INK)
    cf = _font(30, bold=False)
    d.text((x0, fy + 42), "THE ONE THAT MAKES STEP 3 EASY", font=_font(22), fill=GOLD)
    cl = _wrap(d, callout, _font(40), PIN_W - 2 * MARGIN - 220)[:2]
    ty = fy + 80
    for ln in cl:
        d.text((x0, ty), ln, font=_font(40), fill=CREAM)
        ty += 50
    price = price_band(price) if price else price   # bands, never exact prices
    if price:
        pf = _font(TYPE["price"])
        tw = d.textlength(price, font=pf)
        bx = PIN_W - MARGIN - tw - 44
        d.rounded_rectangle([(bx, fy + 84), (bx + tw + 44, fy + 144)], radius=30, fill=GOLD)
        d.text((bx + 22, fy + 92), price, font=pf, fill=INK)
    ff = _font(TYPE["footer"])
    d.text(((PIN_W - d.textlength(footer, font=ff)) / 2, PIN_H - 62), footer, font=ff, fill=GOLD)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(out_path, "PNG", optimize=True)
    return out_path


if __name__ == "__main__":
    render_howto(
        "4 Under-Sink Fixes That Actually Work",
        "under sink organization",
        ["Measure around the drain pipe before you buy anything — most bins ignore it.",
         "Daily cleaners in front, backups behind. You stop unloading everything.",
         "Use a two-tier pull-out so the back row comes to you.",
         "Stick a hook on the door for gloves and a brush."],
        "2-Tier Sliding Under-Sink Organizer", "$24.99",
        Path(sys.argv[1] if len(sys.argv) > 1 else "/tmp/howto_sample.png"))
    print("ok")
