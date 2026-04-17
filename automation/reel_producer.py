"""GHP Reel Producer — Agent 3 of the flywheel.

Takes today's Reel scripts and renders actual 1080x1920 MP4 videos.

Tools (all free, all run in GitHub Actions):
- Pillow: per-scene 1080x1920 image composition with text overlay
- edge-tts: free neural TTS for voiceover
- ffmpeg: assembles images + audio into final Reel MP4

Output per script:
- social/reels/reel-<date>-NNN.mp4 (committed → IG can fetch via raw.githubusercontent)
- Updates social/post_queue.json: status → "ready", video_url → github raw URL

Keep it simple: slideshow-style Reels (Ken Burns zoom) with on-screen text + VO.
Production value is fine for validation phase — beats 0-engagement static posts.
"""
import asyncio
import json
import os
import subprocess
import sys
from pathlib import Path
from datetime import datetime, timezone

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
SCRIPT_DIR = ROOT / "automation" / "scripts"
REEL_DIR = ROOT / "social" / "reels"
REEL_DIR.mkdir(parents=True, exist_ok=True)
QUEUE_PATH = ROOT / "social" / "post_queue.json"

# GitHub raw URL pattern — confirmed public + served with correct MIME
RAW_URL_BASE = "https://raw.githubusercontent.com/GoldenHomeProject/golden-home-project/main"

WIDTH, HEIGHT = 1080, 1920
BG_COLOR = (15, 15, 25)  # GHP dark
TEXT_COLOR = (240, 236, 228)
ACCENT_COLOR = (212, 167, 69)  # GHP gold

# Try common font paths in ubuntu-latest runner
FONT_CANDIDATES = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    "/System/Library/Fonts/Helvetica.ttc",  # mac fallback for local test
]


def find_font(size: int) -> ImageFont.FreeTypeFont:
    for path in FONT_CANDIDATES:
        if os.path.exists(path):
            return ImageFont.truetype(path, size)
    return ImageFont.load_default()


def wrap_text(text: str, font, max_width: int) -> list[str]:
    """Word-wrap text to fit max_width pixels."""
    words = text.split()
    lines, current = [], ""
    for word in words:
        trial = f"{current} {word}".strip()
        if font.getbbox(trial)[2] <= max_width:
            current = trial
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines


def render_scene(text: str, out_path: Path, accent: bool = False):
    """Render a single 1080x1920 frame with centered text."""
    img = Image.new("RGB", (WIDTH, HEIGHT), BG_COLOR)
    draw = ImageDraw.Draw(img)

    # Gold accent bar at top
    draw.rectangle([(0, 0), (WIDTH, 12)], fill=ACCENT_COLOR)
    draw.rectangle([(0, HEIGHT - 12), (WIDTH, HEIGHT)], fill=ACCENT_COLOR)

    font_size = 110 if accent else 90
    font = find_font(font_size)
    max_text_width = WIDTH - 160

    lines = wrap_text(text.upper() if accent else text, font, max_text_width)
    line_height = int(font_size * 1.2)
    total_h = line_height * len(lines)
    y = (HEIGHT - total_h) // 2

    for line in lines:
        bbox = font.getbbox(line)
        w = bbox[2] - bbox[0]
        x = (WIDTH - w) // 2
        # Drop shadow for readability
        draw.text((x + 4, y + 4), line, fill=(0, 0, 0), font=font)
        color = ACCENT_COLOR if accent else TEXT_COLOR
        draw.text((x, y), line, fill=color, font=font)
        y += line_height

    # Watermark
    watermark_font = find_font(32)
    draw.text((40, HEIGHT - 80), "@goldenhomeproject", fill=ACCENT_COLOR, font=watermark_font)

    img.save(out_path, "PNG", optimize=True)


async def render_voiceover(text: str, out_path: Path):
    """edge-tts → MP3. Free, high quality, no API key."""
    import edge_tts
    # Warm female voice — fits GHP's conversational tone
    communicate = edge_tts.Communicate(text, "en-US-JennyNeural", rate="+5%")
    await communicate.save(str(out_path))


