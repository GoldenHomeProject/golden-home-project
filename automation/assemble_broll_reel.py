#!/usr/bin/env python3
"""Assemble a real-motion roundup Reel from image-to-video B-roll clips.

The 2026-06-18 teardown found fully-synthetic AI renders cap conversion — shoppers
smell them. This is different: each scene starts from a GENUINE Amazon listing photo of
a real product, animated with subtle realistic motion (Wan 2.2 i2v) or a gentle Ken-Burns
push, so it reads as real home video. Captions/CTA are Pillow PNG overlays (local ffmpeg
here has no drawtext). NOT for Amazon's shoppable-video program (AI motion fails their
originality review) — this targets IG/YT/Pinterest, where it's allowed and where the
"obviously-AI" conversion problem actually lives.

Output: 1080x1920 H.264 MP4 ready for reel_publisher.py.
"""
from __future__ import annotations
import subprocess, sys
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

ROOT = Path.home() / "Developer/ghp-transfer/work"
ASSETS = ROOT / "automation" / "broll_assets"
PY = str(Path.home() / ".ghp-presenter/venv/bin/python")
FONT = "/System/Library/Fonts/Supplemental/Arial Bold.ttf"
W, H = 1080, 1920
GOLD = (212, 167, 69)

HOOK = "3 Cheap Kitchen Organizers That Work"
SCENES = [
    ("01_undersink.mp4",    "1.  Under-sink pull-out drawers"),
    ("02_lazysusan.mp4",    "2.  Corner cabinet lazy Susan"),
    ("03_slidingbasket.mp4","3.  Sliding cabinet basket"),
]
VO = ("Three cheap kitchen organizers that actually earn their space. "
      "First, an under-sink pull-out drawer that finally uses the dead zone around your pipes. "
      "Next, a corner cabinet lazy Susan, so nothing gets lost in the back again. "
      "And a sliding cabinet basket that brings the whole shelf out to you. "
      "All three are on our Amazon storefront. Link in bio.")
CTA = "Shop all 3  →  link in bio"


def run(cmd):
    r = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    if r.returncode:
        sys.exit(f"ffmpeg failed:\n{r.stderr.decode()[-800:]}")


def dur(p: Path) -> float:
    out = subprocess.run(["ffprobe","-v","error","-show_entries","format=duration",
                          "-of","default=nk=1:nw=1",str(p)], capture_output=True, text=True).stdout.strip()
    return float(out or 0)


def _centered(draw, y, text, font, fill, shadow=True):
    w = draw.textlength(text, font=font)
    x = (W - w) / 2
    if shadow:
        draw.text((x+3, y+3), text, font=font, fill=(0, 0, 0, 180))
    draw.text((x, y), text, font=font, fill=fill)
    return w


def _pill(draw, y, text, font, text_fill, box_fill, pad=28):
    w = draw.textlength(text, font=font)
    asc, desc = font.getmetrics()
    h = asc + desc
    x0 = (W - w) / 2 - pad
    x1 = (W + w) / 2 + pad
    draw.rounded_rectangle([x0, y - pad//2, x1, y + h + pad//2], radius=26, fill=box_fill)
    draw.text(((W - w) / 2, y), text, font=font, fill=text_fill)


def make_overlay(caption: str, show_cta: bool, out: Path):
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    f_hook = ImageFont.truetype(FONT, 46)
    f_cap = ImageFont.truetype(FONT, 60)
    f_cta = ImageFont.truetype(FONT, 52)
    # top hook in the upper letterbox (square sits ~y=420..1500)
    _centered(d, 300, HOOK, f_hook, GOLD + (255,))
    # bottom numbered caption on a translucent bar
    _pill(d, 1560, caption, f_cap, (255, 255, 255, 255), (0, 0, 0, 150))
    if show_cta:
        _pill(d, 1690, CTA, f_cta, (10, 10, 10, 255), GOLD + (245,))
    img.save(out)


def build_segment(src: Path, overlay_png: Path, out: Path, target: float):
    """Slow the source to `target` seconds (slow-mo = premium B-roll, no frozen tail),
    fill a blurred vertical canvas, and burn in the caption overlay."""
    spd = max(target / max(dur(src), 0.1), 1.0)  # only ever slow down, never speed up
    fc = (
        f"[0:v]setpts={spd:.3f}*PTS[m];"
        "[m]split[m1][m2];"
        "[m1]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,"
        "boxblur=26:2,eq=brightness=-0.10,setsar=1[bg];"
        "[m2]scale=1080:1080:flags=lanczos,setsar=1[fg];"
        "[bg][fg]overlay=(W-w)/2:(H-h)/2[base];"
        "[base][1:v]overlay=0:0:format=auto,fps=30[v]"
    )
    run(["ffmpeg","-y","-i",str(src),"-loop","1","-i",str(overlay_png),
         "-filter_complex",fc,"-map","[v]","-an","-t",f"{target:.3f}",
         "-c:v","libx264","-pix_fmt","yuv420p","-r","30",str(out)])


def main():
    ASSETS.mkdir(parents=True, exist_ok=True)
    present = [(i, clip, cap) for i, (clip, cap) in enumerate(SCENES)
               if (ASSETS / clip).exists()]
    if not present:
        sys.exit("no scene clips present")

    # VO first, so we can fit the scenes to its length (no frozen-frame tail).
    mp3 = ASSETS / "vo.mp3"; wav = ASSETS / "vo.wav"
    subprocess.run([PY,"-m","edge_tts","--voice","en-US-AvaNeural","--rate=-3%",
                    "--text",VO,"--write-media",str(mp3)], check=True)
    run(["ffmpeg","-y","-i",str(mp3),"-ar","44100","-ac","2",str(wav)])
    adur = dur(wav)
    target = (adur + 0.5) / len(present)  # +0.5s so VO finishes just before the video

    segs = []
    for n, (i, clip, cap) in enumerate(present):
        png = ASSETS / f"ov_{i}.png"
        make_overlay(cap, show_cta=(n == len(present) - 1), out=png)
        seg = ASSETS / f"seg_{i}.mp4"
        build_segment(ASSETS / clip, png, seg, target)
        segs.append(seg)
        print(f"[seg {i}] {seg.name} ({target:.1f}s)")

    lst = ASSETS / "concat.txt"
    lst.write_text("".join(f"file '{s}'\n" for s in segs))
    silent = ASSETS / "reel_silent.mp4"
    run(["ffmpeg","-y","-f","concat","-safe","0","-i",str(lst),
         "-c:v","libx264","-pix_fmt","yuv420p","-r","30",str(silent)])

    out = ROOT / "automation" / "reels" / "kitchen_organizers_roundup.mp4"
    out.parent.mkdir(parents=True, exist_ok=True)
    run(["ffmpeg","-y","-i",str(silent),"-i",str(wav),
         "-map","0:v","-map","1:a","-c:v","libx264","-pix_fmt","yuv420p",
         "-c:a","aac","-shortest",str(out)])
    print(f"[reel] {out}\n  scenes={len(segs)} per-scene={target:.1f}s "
          f"vo={adur:.1f}s size={out.stat().st_size} bytes")


if __name__ == "__main__":
    main()
