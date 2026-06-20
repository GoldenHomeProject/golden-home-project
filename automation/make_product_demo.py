#!/usr/bin/env python3
"""Single-product shoppable demo video for the Amazon Influencer storefront.

Amazon's onsite-commission videos convert best as clean product demos showing
the REAL product (not an AI face). This builds a 1080x1920 demo from a product's
real Amazon listing photo + a Ken-Burns zoom + benefit captions + price chip +
Ava voiceover. ffmpeg-only (no LTX/HF) so it's fast and avoids the synthetic-face
conversion problem flagged in the 2026-06-18 teardown.

Usage:  make_product_demo.py <ASIN> [--name "..."] [--out path.mp4]
Pulls product name + verified_price from the dm_keyword_registry; image from
social/product_images/<ASIN>.jpg.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path.home() / "golden-home-project"
PRES = Path.home() / ".ghp-presenter"
IMAGES = ROOT / "social" / "product_images"
REGISTRY = ROOT / "social" / "dm_keyword_registry.json"
FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
PY = str(PRES / "venv" / "bin" / "python")

# Per-ASIN demo copy: hook + 2-3 benefit captions + the spoken script.
# Honest, specific, no fabricated personal claims. Captions are short for muted
# viewers; the VO is the same content spoken naturally.
DEMOS = {
    "B0D176VGXZ": {
        "hook": "The Under-Sink Cabinet Fix",
        "captions": ["Adjusts around the pipes", "Two pull-out drawers", "Wasted space, reclaimed"],
        "vo": "The under-sink cabinet is the most wasted space in the kitchen. This "
              "expandable organizer adjusts around the pipes, and the two pull-out "
              "drawers turn that dead zone into real, reachable storage. Four point "
              "seven stars. Tap to see it on Amazon.",
    },
    "B0B3WSZ3QP": {
        "hook": "Stop Digging in Corner Cabinets",
        "captions": ["One spin, not a dig", "Corners & condiments", "Nothing expires in the back"],
        "vo": "Corner cabinets are where things expire forgotten in the back. A lazy "
              "susan turntable brings the whole back row to your hand with one spin. "
              "Four point seven stars, under twenty dollars. Tap to see it on Amazon.",
    },
    "B01M0TS64K": {
        "hook": "Turn a Deep Cabinet Into Drawers",
        "captions": ["Two pull-out baskets", "See everything at once", "Best for deep cabinets"],
        "vo": "Deep cabinets swallow everything at the back. These two sliding chrome "
              "baskets turn one dark cabinet into two drawers you can actually see "
              "into. Six thousand five-star ratings. Tap to see it on Amazon.",
    },
    "B0BXSMJK86": {
        "hook": "The $8 Upgrade That Ties It Together",
        "captions": ["Grips so nothing slides", "Protects every shelf", "Cuts to size in seconds"],
        "vo": "This is the cheapest upgrade that makes everything else look finished. "
              "Non-slip liner grips so jars and bottles stop sliding when you open a "
              "drawer, and it cuts to size with scissors in seconds. Four point seven "
              "stars, just eight dollars. Tap to shop on Amazon.",
    },
    "B08CYBPMJC": {
        "hook": "Hotel Towels for Under $40",
        "captions": ["600 GSM Turkish cotton", "Soft and quick-drying", "Over 26,000 ratings"],
        "vo": "Upgrade the most-used thing in your bathroom. This four-piece Turkish "
              "cotton set is six hundred G S M, soft, absorbent, and quick-drying, "
              "with over twenty-six thousand ratings. Under forty dollars. Tap to "
              "shop on Amazon.",
    },
    "B01FXN3E74": {
        "hook": "Cleaner Water, No Plumbing",
        "captions": ["Filters as you pour", "10-cup, fits the fridge", "Cuts the bottle habit"],
        "vo": "Better-tasting water without a plumber or a single plastic bottle. "
              "This ten-cup Brita pitcher filters as you pour and fits right in the "
              "fridge door. Four point six stars, under thirty dollars. Tap to shop "
              "on Amazon.",
    },
    "B088WYYH85": {
        "hook": "Stop Waking Up Sweaty",
        "captions": ["Lightweight waffle weave", "Breathable for hot sleepers", "Queen size"],
        "vo": "If you sleep hot, this is the fix. A lightweight waffle-weave blanket "
              "that breathes instead of trapping heat, so you stop waking up sweaty. "
              "Four point five stars, under forty dollars for a queen. Tap to shop "
              "on Amazon.",
    },
    "B099NTSWD9": {
        "hook": "Make Food Last 5x Longer",
        "captions": ["Seals out air & freezer burn", "Frees up pantry space", "Pays for itself"],
        "vo": "The one kitchen upgrade that pays itself back. Vacuum-sealing pantry "
              "staples and freezer portions cuts food waste and frees the shelf space "
              "bulky bags hog. Four point five stars. Tap to shop on Amazon.",
    },
    "B0CVVVNB9L": {
        "hook": "Refresh a Room for $17",
        "captions": ["Set of 4 covers", "Boho sage corduroy", "Fits 18x18 inserts"],
        "vo": "The fastest way to refresh a room without buying new furniture. This "
              "set of four boho sage corduroy covers fits standard eighteen-inch "
              "inserts and swaps your whole look in minutes. Under seventeen dollars. "
              "Tap to shop on Amazon.",
    },
    "B07Y39ZXV7": {
        "hook": "Double Your Closet Space",
        "captions": ["Slim non-slip velvet", "Clothes stop sliding off", "4.8 stars"],
        "vo": "These slim velvet hangers take up a fraction of the space of plastic "
              "ones, and the non-slip surface means clothes stop sliding to the floor. "
              "Four point eight stars, the highest-rated pick here. Tap to shop on "
              "Amazon.",
    },
}


def sh(cmd):
    print("+ ffmpeg ...", file=sys.stderr)
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def make_voice(text: str, out_wav: Path):
    mp3 = out_wav.with_suffix(".mp3")
    subprocess.run([PY, "-m", "edge_tts", "--voice", "en-US-AvaNeural",
                    "--rate=-3%", "--text", text, "--write-media", str(mp3)], check=True)
    subprocess.run(["ffmpeg", "-y", "-i", str(mp3), "-ar", "44100", "-ac", "2", str(out_wav)],
                   check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def _esc(s: str) -> str:
    s = "".join(c for c in s if c.isalnum() or c in " .,!?$&'-")
    return s.replace("'", "’").replace(":", "\\:").replace(",", "\\,")


def build(asin: str, name: str, price: str, out_mp4: Path):
    demo = DEMOS.get(asin)
    if not demo:
        raise SystemExit(f"no demo copy for {asin}; add it to DEMOS")
    img = IMAGES / f"{asin}.jpg"
    if not img.exists():
        raise SystemExit(f"no product image at {img}")

    wav = PRES / "out" / f"demo_{asin}.wav"
    make_voice(demo["vo"], wav)
    dur = float(subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=nk=1:nw=1", str(wav)],
        capture_output=True, text=True).stdout.strip() or "14")
    dur = max(dur + 0.4, 6.0)

    frames = int(dur * 30)
    # Product image: scale to fit, slow Ken-Burns zoom, on a clean dark brand card.
    vf = (
        f"[1:v]scale=1000:-1:flags=lanczos,"
        f"zoompan=z='min(zoom+0.0010,1.12)':d={frames}:x='iw/2-(iw/zoom/2)':"
        f"y='ih/2-(ih/zoom/2)':s=1000x1000:fps=30[pz];"
        f"color=c=0x0a0a0a:s=1080x1920:d={dur}[bg];"
        f"[bg][pz]overlay=(W-w)/2:330[v0];"
        # gold hook at top
        f"[v0]drawtext=fontfile={FONT}:text='{_esc(demo['hook'])}':fontsize=58:"
        f"fontcolor=0xd4a745:x=(w-text_w)/2:y=150[v1];"
        # product name band under image
        f"[v1]drawtext=fontfile={FONT}:text='{_esc(name[:38])}':fontsize=38:"
        f"fontcolor=white:x=(w-text_w)/2:y=1360[v2];"
        # price chip
        f"[v2]drawtext=fontfile={FONT}:text='{_esc(price)}':fontsize=60:fontcolor=white:"
        f"box=1:boxcolor=0x1B7F4D@0.95:boxborderw=18:x=(w-text_w)/2:y=1430[v3]"
    )
    # timed benefit captions across the lower third
    caps = demo["captions"]
    per = (dur - 1.0) / max(len(caps), 1)
    cur = "v3"
    for i, c in enumerate(caps):
        t0, t1 = 0.5 + i * per, 0.5 + (i + 1) * per
        nxt = f"c{i}"
        vf += (f";[{cur}]drawtext=fontfile={FONT}:text='{_esc(c)}':fontsize=52:"
               f"fontcolor=white:borderw=4:bordercolor=black:box=1:boxcolor=black@0.45:"
               f"boxborderw=16:x=(w-text_w)/2:y=1600:"
               f"enable='between(t,{t0:.2f},{t1:.2f})'[{nxt}]")
        cur = nxt
    # CTA last 2.5s
    vf += (f";[{cur}]drawtext=fontfile={FONT}:text='Tap to shop on Amazon':fontsize=46:"
           f"fontcolor=0x0a0a0a:box=1:boxcolor=0xd4a745@0.95:boxborderw=16:"
           f"x=(w-text_w)/2:y=1740:enable='gte(t,{max(dur-2.5,0):.2f})'[vout]")

    sh(["ffmpeg", "-y", "-i", str(wav), "-loop", "1", "-i", str(img),
        "-filter_complex", vf, "-map", "[vout]", "-map", "0:a",
        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac",
        "-t", f"{dur:.2f}", str(out_mp4)])
    print(f"[demo] wrote {out_mp4} ({dur:.1f}s)")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("asin")
    ap.add_argument("--name", default="")
    ap.add_argument("--out", default="")
    args = ap.parse_args()
    reg = json.loads(REGISTRY.read_text())
    entry = next((e for e in reg.get("entries", []) + reg.get("vetted", [])
                  if e.get("asin") == args.asin), {})
    name = args.name or entry.get("product_name", args.asin).split("(")[0].strip()
    price = entry.get("verified_price", "")
    out = Path(args.out) if args.out else (PRES / "out" / f"demo_{args.asin}.mp4")
    build(args.asin, name, price, out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
