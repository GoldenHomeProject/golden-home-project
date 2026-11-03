#!/usr/bin/env python3
"""pin_formats.py — the format library beyond product / collage / how-to.

Ian, 2026-11-03: "your content is too generic and too repetitive and follows the same
format and layout". Every layout here is drawn in BOTH brand looks from one code path, so
the A/B test stays fair: identical words, only the look differs (brand_ab.variant_for).

    problem_fix  the problem in a sentence, a photo, the fix
    versus       two products side by side: "pick this if..."
    mistakes     3 buying mistakes, each with what to do instead
    size_guide   a reference table (standard sizes only, from FACTS)
    room_cart    a whole room refresh with a total price band
    checklist    5-7 checkbox lines for one job

Honesty rules hold: price bands only, real sizes only (FACTS or the listing title),
no first-person experience, no claims about the pictured item.
"""
from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw

import brand_ab as b
from brand_ab import F, W, H, M, _wrap, _fit, _cover, _round

STYLE = {
    "A": dict(bg=b.PAPER, ink=b.PINE, accent=b.MARIGOLD, panel=b.SAGE, body=b.BODY, meta=b.STONE,
              head="Bricolage-ExtraBold.ttf", txt="DMSans-Regular.ttf", bold="DMSans-Bold.ttf",
              kick="DMMono-Medium.ttf", line=1.02, radius=22),
    "B": dict(bg=b.B_WHITE, ink=b.B_INK, accent=b.B_GOLD, panel=(250, 246, 238), body=b.B_INK,
              meta=b.B_META, head="Fraunces-SemiBold.ttf", txt="WorkSans-Regular.ttf",
              bold="WorkSans-SemiBold.ttf", kick="WorkSans-SemiBold.ttf", line=1.12, radius=6),
}


def _start(v: str, kicker: str, headline: str, max_lines: int = 3, sizes=range(80, 50, -4)):
    s = STYLE[v]
    c = Image.new("RGBA", (W, H), s["bg"] + (255,))
    d = ImageDraw.Draw(c)
    if v == "A":
        d.text((M, 60), kicker.upper(), font=F(s["kick"], 22), fill=s["meta"])
        y = 100
    else:
        d.rectangle([M, 76, M + 72, 80], fill=s["accent"])
        b.b_kicker(d, 65, kicker)
        y = 104
    hf, lines, sz = _fit(d, headline, s["head"], sizes, W - 2 * M, max_lines)
    for ln in lines:
        d.text((M, y), ln, font=hf, fill=s["ink"])
        y += int(sz * s["line"])
    return c, d, s, y + 30


def _finish(c, d, v: str, out: Path, footer: str = "") -> Path:
    s = STYLE[v]
    if v == "A":
        if footer:
            d.text((M, H - 150), footer, font=F(s["bold"], 28), fill=s["ink"])
        b.a_wordmark(d, M, H - 96)
    else:
        b.b_footer(d, footer)
        b.b_wordmark(d, H - 70)
    out.parent.mkdir(parents=True, exist_ok=True)
    c.convert("RGB").save(out, "PNG", optimize=True)
    return out


def _label(d, s, v, x, y, text):
    if v == "A":
        f = F(s["kick"], 22)
        w = d.textlength(text.upper(), font=f)
        d.rounded_rectangle([x, y, x + w + 28, y + 40], radius=20, fill=s["accent"])
        d.text((x + 14, y + 8), text.upper(), font=f, fill=s["ink"])
        return y + 56
    d.text((x, y), text.upper(), font=F(s["kick"], 22), fill=s["accent"])
    return y + 40


def _para(d, s, x, y, text, size, width, max_lines=4, font=None, fill=None, gap=1.3):
    f = F(font or s["txt"], size)
    for ln in _wrap(d, text, f, width)[:max_lines]:
        d.text((x, y), ln, font=f, fill=fill or s["body"])
        y += int(size * gap)
    return y


# ------------------------------------------------------------------ formats
def problem_fix(v, kicker, headline, problem, fix, photo: Path | None, detail, band, out: Path):
    c, d, s, y = _start(v, kicker, headline, 2, range(72, 48, -4))
    y = _label(d, s, v, M, y, "The problem")
    y = _para(d, s, M, y, problem, 36, W - 2 * M, 3) + 18
    ph_h = 560
    if photo and Path(photo).exists():
        img = _cover(Image.open(photo).convert("RGB"), W - 2 * M, ph_h)
        c.alpha_composite(_round(img, s["radius"]), (M, y))
    else:
        d.rounded_rectangle([M, y, W - M, y + ph_h], radius=s["radius"], fill=s["panel"])
    y += ph_h + 26
    y = _label(d, s, v, M, y, "The fix")
    y = _para(d, s, M, y, fix, 34, W - 2 * M, 3, font=s["bold"], fill=s["ink"]) + 6
    meta = " · ".join(x for x in (detail, band.lower() if band else "") if x)
    _para(d, s, M, y, meta, 26, W - 2 * M, 1, fill=s["meta"])
    return _finish(c, d, v, out)


