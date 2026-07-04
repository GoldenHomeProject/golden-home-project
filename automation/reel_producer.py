"""GHP Reel Producer — renders 1080x1920 MP4 Reels from scripts.

All services used are FREE:
- Pexels Photo API (PEXELS_API_KEY) for REAL photos matching visual_prompt — preferred
- Pollinations.ai FLUX as fallback only when Pexels returns no match
- edge-tts en-US-AvaNeural for natural voiceover — no key
- ffmpeg for Ken Burns motion, text overlay, and assembly — bundled on runner
- Pillow for on-screen text composition

Output per script:
- social/reels/reel-<date>-NNN.mp4 (committed → IG fetches via raw.githubusercontent URL)
- Updates social/post_queue.json entry: status → "ready", video_url → raw URL

2026-04-30 quality pivot — faceless-but-real per CEO mandate:
- Pexels real photos preferred over AI-generated (algos downrank AI imagery)
- AvaNeural voice replaces JennyNeural (more natural cadence)
- Pollinations stays as last-resort fallback so renders never fail
"""
import asyncio
import json
import os
import subprocess
import sys
from pathlib import Path
from datetime import datetime, timezone
from urllib import request, parse

from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, str(Path(__file__).parent))
from agent_log import append_log_entry

ROOT = Path(__file__).resolve().parent.parent
SCRIPT_DIR = ROOT / "automation" / "scripts"
REEL_DIR = ROOT / "social" / "reels"
REEL_DIR.mkdir(parents=True, exist_ok=True)
QUEUE_PATH = ROOT / "social" / "post_queue.json"
MUSIC_DIR = ROOT / "social" / "music"

# Music bed mapping — pick a track based on content mood.
# night_owl = chill, atmospheric — bedroom / sleep / bathroom / pillow
# day_bird  = soft uplifting — kitchen / organizing / before-after / pets / tech
MUSIC_MOOD_KEYWORDS = {
    "night_owl.mp3": ("pillow", "sleep", "bedroom", "bathroom", "night", "neck", "side sleeper"),
}
MUSIC_DEFAULT = "day_bird.mp3"
# -22 dB below voiceover. Math: 10^(-22/20) ≈ 0.08
MUSIC_GAIN = 0.08

RAW_URL_BASE = "https://goldenhomeproject.com"

WIDTH, HEIGHT = 1080, 1920
ACCENT_COLOR = (212, 167, 69)
TEXT_COLOR = (255, 253, 247)
SHADOW_COLOR = (0, 0, 0)

FONT_CANDIDATES = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    "/System/Library/Fonts/Helvetica.ttc",
]


def find_font(size: int) -> ImageFont.FreeTypeFont:
    for path in FONT_CANDIDATES:
        if os.path.exists(path):
            return ImageFont.truetype(path, size)
    return ImageFont.load_default()


PEXELS_API_KEY = os.environ.get("PEXELS_API_KEY", "").strip()


def _short_query(prompt: str) -> str:
    """Pexels search works better with 2–4 nouns, not full sentences.

    Strip filler like 'first-person POV', 'close-up of', 'person', etc.,
    keep the concrete object/scene words.
    """
    p = prompt.lower()
    for cue in (
        "first-person pov", "close-up of", "tight close-up of", "shot of",
        "view of", "image of", "photo of", "picture of",
    ):
        p = p.replace(cue, " ")
    # Keep first 5 words after cleanup; Pexels prefers short queries.
    words = [w for w in p.replace(",", " ").split() if w and len(w) > 2]
    return " ".join(words[:5]).strip()


def fetch_pexels_photo(prompt: str, out_path: Path) -> bool:
    """Search Pexels for a real portrait-orientation photo matching the prompt.

    Free key, 200 req/hr, 20k/mo — already in PEXELS_API_KEY secret.
    Returns False on miss or API failure so caller can fall back.
    """
    if not PEXELS_API_KEY:
        return False
    query = _short_query(prompt)
    if not query:
        return False
    enc = parse.quote(query)
    url = (
        f"https://api.pexels.com/v1/search?query={enc}"
        f"&per_page=5&orientation=portrait&size=large"
    )
    req = request.Request(url, headers={"Authorization": PEXELS_API_KEY})
    try:
        with request.urlopen(req, timeout=20) as r:
            data = json.loads(r.read())
    except Exception as e:
        print(f"    pexels search failed: {e}")
        return False
    photos = data.get("photos", []) or []
    if not photos:
        return False
    # Prefer the largest available (`original` if present, else `large2x`/`large`).
    src = photos[0].get("src", {}) or {}
    img_url = src.get("original") or src.get("large2x") or src.get("large")
    if not img_url:
        return False
    img_req = request.Request(img_url, headers={"User-Agent": "GHP-ReelProducer/1.0"})
    try:
        with request.urlopen(img_req, timeout=30) as r:
            img_bytes = r.read()
        if len(img_bytes) < 5000:
            raise ValueError(f"Pexels image too small ({len(img_bytes)} bytes)")
        out_path.write_bytes(img_bytes)
        print(f"    pexels hit: query='{query}' photographer={photos[0].get('photographer','?')}")
        return True
    except Exception as e:
        print(f"    pexels download failed: {e}")
        return False


