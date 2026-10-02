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


def _frame_ok(frame: Path, subject: str) -> tuple[bool, str]:
    """One Claude look at a frame: shows the subject, no face, bright and brand-safe."""
    sys.path.insert(0, str(Path(__file__).parent))
    try:
        from _claude_api import _load_token_file
        _load_token_file()
    except Exception:
        pass
    prompt = (f"Read the image file {frame} and judge it as background footage for a "
              f"home-products Pinterest pin about: {subject}.\n"
              "Reply with ONLY a JSON object: {\"shows_subject\": true/false (true ONLY if the subject is the clear main focus, filling a good part of the frame — not a corner or background detail, AND the same product type and material the subject names — e.g. a chunky knit is NOT a fleece throw; colour does not matter), "
              "\"face_visible\": true/false, \"bright_clean_home\": true/false, "
              "\"note\": \"<10 words>\"}. face_visible is true if any person's face is "
              "recognisable, even partly. Hands and bodies without faces are fine.")
    try:
        out = subprocess.run(["claude", "-p", "--allowedTools", "Read", "--max-turns", "3"],
                             input=prompt, capture_output=True, text=True, timeout=150).stdout
        m = re.search(r"\{.*\}", out, re.S)
        d = json.loads(m.group()) if m else {}
    except Exception as e:  # noqa: BLE001
        return False, f"check failed: {e}"
    ok = bool(d.get("shows_subject")) and not d.get("face_visible", True) \
        and bool(d.get("bright_clean_home"))
    return ok, str(d.get("note") or d)[:80]


def _ff(*args: str) -> bool:
    r = subprocess.run(["ffmpeg", "-v", "error", "-y", *args], capture_output=True, text=True)
    if r.returncode != 0:
        print(f"  [video] ffmpeg: {r.stderr.strip()[:200]}")
    return r.returncode == 0


def make_video_pin(queries: list[str], subject: str, headline: str, product_name: str,
                   price: str, kicker: str, out_mp4: Path, tries: int = 4) -> Path | None:
    """Build the video pin; None means use the still pin."""
    subject_words = {w for w in re.findall(r"[a-z]+", subject.lower()) if len(w) > 3}
    seen, checked = set(), 0
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        for q in queries:
            for v in _search(q):
                if checked >= tries:
                    return None
                if v.get("id") in seen or v.get("id") in _used() or (v.get("duration") or 0) < 5:
                    continue
                seen.add(v.get("id"))
                words = _slug_words(v)
                if words & set(UNSAFE):
                    continue
                link = _best_file(v)
                if not link:
                    continue
                src = td / f"{v['id']}.mp4"
                try:
                    with request.urlopen(request.Request(link, headers={"User-Agent": UA}),
                                         timeout=60) as r:
                        src.write_bytes(r.read())
                except Exception as e:  # noqa: BLE001
                    print(f"  [video] download failed: {e}")
                    continue
                frame = td / f"{v['id']}.jpg"
                mid = min(SECS, float(v.get("duration") or SECS)) / 2
                if not _ff("-ss", f"{mid:.1f}", "-i", str(src), "-frames:v", "1",
                           "-vf", "scale=720:-2", str(frame)):
                    continue
                checked += 1
                ok, note = _frame_ok(frame, subject)
                print(f"  [video] pexels {v['id']} ({q!r}): {'OK' if ok else 'reject'} — {note}")
                if not ok:
                    continue

                overlay = render_product_pin(headline, product_name, price, None,
                                             kicker=kicker, window=True)
                x, y, w, h = overlay.info["card"]
                ov = td / "overlay.png"
                overlay.save(ov)
                dur = min(SECS, float(v.get("duration") or SECS))
                fc = (f"color=c=white:s={PIN_W}x{PIN_H}:d={dur}[bg];"
                      f"[0:v]scale={w}:{h}:force_original_aspect_ratio=increase,"
                      f"crop={w}:{h},eq=brightness=0.03:saturation=1.05,fps=30,setsar=1[v];"
                      f"[bg][v]overlay={x}:{y}:shortest=1[b];[b][1:v]overlay=0:0,format=yuv420p")
                out_mp4.parent.mkdir(parents=True, exist_ok=True)
                if _ff("-t", f"{dur}", "-i", str(src), "-i", str(ov), "-filter_complex", fc,
                       "-t", f"{dur}", "-an", "-c:v", "libx264", "-preset", "veryfast",
                       "-crf", "21", "-movflags", "+faststart", str(out_mp4)):
                    _mark_used(v.get("id"))
                    return out_mp4
    return None


if __name__ == "__main__":
    # Smoke test: python3 automation/video_pin.py "fleece throw blanket" out.mp4
    q = sys.argv[1] if len(sys.argv) > 1 else "folding fleece blanket"
    out = Path(sys.argv[2] if len(sys.argv) > 2 else "/tmp/video_pin_test.mp4")
    r = make_video_pin([q, q.split()[-1]], q, "Gift Ideas Under $25: A Fleece Throw",
                       "Bedsure GentleSoft Fleece Throw Blanket", "$19.98",
                       "gift ideas under $25", out)
    print("RESULT:", r)