def versus(v, kicker, headline, left: dict, right: dict, out: Path):
    """left/right: {type, picks: [2-3 'pick this if' lines], band}"""
    c, d, s, y = _start(v, kicker, headline, 3)
    gap = 24
    cw = (W - 2 * M - gap) // 2
    top, bot = y + 10, H - 190
    for i, side in enumerate((left, right)):
        x = M + i * (cw + gap)
        if v == "A":
            d.rounded_rectangle([x, top, x + cw, bot], radius=s["radius"],
                                fill=(s["panel"] if i == 0 else (251, 236, 205)))
        else:
            d.rectangle([x, top, x + cw, bot], outline=s["accent"], width=2)
        yy = top + 28
        d.text((x + 26, yy), "Option 1" if i == 0 else "Option 2", font=F(s["kick"], 22),
               fill=s["accent"] if v == "B" else s["ink"])
        yy += 44
        yy = _para(d, s, x + 26, yy, side.get("type", ""), 46, cw - 52, 3, font=s["head"],
                   fill=s["ink"], gap=1.1) + 20
        d.text((x + 26, yy), "PICK THIS IF", font=F(s["kick"], 20), fill=s["meta"])
        yy += 38
        for p in side.get("picks", [])[:3]:
            d.ellipse([x + 26, yy + 12, x + 38, yy + 24], fill=s["accent"])
            yy = _para(d, s, x + 50, yy, p, 33, cw - 80, 4) + 22
        if side.get("band"):
            d.text((x + 26, bot - 64), side["band"], font=F(s["bold"], 34), fill=s["ink"])
    return _finish(c, d, v, out)


def mistakes(v, kicker, headline, items: list[dict], out: Path, footer="Save this before you shop."):
    """items: [{mistake, instead}] x3"""
    c, d, s, y = _start(v, kicker, headline, 3)
    avail = H - 200 - y
    per = avail // max(1, len(items[:3]))
    for i, it in enumerate(items[:3], 1):
        top = y + (i - 1) * per
        if v == "A":
            d.rounded_rectangle([M, top, W - M, top + per - 22], radius=s["radius"], fill=s["panel"])
        else:
            d.line([(M, top), (W - M, top)], fill=s["accent"], width=2)
        x0 = M + 28
        yy = top + 26
        nf = F(s["head"], 44)
        d.text((x0, yy - 4), f"{i}", font=nf, fill=s["accent"] if v == "B" else s["ink"])
        tx = x0 + 60
        yy = _para(d, s, tx, yy, it.get("mistake", ""), 32, W - M - 28 - tx, 2,
                   font=s["bold"], fill=s["ink"]) + 8
        d.text((tx, yy), "INSTEAD", font=F(s["kick"], 20), fill=s["meta"])
        _para(d, s, tx, yy + 32, it.get("instead", ""), 28, W - M - 28 - tx, 3)
    return _finish(c, d, v, out, footer)