def pollinations_url(prompt: str) -> str:
    """Pollinations.ai FLUX endpoint — free, no auth. FALLBACK ONLY.

    Used only when Pexels returns no match. AI-generated imagery is
    algorithmically downranked on IG/YT, so Pexels real photos are preferred.
    """
    styled = (
        f"{prompt}, professional product photography, warm natural lighting, "
        f"shallow depth of field, 8k, editorial home magazine style, "
        f"clean composition, no text, no watermark"
    )
    enc = parse.quote(styled)
    return (
        f"https://image.pollinations.ai/prompt/{enc}"
        f"?width={WIDTH}&height={HEIGHT}&model=flux&nologo=true&enhance=true"
    )


def fetch_scene_bg(prompt: str, out_path: Path) -> bool:
    """Try Pexels real photo first; fall back to Pollinations AI on miss.

    Returns False only if both sources fail across all retries — caller then
    uses fallback_bg() branded gradient so a render never crashes.
    """
    if fetch_pexels_photo(prompt, out_path):
        return True
    url = pollinations_url(prompt)
    req = request.Request(url, headers={"User-Agent": "GHP-ReelProducer/1.0"})
    for attempt in range(3):
        try:
            with request.urlopen(req, timeout=60) as r:
                data = r.read()
            if len(data) < 5000:
                raise ValueError(f"Response too small ({len(data)} bytes)")
            out_path.write_bytes(data)
            print(f"    pollinations fallback used")
            return True
        except Exception as e:
            print(f"    pollinations attempt {attempt+1} failed: {e}")
    return False


def fallback_bg(out_path: Path):
    """If Pollinations fails, render a GHP-branded gradient fallback."""
    img = Image.new("RGB", (WIDTH, HEIGHT), (15, 15, 25))
    draw = ImageDraw.Draw(img)
    for y in range(HEIGHT):
        t = y / HEIGHT
        r = int(15 + 10 * (1 - t))
        g = int(15 + 8 * (1 - t))
        b = int(25 + 20 * (1 - t))
        draw.line([(0, y), (WIDTH, y)], fill=(r, g, b))
    img.save(out_path, "JPEG", quality=90)


def compose_scene_frame(bg_path: Path, on_screen_text: str, out_path: Path,
                        accent: bool = False):
    """Open background, darken bottom third, overlay readable typography."""
    img = Image.open(bg_path).convert("RGB")
    if img.size != (WIDTH, HEIGHT):
        img = img.resize((WIDTH, HEIGHT), Image.LANCZOS)

    overlay = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
    odraw = ImageDraw.Draw(overlay)
    for y in range(int(HEIGHT * 0.45), HEIGHT):
        alpha = int(220 * ((y - HEIGHT * 0.45) / (HEIGHT * 0.55)))
        odraw.line([(0, y), (WIDTH, y)], fill=(0, 0, 0, min(alpha, 200)))

    odraw.rectangle([(0, 0), (WIDTH, 10)], fill=ACCENT_COLOR + (255,))
    odraw.rectangle([(0, HEIGHT - 10), (WIDTH, HEIGHT)], fill=ACCENT_COLOR + (255,))

    img = Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB")
    draw = ImageDraw.Draw(img)

    text = (on_screen_text or "").strip()
    if text:
        font_size = 120 if accent else 92
        font = find_font(font_size)
        max_width = WIDTH - 120

        words = text.upper().split() if accent else text.split()
        lines, cur = [], ""
        for w in words:
            trial = f"{cur} {w}".strip()
            if font.getbbox(trial)[2] <= max_width:
                cur = trial
            else:
                if cur:
                    lines.append(cur)
                cur = w
        if cur:
            lines.append(cur)

        line_h = int(font_size * 1.2)
        total_h = line_h * len(lines)
        y0 = int(HEIGHT * 0.62) - total_h // 2

        for i, line in enumerate(lines):
            bbox = font.getbbox(line)
            w = bbox[2] - bbox[0]
            x = (WIDTH - w) // 2
            y = y0 + i * line_h
            # Drop shadow for legibility over any background
            draw.text((x + 4, y + 4), line, fill=SHADOW_COLOR, font=font)
            color = ACCENT_COLOR if accent else TEXT_COLOR
            draw.text((x, y), line, fill=color, font=font)

    wfont = find_font(34)
    draw.text((42, HEIGHT - 70), "@goldenhomeproject", fill=ACCENT_COLOR, font=wfont)

    img.save(out_path, "JPEG", quality=92, optimize=True)


