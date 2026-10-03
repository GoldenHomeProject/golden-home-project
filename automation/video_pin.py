#!/usr/bin/env python3
"""video_pin.py — a Pinterest VIDEO pin: our product-pin layout with real footage in the card.

Why (2026-10-02)
----------------
Ian asked for higher-quality visuals at $0. Free AI video tiers either forbid commercial
use or cap at 480p with a watermark, and AI footage of a product can show features the
product does not have. Pexels videos are real HD footage, free for commercial use,
modification allowed — so the motion comes from a real home, and the pin keeps exactly
the same honest framing as our photo pins: a scene of the CATEGORY, never claimed to be
the item.

Rules that come from the Pexels license and our own history:
  * No identifiable faces. The license forbids implying a person in the footage endorses
    our product. Every candidate gets one frame checked by Claude before use.
  * The clip must actually show the thing (a blanket for a blanket). Our photo pins
    shipped a whisky bar for a Halloween scarf because nobody looked at the image.
  * Brand-safe and bright, like the photo pins.

Output: 1000x1500 (2:3) H.264, 6-8 s, silent, the product pin layout around a moving card.
Any failure returns None and the caller ships the still pin instead.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from urllib import parse, request

sys.path.insert(0, str(Path(__file__).parent))
from brand import PIN_W, PIN_H  # noqa: E402
from product_pin import render_product_pin  # noqa: E402

PEXELS_API_KEY = os.environ.get("PEXELS_API_KEY", "").strip()
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36")
SECS = 8
# Each Pexels clip is used once. Three frame gift pins all got clip 8947326 on 2026-10-02;
# Pinterest treats a picture it has already seen as stale, so a reused clip is a weak pin.
USED = Path.home() / ".ghp-engagement" / "pexels_video_used.json"


def _used() -> set:
    try:
        return set(json.loads(USED.read_text()))
    except (OSError, ValueError):
        return set()


def _mark_used(vid) -> None:
    u = _used() | {vid}
    USED.parent.mkdir(parents=True, exist_ok=True)
    USED.write_text(json.dumps(sorted(u)))
UNSAFE = ("bar", "pub", "whisky", "whiskey", "beer", "wine", "cocktail", "alcohol",
          "smoking", "cigarette", "casino", "bikini", "lingerie", "nude", "party")


def _search(query: str) -> list[dict]:
    if not PEXELS_API_KEY:
        print("  [video] no PEXELS_API_KEY")
        return []
    url = (f"https://api.pexels.com/videos/search?query={parse.quote(query)}"
           f"&per_page=12&size=medium")
    req = request.Request(url, headers={"Authorization": PEXELS_API_KEY, "User-Agent": UA})
    try:
        with request.urlopen(req, timeout=20) as r:
            return json.loads(r.read()).get("videos", []) or []
    except Exception as e:  # noqa: BLE001
        print(f"  [video] search failed {query!r}: {e}")
        return []


def _best_file(v: dict) -> str | None:
    """An HD rendition big enough to crop into ~880x900, small enough for the Pi."""
    files = [f for f in v.get("video_files") or []
             if f.get("file_type") == "video/mp4" and f.get("width") and f.get("height")
             and min(f["width"], f["height"]) >= 1080 and max(f["width"], f["height"]) <= 3840]
    if not files:
        return None
    files.sort(key=lambda f: abs(min(f["width"], f["height"]) - 1440))
    return files[0]["link"]


MATERIALS = ("fleece", "satin", "silk", "cotton", "linen", "knit", "velvet", "sherpa",
             "flannel", "bamboo", "microfiber", "stainless", "ceramic", "glass", "wood",
             "wooden", "bamboo", "leather", "wool", "chenille", "faux fur")
ITEMS = ("throw blanket", "blanket", "throw", "pillowcase", "pillow", "sheet", "duvet",
         "comforter", "towel", "travel mug", "mug", "tumbler", "kettle", "pitcher",
         "candle", "diffuser", "picture frame", "frame", "vase", "basket", "tray",
         "lazy susan", "jar", "coaster", "slippers", "robe", "string lights", "wreath")


def queries_for(name: str) -> list[str]:
    """Stock-footage searches from WHAT the product is, not what it is called.
    Amazon names lead with brands ("Bedsure GentleSoft Fleece…") that no stock
    library knows, so searches built from the name came back with towels and feathers."""
    n = name.lower()
    item = next((i for i in ITEMS if i in n), "")
    mat = next((m for m in MATERIALS if m in n), "")
    if not item:
        return []
    base = f"{mat} {item}".strip()
    return list(dict.fromkeys([f"{base} close up", f"{base} home", base, item]))


def _slug_words(v: dict) -> set[str]:
    return set(re.findall(r"[a-z]+", (v.get("url") or "").lower()))


def _small_file(v: dict) -> str | None:
    """Lowest rendition >= 540px — enough to judge a clip without downloading it in HD."""
    files = [f for f in v.get("video_files") or []
             if f.get("file_type") == "video/mp4" and f.get("width") and f.get("height")
             and min(f["width"], f["height"]) >= 540]
    files.sort(key=lambda f: min(f["width"], f["height"]))
    return files[0]["link"] if files else None


def _get(url: str, dest: Path) -> bool:
    try:
        with request.urlopen(request.Request(url, headers={"User-Agent": UA}), timeout=90) as r:
            dest.write_bytes(r.read())
        return True
    except Exception as e:  # noqa: BLE001
        print(f"  [video] download failed: {e}")
        return False


def _contact_sheet(src: Path, dur: float, out: Path) -> bool:
    """Three frames across the part of the clip we would use (start, middle, end), side by
    side. One frame let a clip through whose second half was a blank white wall."""
    span = min(SECS, dur)
    ts = [span * 0.12, span * 0.5, span * 0.88]
    parts = []
    for i, t in enumerate(ts):
        f = out.with_name(f"{out.stem}-{i}.jpg")
        if not _ff("-ss", f"{t:.2f}", "-i", str(src), "-frames:v", "1",
                   "-vf", "scale=480:480:force_original_aspect_ratio=increase,crop=480:480",
                   str(f)):
            return False
        parts.append(f)
    return _ff("-i", str(parts[0]), "-i", str(parts[1]), "-i", str(parts[2]),
               "-filter_complex", "[0][1][2]hstack=3", str(out))


def _judge(sheet: Path, subject: str) -> dict:
    """Claude looks at the 3-frame sheet and scores the clip as a Pinterest video."""
    try:
        from _claude_api import _load_token_file
        _load_token_file()
    except Exception:
        pass
    prompt = (
        f"Read the image file {sheet}. It is three frames (start, middle, end) from one "
        f"stock clip we might use in a Pinterest video pin for: {subject}.\n"
        "Judge strictly. Reply with ONLY a JSON object:\n"
        "{\"item_in_all_frames\": true/false — the actual OBJECT (e.g. a pillowcase on a "
        "pillow, a folded towel, a framed picture, a mug) is recognisable and prominent in "
        "ALL three frames. A close-up of fabric texture alone is FALSE; an empty wall is FALSE,\n"
        " \"material_match\": true/false — the SAME product type and material as named, not "
        "a related one: a flask or thermos is not a travel mug, an open cup is not a lidded "
        "tumbler, a chunky knit is not fleece, a towel is not a blanket. Colour does not "
        "matter. A shopper who clicks should see the kind of thing the video showed,\n"
        " \"face_visible\": true/false — any recognisable human face, even partly,\n"
        " \"score\": 1-10 — how appealing and scroll-stopping this is as a Pinterest home "
        "video: bright, styled, clean, inviting. 7 = good, 9 = magazine quality,\n"
        " \"shot\": \"wide\" or \"detail\",\n"
        " \"note\": \"<12 words>\"}")
    try:
        out = subprocess.run(["claude", "-p", "--allowedTools", "Read", "--max-turns", "3"],
                             input=prompt, capture_output=True, text=True, timeout=180).stdout
        m = re.search(r"\{.*\}", out, re.S)
        return json.loads(m.group()) if m else {}
    except Exception as e:  # noqa: BLE001
        return {"note": f"check failed: {e}"}


def _ff(*args: str) -> bool:
    r = subprocess.run(["ffmpeg", "-v", "error", "-y", *args], capture_output=True, text=True)
    if r.returncode != 0:
        print(f"  [video] ffmpeg: {r.stderr.strip()[:200]}")
    return r.returncode == 0


def clean_headline(h: str, limit: int = 58) -> str:
    """Never ship a cut-off headline ("…Set of 2 - Ultra Soft…"): drop the spec tail after
    a dash/comma when the name was truncated or is too long, then trim to whole words."""
    cut_off = bool(re.search(r"…|\.\.\.", h))
    h = re.sub(r"…|\.\.\.", "", h).strip()
    if cut_off or len(h) > limit:
        head = re.split(r"\s[-–|]\s|,", h)[0].strip()
        h = head if len(head) >= 12 else h
    while len(h) > limit:
        h = h.rsplit(" ", 1)[0]
    return h.rstrip(" -–,|:")


MIN_SCORE = 7
LEAD_SCORE = 8
MAX_JUDGED = 6


def item_headline(product_name: str, kicker: str) -> str | None:
    """'Gift Ideas Under $25: Stainless Travel Mug' — the search phrase plus WHAT the
    product is, never its brand ("Contigo Byron Vacuum-Insulated" read like a part number)."""
    n = product_name.lower()
    item = next((i for i in ITEMS if i in n), "")
    mat = next((m for m in MATERIALS if m in n), "")
    if not item or not kicker:
        return None
    return f"{kicker.title()}: {(mat + ' ' + item).strip().title()}"


def make_video_pin(queries: list[str], subject: str, headline: str, product_name: str,
                   price: str, kicker: str, out_mp4: Path, tries: int = MAX_JUDGED) -> Path | None:
    """Build the best video pin we can, or None (the caller ships the still pin).

    1. Screen up to MAX_JUDGED unused clips cheaply (small rendition, 3-frame sheet).
    2. Keep clips where the item is visible throughout, material matches, no face,
       score >= MIN_SCORE. Rank by score.
    3. Two good clips -> a two-shot edit (wide first, then detail) with a crossfade;
       one -> a single 8 s shot. Download only the winners in HD.
    """
    judged, seen = [], set()
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        for q in queries:
            if len(judged) >= tries:
                break
            for v in _search(q):
                if len(judged) >= tries:
                    break
                vid = v.get("id")
                if vid in seen or vid in _used() or (v.get("duration") or 0) < 6:
                    continue
                seen.add(vid)
                if _slug_words(v) & set(UNSAFE) or not _best_file(v):
                    continue
                small = _small_file(v)
                lo = td / f"{vid}-lo.mp4"
                if not small or not _get(small, lo):
                    continue
                sheet = td / f"{vid}-sheet.jpg"
                if not _contact_sheet(lo, float(v.get("duration") or SECS), sheet):
                    continue
                d = _judge(sheet, subject)
                ok = (d.get("item_in_all_frames") and d.get("material_match")
                      and d.get("face_visible") is False
                      and int(d.get("score") or 0) >= MIN_SCORE)
                judged.append((int(d.get("score") or 0) if ok else 0, v, d))
                print(f"  [video] pexels {vid} ({q!r}): "
                      f"{'OK ' + str(d.get('score')) if ok else 'reject'} — {str(d.get('note'))[:70]}")

        good = sorted([j for j in judged if j[0] >= MIN_SCORE], key=lambda j: -j[0])
        # The lead clip has to be genuinely strong; a second shot may be merely good.
        if not good or good[0][0] < LEAD_SCORE:
            return None
        picks = good[:2]
        # Wide shot first, detail second, when we have one of each.
        picks.sort(key=lambda j: 0 if j[2].get("shot") == "wide" else 1)
        srcs = []
        for _, v, _ in picks:
            hd = td / f"{v['id']}-hd.mp4"
            if _get(_best_file(v), hd):
                srcs.append((hd, float(v.get("duration") or SECS), v["id"]))
        if not srcs:
            return None

        overlay = render_product_pin(item_headline(product_name, kicker) or clean_headline(headline),
                                     product_name, price, None,
                                     kicker=kicker, window=True)
        x, y, w, h = overlay.info["card"]
        ov = td / "overlay.png"
        overlay.save(ov)
        grade = (f"scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h},"
                 "eq=contrast=1.04:brightness=0.03:saturation=1.07,unsharp=5:5:0.5,"
                 "fps=30,setsar=1,format=yuv420p")
        args, fc = [], ""
        if len(srcs) == 2:
            seg, xf = 4.6, 0.8                     # 4.6 + 4.6 - 0.8 = 8.4 s
            total = seg * 2 - xf
            for i, (s, dur, _) in enumerate(srcs):
                # stay inside the 8 s window the contact sheet was judged on
                args += ["-ss", "0.4", "-t", f"{seg}", "-i", str(s)]
            fc = (f"[0:v]{grade}[a];[1:v]{grade}[b];"
                  f"[a][b]xfade=transition=fade:duration={xf}:offset={seg - xf}[v];")
        else:
            s, dur, _ = srcs[0]
            total = min(SECS, dur)
            args += ["-t", f"{total}", "-i", str(s)]
            fc = f"[0:v]{grade}[v];"
        n = len(srcs)
        args += ["-i", str(ov)]
        fc += (f"color=c=white:s={PIN_W}x{PIN_H}:d={total}[bg];"
               f"[bg][v]overlay={x}:{y}:shortest=1[b];[b][{n}:v]overlay=0:0,format=yuv420p")
        out_mp4.parent.mkdir(parents=True, exist_ok=True)
        if not _ff(*args, "-filter_complex", fc, "-t", f"{total:.2f}", "-an",
                   "-c:v", "libx264", "-preset", "medium", "-crf", "18",
                   "-movflags", "+faststart", str(out_mp4)):
            return None
        for _, _, vid in srcs:
            _mark_used(vid)
        print(f"  [video] built {'two-shot' if n == 2 else 'single-shot'} "
              f"(scores {[p[0] for p in picks]}) -> {out_mp4.name}")
        return out_mp4


if __name__ == "__main__":
    # Smoke test: python3 automation/video_pin.py "fleece throw blanket" out.mp4
    q = sys.argv[1] if len(sys.argv) > 1 else "folding fleece blanket"
    out = Path(sys.argv[2] if len(sys.argv) > 2 else "/tmp/video_pin_test.mp4")
    r = make_video_pin([q, q.split()[-1]], q, "Gift Ideas Under $25: A Fleece Throw",
                       "Bedsure GentleSoft Fleece Throw Blanket", "$19.98",
                       "gift ideas under $25", out)
    print("RESULT:", r)
