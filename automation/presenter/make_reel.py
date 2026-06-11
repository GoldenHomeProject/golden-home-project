#!/usr/bin/env python3
"""GHP AI-presenter reel pipeline with built-in human variety.

One presenter (same recurring face) but every post deliberately varies:
  - persona VARIANT image (outfit + lighting + background) via FLUX Kontext, face preserved
  - render POLISH: 'raw' (LTX-2 native, soft natural skin) or 'sharp' (GFPGAN)
so the account collectively reads as a real person, not a too-perfect studio bot.

Steps: script.txt -> Ava voice (edge-tts) -> LTX-2 talking head (HF token)
       -> [optional GFPGAN sharpen] -> vertical 1080x1920 composite.
"""
import argparse, json, random, shutil, subprocess, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "out"
VARIANTS = OUT / "variants"
TOKEN_FILE = ROOT / ".hf_token"

LTX_SPACE = "multimodalart/ltx2-audio-to-video"
PROMPT = ("A friendly young woman presenter looking directly at the camera and speaking, "
          "lips in sync with her words, calm steady upright posture, shoulders square to camera, "
          "minimal subtle head movement, natural eye blinking, relaxed natural expression, "
          "well-proportioned neck and shoulders, photorealistic portrait")
NEG = ("elongated neck, long neck, stretched neck, tilted head, distorted anatomy, warped, "
       "deformed, low quality, worst quality, blurry mouth, frozen, static")

# Recurring face, varied wardrobe/lighting/background. Canonical persona + FLUX Kontext edits.
DEFAULT_VARIANTS = [
    OUT / "persona.png",            # cream/neutral, soft studio
    VARIANTS / "blazer_evening.png",  # navy blazer, warm evening lamp
    VARIANTS / "tee_daylight.png",    # olive tee, bright window daylight
    VARIANTS / "denim_studio.png",    # light denim, clean studio
]


def sh(cmd, **kw):
    print("+", " ".join(str(c) for c in cmd))
    return subprocess.run(cmd, check=True, **kw)


def make_voice(script: Path, out_wav: Path):
    mp3 = out_wav.with_suffix(".mp3")
    sh([sys.executable, "-m", "edge_tts", "--voice", "en-US-AvaNeural",
        "--rate=-2%", "--file", str(script), "--write-media", str(mp3)])
    sh(["ffmpeg", "-y", "-i", str(mp3), "-ar", "16000", "-ac", "1", str(out_wav)],
       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def ltx2(img: Path, wav: Path, out_mp4: Path, seed: int, duration: float):
    from gradio_client import Client, handle_file
    token = TOKEN_FILE.read_text().strip()
    c = Client(LTX_SPACE, token=token)
    print(f"[ltx2] generating seed={seed} dur={duration}s from {img.name} ...")
    res = c.predict(handle_file(str(img)), handle_file(str(wav)),
                    PROMPT, NEG, duration, seed, api_name="/generate")
    vid = res[0] if isinstance(res, (list, tuple)) else res
    shutil.copy(vid, out_mp4)
    print(f"[ltx2] wrote {out_mp4}")


def gfpgan(in_mp4: Path, out_mp4: Path):
    sad = ROOT / "SadTalker"
    sh([str(ROOT / "venv-sad" / "bin" / "python"), str(ROOT / "enhance_gfpgan.py"),
        "--in", str(in_mp4), "--out", str(out_mp4)],
       cwd=str(sad), env={**__import__("os").environ, "PYTORCH_ENABLE_MPS_FALLBACK": "1"})


def _probe_duration(p: Path) -> float:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(p)],
        capture_output=True, text=True)
    try:
        return float(out.stdout.strip())
    except ValueError:
        return 0.0


_CAPTION_FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"


def _caption_chunks(text: str, words_per: int = 4) -> list[str]:
    words = [w for w in text.replace("\n", " ").split() if w]
    return [" ".join(words[i:i + words_per]) for i in range(0, len(words), words_per)]


def _drawtext_escape(s: str) -> str:
    # drawtext is picky: keep plain words, escape its metacharacters.
    s = "".join(ch for ch in s if ch.isalnum() or ch in " .,!?$&'-")
    return (s.replace("\\", "").replace("'", "’")
             .replace(":", "\\:").replace(",", "\\,"))


def composite(in_mp4: Path, out_mp4: Path, script_text: str = ""):
    """Full-frame 9:16 composite (2026-06-11 quality pass).

    The old layout letterboxed the square render inside a blurred copy of
    itself — content filled ~35% of the frame and there were no captions,
    so muted viewers (most of them) got nothing. Now: center-crop the
    square persona to fill 1080x1920 (face is centered, the crop is safe)
    and burn in evenly-timed caption chunks from the voiceover script.
    """
    vf = "scale=1920:1920:flags=lanczos,crop=1080:1920:(in_w-1080)/2:0"
    if script_text:
        dur = _probe_duration(in_mp4) or 10.0
        chunks = _caption_chunks(script_text)
        if chunks:
            per = dur / len(chunks)
            for i, chunk in enumerate(chunks):
                t0, t1 = i * per, (i + 1) * per
                vf += (
                    f",drawtext=fontfile={_CAPTION_FONT}:text='{_drawtext_escape(chunk)}'"
                    f":fontsize=62:fontcolor=white:borderw=4:bordercolor=black"
                    f":box=1:boxcolor=black@0.35:boxborderw=18"
                    f":x=(w-text_w)/2:y=h-440"
                    f":enable='between(t,{t0:.2f},{t1:.2f})'"
                )
    sh(["ffmpeg", "-y", "-i", str(in_mp4), "-vf", vf,
        "-c:v", "libx264", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-shortest", str(out_mp4)],
       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--script", default=str(OUT / "script.txt"))
    ap.add_argument("--variant", help="persona image; default = rotate/random from the set")
    ap.add_argument("--polish", choices=["raw", "sharp", "auto"], default="auto",
                    help="auto = random per post (the human-variety mix)")
    ap.add_argument("--seed", type=int, default=77)
    ap.add_argument("--duration", type=float, default=4.0)
    ap.add_argument("--name", default="reel", help="output basename")
    args = ap.parse_args()

    script = Path(args.script)
    variant = Path(args.variant) if args.variant else random.choice(
        [p for p in DEFAULT_VARIANTS if p.exists()])
    polish = random.choice(["raw", "sharp"]) if args.polish == "auto" else args.polish

    print(f"[plan] variant={variant.name} polish={polish} seed={args.seed} dur={args.duration}s")
    wav = OUT / "vo_ava.wav"
    raw = OUT / f"{args.name}_ltx.mp4"
    make_voice(script, wav)
    ltx2(variant, wav, raw, args.seed, args.duration)

    head = raw
    if polish == "sharp":
        head = OUT / f"{args.name}_hd.mp4"
        gfpgan(raw, head)

    final = OUT / f"{args.name}_final.mp4"
    composite(head, final, script.read_text().strip())

    meta = OUT / f"{args.name}_meta.json"
    meta.write_text(json.dumps(
        {"variant": variant.name, "polish": polish, "seed": args.seed,
         "duration": args.duration, "script": script.read_text().strip()}, indent=2))
    print(f"[done] {final}  ({variant.name}, {polish})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