async def render_voiceover(text: str, out_path: Path):
    """Use en-US-AvaNeural (English-LOCKED), NOT AvaMultilingualNeural.
    The multilingual model drifts into non-English phonetics on brand names and
    abbreviations (e.g. 'Govee', 'Eli & Elm', 'lbs'), producing audible Spanish/
    Italian-sounding fragments mid-voiceover (caught 2026-06-04 on a live reel).
    AvaNeural is the same Ava speaker, English only — keep it locked."""
    import edge_tts
    communicate = edge_tts.Communicate(
        text, "en-US-AvaNeural", rate="+5%", pitch="+0Hz"
    )
    await communicate.save(str(out_path))


def ffmpeg_kenburns_scene(frame_path: Path, duration: float, out_path: Path,
                          zoom_in: bool = True):
    """Turn a static JPEG into a moving video clip via Ken Burns zoom."""
    frames = max(int(duration * 30), 30)
    # ffmpeg's zoompan filter name is `zoompan`; its internal zoom variable is
    # referenced as `z` (or `zoom`). Earlier version used bare `zoom='...'`
    # which ffmpeg parsed as an unknown filter. Pix-fmt goes via -pix_fmt flag
    # rather than trailing filter to avoid chain parser edge cases.
    if zoom_in:
        z_expr = "min(zoom+0.0015,1.15)"
    else:
        z_expr = "if(lte(zoom,1.0),1.15,max(1.001,zoom-0.0015))"
    vf = (
        f"scale=2160:3840,"
        f"zoompan=z='{z_expr}':d={frames}:s={WIDTH}x{HEIGHT}:fps=30"
    )
    cmd = [
        "ffmpeg", "-y", "-loglevel", "error",
        "-loop", "1", "-i", str(frame_path),
        "-vf", vf,
        "-t", f"{duration}",
        "-c:v", "libx264", "-preset", "medium", "-crf", "22",
        "-pix_fmt", "yuv420p",
        str(out_path),
    ]
    subprocess.run(cmd, check=True)


def pick_music_bed(script: dict) -> Path | None:
    """Pick a music bed based on script content mood. Returns None if none found."""
    if not MUSIC_DIR.exists():
        return None
    haystack = " ".join([
        script.get("hook", ""),
        script.get("caption", ""),
        (script.get("affiliate_strategy") or {}).get("primary_product", ""),
    ]).lower()
    for filename, keywords in MUSIC_MOOD_KEYWORDS.items():
        if any(k in haystack for k in keywords):
            p = MUSIC_DIR / filename
            if p.exists():
                return p
    default = MUSIC_DIR / MUSIC_DEFAULT
    return default if default.exists() else None


def ffmpeg_concat_with_audio(clip_paths: list[Path], audio_path: Path,
                             out_path: Path, music_path: Path | None = None):
    """Concat per-scene MP4s, mix voiceover + optional music bed."""
    concat_list = out_path.parent / f"{out_path.stem}_concat.txt"
    concat_list.write_text(
        "\n".join(f"file '{p.absolute()}'" for p in clip_paths)
    )

    if music_path and music_path.exists():
        # Voice at full volume, music at MUSIC_GAIN, 0.5s fade on music ends.
        filter_complex = (
            f"[2:a]volume={MUSIC_GAIN},afade=t=in:st=0:d=0.3,afade=t=out:st=25:d=1.5[mbed];"
            f"[1:a][mbed]amix=inputs=2:duration=first:dropout_transition=0:normalize=0,"
            f"alimiter=limit=0.95[aout]"
        )
        cmd = [
            "ffmpeg", "-y", "-loglevel", "error",
            "-f", "concat", "-safe", "0", "-i", str(concat_list),
            "-i", str(audio_path),
            "-stream_loop", "-1", "-i", str(music_path),
            "-filter_complex", filter_complex,
            "-map", "0:v", "-map", "[aout]",
            "-c:v", "libx264", "-preset", "medium", "-crf", "22", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "160k",
            "-shortest",
            "-movflags", "+faststart",
            str(out_path),
        ]
    else:
        cmd = [
            "ffmpeg", "-y", "-loglevel", "error",
            "-f", "concat", "-safe", "0", "-i", str(concat_list),
            "-i", str(audio_path),
            "-c:v", "libx264", "-preset", "medium", "-crf", "22", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "160k",
            "-shortest",
            "-movflags", "+faststart",
            str(out_path),
        ]
    subprocess.run(cmd, check=True)
    concat_list.unlink(missing_ok=True)