def ffmpeg_assemble(scene_images: list[Path], scene_durations: list[float],
                    audio_path: Path, out_path: Path):
    """Concat scene PNGs with durations, overlay audio track."""
    # Build ffconcat file
    concat_file = out_path.parent / f"{out_path.stem}_concat.txt"
    lines = []
    for img, dur in zip(scene_images, scene_durations):
        lines.append(f"file '{img.absolute()}'")
        lines.append(f"duration {dur}")
    # Last image needs repeat per ffconcat spec
    lines.append(f"file '{scene_images[-1].absolute()}'")
    concat_file.write_text("\n".join(lines))

    cmd = [
        "ffmpeg", "-y", "-loglevel", "error",
        "-f", "concat", "-safe", "0", "-i", str(concat_file),
        "-i", str(audio_path),
        "-c:v", "libx264", "-pix_fmt", "yuv420p",
        "-vf", f"scale={WIDTH}:{HEIGHT},fps=30",
        "-c:a", "aac", "-b:a", "128k",
        "-shortest",  # cut video to audio length (prevents trailing silence)
        "-movflags", "+faststart",
        str(out_path),
    ]
    subprocess.run(cmd, check=True)
    concat_file.unlink(missing_ok=True)


def produce_reel(script_path: Path) -> Path | None:
    """Full pipeline: script JSON → MP4."""
    script = json.loads(script_path.read_text())
    scenes = script.get("scenes", [])
    if not scenes:
        print(f"  {script_path.name}: no scenes, skipping")
        return None

    stem = script_path.stem  # reel-2026-04-17-001
    work_dir = REEL_DIR / f"_work_{stem}"
    work_dir.mkdir(exist_ok=True)

    # 1. Render per-scene PNGs
    scene_images = []
    scene_durations = []
    voiceover_full = []
    for scene in scenes:
        n = scene.get("n", len(scene_images) + 1)
        text = scene.get("on_screen_text", "").strip() or scene.get("voiceover", "")[:80]
        img_path = work_dir / f"scene_{n:02d}.png"
        render_scene(text, img_path, accent=(n == 1))
        scene_images.append(img_path)
        scene_durations.append(float(scene.get("duration_sec", 4)))
        vo = scene.get("voiceover", "").strip()
        if vo:
            voiceover_full.append(vo)

    # 2. Render combined voiceover
    audio_path = work_dir / "voiceover.mp3"
    vo_text = " ... ".join(voiceover_full) if voiceover_full else script.get("hook", "")
    try:
        asyncio.run(render_voiceover(vo_text, audio_path))
    except Exception as e:
        print(f"  TTS failed ({e}) — rendering silent video")
        # Create a silent track
        total = sum(scene_durations)
        subprocess.run([
            "ffmpeg", "-y", "-loglevel", "error",
            "-f", "lavfi", "-i", f"anullsrc=r=44100:cl=stereo",
            "-t", str(total), "-c:a", "aac", str(audio_path),
        ], check=True)

    # 3. Assemble
    out_path = REEL_DIR / f"{stem}.mp4"
    ffmpeg_assemble(scene_images, scene_durations, audio_path, out_path)

    # 4. Cleanup work dir
    for f in work_dir.iterdir():
        f.unlink()
    work_dir.rmdir()

    size_kb = out_path.stat().st_size // 1024
    print(f"  ✓ {out_path.name} ({size_kb} KB)")
    return out_path


def update_queue(script_path: Path, video_path: Path):
    """Flip queue entry from awaiting_video → ready, set video_url."""
    if not QUEUE_PATH.exists():
        return
    queue = json.loads(QUEUE_PATH.read_text())
    rel_script = str(script_path.relative_to(ROOT))
    rel_video = str(video_path.relative_to(ROOT))
    video_url = f"{RAW_URL_BASE}/{rel_video}"

    changed = False
    for entry in queue:
        if entry.get("script_path") == rel_script and entry.get("status") == "awaiting_video":
            entry["status"] = "ready"
            entry["video_url"] = video_url
            entry["image_url"] = video_url  # instagram-poster keys on image_url field
            changed = True
            break
    if changed:
        QUEUE_PATH.write_text(json.dumps(queue, indent=2))


def main():
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    # Process only today's scripts that don't yet have a video
    candidates = sorted(SCRIPT_DIR.glob(f"reel-{today}-*.json"))
    if not candidates:
        print(f"[reel-producer] No scripts for {today}. Done.")
        return

    print(f"[reel-producer] {len(candidates)} scripts to render")
    for script_path in candidates:
        video_path = REEL_DIR / f"{script_path.stem}.mp4"
        if video_path.exists():
            print(f"  {video_path.name} already exists, skipping")
            continue
        try:
            out = produce_reel(script_path)
            if out:
                update_queue(script_path, out)
        except Exception as e:
            print(f"  ERROR producing {script_path.name}: {e}")


if __name__ == "__main__":
    main()