def size_guide(v, kicker, headline, rows: list[tuple[str, str]], note: str, out: Path):
    c, d, s, y = _start(v, kicker, headline, 3)
    rh = min(140, (H - 330 - y) // max(1, len(rows)))
    y += max(0, (H - 330 - y - rh * len(rows)) // 2)
    lf, rf = F(s["bold"], 42), F(s["txt"] if v == "B" else s["kick"], 40)
    for i, (lab, val) in enumerate(rows):
        top = y + i * rh
        if v == "A" and i % 2 == 0:
            d.rounded_rectangle([M, top, W - M, top + rh - 8], radius=12, fill=s["panel"])
        if v == "B":
            d.line([(M, top + rh - 4), (W - M, top + rh - 4)], fill=s["accent"], width=1)
        cy = top + (rh - 8) // 2 - 24
        d.text((M + 24, cy), lab, font=lf, fill=s["ink"])
        d.text((W - M - 24 - d.textlength(val, font=rf), cy + 2), val, font=rf, fill=s["ink"])
    _para(d, s, M, y + len(rows) * rh + 28, note, 30, W - 2 * M, 3, fill=s["meta"])
    return _finish(c, d, v, out, "Save this for when you shop.")


def room_cart(v, kicker, headline, items: list[dict], total: str, out: Path):
    """items: [{type, why, band}] 3-5; total: e.g. 'All 4 for under $70'"""
    c, d, s, y = _start(v, kicker, headline, 3)
    rh = min(220, (H - 340 - y) // max(1, len(items[:5])))
    for i, it in enumerate(items[:5]):
        top = y + i * rh
        if v == "A":
            d.rounded_rectangle([M, top, W - M, top + rh - 16], radius=s["radius"],
                                fill=s["panel"] if i % 2 == 0 else (251, 236, 205))
        else:
            d.line([(M, top), (W - M, top)], fill=s["accent"], width=2)
        d.text((M + 26, top + 26), it.get("type", ""), font=F(s["bold"], 40), fill=s["ink"])
        _para(d, s, M + 26, top + 82, it.get("why", ""), 30, W - 2 * M - 260, 2, fill=s["meta"])
        bf = F(s["bold"], 32)
        bt = it.get("band", "")
        d.text((W - M - 26 - d.textlength(bt, font=bf), top + 30), bt, font=bf, fill=s["ink"])
    ty = y + len(items[:5]) * rh + 10
    if v == "A":
        d.rounded_rectangle([M, ty, W - M, ty + 84], radius=42, fill=s["ink"])
        tf = F(s["bold"], 34)
        d.text(((W - d.textlength(total, font=tf)) / 2, ty + 22), total, font=tf, fill=b.PAPER)
    else:
        tf = F(s["head"], 42)
        d.text(((W - d.textlength(total, font=tf)) / 2, ty + 16), total, font=tf, fill=s["accent"])
    return _finish(c, d, v, out)


def checklist(v, kicker, headline, items: list[str], out: Path, footer="Save this for later."):
    c, d, s, y = _start(v, kicker, headline, 3)
    rh = min(190, (H - 240 - y) // max(1, len(items[:7])))
    y += max(0, (H - 240 - y - rh * len(items[:7])) // 2)
    for i, it in enumerate(items[:7]):
        top = y + i * rh
        bx = M + 6
        if v == "A":
            d.rounded_rectangle([bx, top + 4, bx + 50, top + 54], radius=10, outline=s["ink"], width=4)
        else:
            d.rectangle([bx, top + 6, bx + 46, top + 52], outline=s["accent"], width=2)
        _para(d, s, bx + 72, top + 2, it, 38, W - 2 * M - 90, 2, fill=s["ink"])
    return _finish(c, d, v, out, footer)


if __name__ == "__main__":
    import sys
    o = Path(sys.argv[1] if len(sys.argv) > 1 else "/tmp/fmt")
    photo = Path(sys.argv[2]) if len(sys.argv) > 2 else None
    for v in "AB":
        problem_fix(v, "small bathroom storage ideas", "The towel that never dries",
                    "A thick towel on a single hook stays damp and starts to smell by day three.",
                    "Waffle-weave towels spread out and dry faster on the same hook.",
                    photo, "4.6 stars on Amazon", "Under $25", o / f"{v}_problem_fix.png")
        versus(v, "bedding", "Fleece or sherpa: which throw?",
               {"type": "Fleece throw", "picks": ["You want light and machine-washable", "It lives on the couch"], "band": "Under $20"},
               {"type": "Sherpa throw", "picks": ["You run cold at night", "You want a thick, plush feel"], "band": "Under $30"},
               o / f"{v}_versus.png")
        mistakes(v, "window treatments", "3 mistakes people make buying blackout curtains",
                 [{"mistake": "Buying panels the exact width of the window", "instead": "Get panels that add up to about twice the window width so they close fully."},
                  {"mistake": "Hanging the rod right on the frame", "instead": "Mount it a few inches above and wider than the frame so light can't leak at the edges."},
                  {"mistake": "Skipping the lining check", "instead": "Look for 'blackout' in the listing, not just 'room darkening'."}],
                 o / f"{v}_mistakes.png")
        size_guide(v, "sheet sizes", "Mattress sizes, in inches",
                   [("Twin", "38 x 75"), ("Twin XL", "38 x 80"), ("Full", "54 x 75"), ("Queen", "60 x 80"),
                    ("King", "76 x 80"), ("California King", "72 x 84")],
                   "Standard US mattress sizes. Check pocket depth against your mattress height too.",
                   o / f"{v}_size_guide.png")
        room_cart(v, "bathroom refresh", "Refresh a small bathroom for under $60",
                  [{"type": "Waffle shower curtain", "why": "Hotel look, machine washable", "band": "Under $15"},
                   {"type": "Rust-proof hooks", "why": "12 in the pack", "band": "Under $10"},
                   {"type": "Bath mat", "why": "Non-slip backing", "band": "Under $20"},
                   {"type": "Hand towels", "why": "6-pack, cotton", "band": "Under $15"}],
                  "All 4 for under $60", o / f"{v}_room_cart.png")
        checklist(v, "guest room", "Guest room checklist before the holidays",
                  ["Fresh sheets on the bed, a spare set in the closet", "An extra blanket within reach",
                   "Empty hangers and one clear drawer", "A night light for the hallway",
                   "Phone charger by the bed", "A small tray for keys and glasses"],
                  o / f"{v}_checklist.png")
    print("ok")