def produce_reel(script_path: Path) -> Path | None:
    script = json.loads(script_path.read_text())
    scenes = script.get("scenes", [])
    if not scenes:
        print(f"  {script_path.name}: no scenes, skipping")
        return None

    stem = script_path.stem
    work_dir = REEL_DIR / f"_work_{stem}"
    work_dir.mkdir(exist_ok=True)

    scene_clips = []
    voiceover_full = []

    for i, scene in enumerate(scenes):
        n = scene.get("n", i + 1)
        visual = scene.get("visual_prompt", "").strip()
        on_text = scene.get("on_screen_text", "")
        vo = scene.get("voiceover", "").strip()
        duration = float(scene.get("duration_sec", 4))

        bg_path = work_dir / f"bg_{n:02d}.jpg"
        frame_path = work_dir / f"frame_{n:02d}.jpg"
        clip_path = work_dir / f"clip_{n:02d}.mp4"

        print(f"    scene {n}: {visual[:60]}")
        if not visual or not fetch_scene_bg(visual, bg_path):
            fallback_bg(bg_path)

        compose_scene_frame(bg_path, on_text, frame_path, accent=(n == 1))
        ffmpeg_kenburns_scene(frame_path, duration, clip_path,
                              zoom_in=(i % 2 == 0))
        scene_clips.append(clip_path)

        if vo:
            voiceover_full.append(vo)

    audio_path = work_dir / "voiceover.mp3"
    vo_text = " ... ".join(voiceover_full) if voiceover_full else script.get("hook", "")
    try:
        asyncio.run(render_voiceover(vo_text, audio_path))
    except Exception as e:
        print(f"  TTS failed ({e}), generating silent track")
        total = sum(float(s.get("duration_sec", 4)) for s in scenes)
        subprocess.run([
            "ffmpeg", "-y", "-loglevel", "error",
            "-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo",
            "-t", str(total), "-c:a", "aac", str(audio_path),
        ], check=True)

    out_path = REEL_DIR / f"{stem}.mp4"
    music_path = pick_music_bed(script)
    if music_path:
        print(f"    music bed: {music_path.name}")
    ffmpeg_concat_with_audio(scene_clips, audio_path, out_path,
                             music_path=music_path)

    # Cleanup
    for f in work_dir.iterdir():
        f.unlink()
    work_dir.rmdir()

    size_kb = out_path.stat().st_size // 1024
    print(f"  ✓ {out_path.name} ({size_kb} KB)")
    return out_path


def update_queue(script_path: Path, video_path: Path):
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
            entry["image_url"] = video_url
            changed = True
            break
    if changed:
        QUEUE_PATH.write_text(json.dumps(queue, indent=2))


def main():
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    candidates = sorted(SCRIPT_DIR.glob(f"reel-{today}-*.json"))
    if not candidates:
        print(f"[reel-producer] No scripts for {today}. Done.")
        return

    print(f"[reel-producer] {len(candidates)} scripts to render")
    failures = 0
    attempted = 0
    for script_path in candidates:
        video_path = REEL_DIR / f"{script_path.stem}.mp4"
        if video_path.exists():
            print(f"  {video_path.name} already exists, skipping")
            continue
        attempted += 1
        try:
            out = produce_reel(script_path)
            if out:
                update_queue(script_path, out)
            else:
                failures += 1
                print(f"  produce_reel returned None for {script_path.name}")
        except Exception as e:
            failures += 1
            print(f"  ERROR producing {script_path.name}: {e}")

    # Per AGENT COORDINATION PROTOCOL — log before the possible sys.exit
    rendered = attempted - failures
    append_log_entry(
        agent="Reel Producer",
        ran=f"Rendered {rendered}/{attempted} MP4s for {today}" + (f" ({failures} failed)" if failures else ""),
        changed=f"social/reels/reel-{today}-*.mp4, social/post_queue.json" if rendered else "none",
        external="none",
        hint=f"IG Poster has {rendered} new Reels ready for 14:00 + 22:00 UTC slots" if rendered else "No new Reels today — IG Poster should use backlog",
    )

    if failures:
        print(f"[reel-producer] FAIL: {failures}/{attempted} reels failed to render")
        sys.exit(1)
    print(f"[reel-producer] OK: {attempted} reels rendered")


if __name__ == "__main__":
    main()
