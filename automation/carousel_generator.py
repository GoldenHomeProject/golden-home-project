#!/usr/bin/env python3
"""GHP Carousel Generator — produces 5-slide IG carousel posts.

Structurally different from the Reel pipeline (which has been shipping
0-engagement content for weeks per project_ghp_2026-05-29_diagnosis.md):

  - Image carousel, NOT video. IG algo treats carousels as "saves"-driven
    content and surfaces them differently from reels.
  - Real Pexels stock photos as backgrounds, NEVER AI-generated imagery.
    AI imagery is algo-downranked. We use Pollinations ONLY for reels and
    even there it's a fallback. Carousels are stock-only.
  - No voiceover, no music, no video processing — just PNG slides with
    PIL text overlay. Lower production bar, faster iteration.
  - Caption written for save-prompted engagement, not view-time.

Pipeline:
  1. Pick a vetted ASIN (least-recently-used in carousel history).
  2. Call Claude for slide content (hook + 3 tips + CTA + caption).
  3. Fetch 4 Pexels photos via search queries Claude returns.
  4. Compose 5 PNGs (1080x1350) with dark text-overlay band.
  5. Write to social/carousels/<date>-<asin>/ and append to post_queue.json
     with media_type=CAROUSEL_ALBUM so the IG poster can publish via the
     Meta Graph carousel endpoint.

Usage (local):
    PEXELS_API_KEY=xxx CLAUDE_CODE_OAUTH_TOKEN=yyy \
        python3 automation/carousel_generator.py

Usage (cron, GH Actions): wrapped by .github/workflows/content-generator.yml
once the Meta carousel poster is wired (task #32).
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib import parse, request

try:
    from PIL import Image, ImageDraw, ImageFont, ImageFilter
except ImportError:
    print("ERROR: Pillow not installed. pip install Pillow", file=sys.stderr)
    sys.exit(2)

sys.path.insert(0, str(Path(__file__).parent))
from _claude_api import call_claude_json  # noqa: E402
from agent_log import append_log_entry  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
SOCIAL = ROOT / "social"
CAROUSELS = SOCIAL / "carousels"
REGISTRY_PATH = SOCIAL / "dm_keyword_registry.json"
QUEUE_PATH = SOCIAL / "post_queue.json"

CANVAS_W, CANVAS_H = 1080, 1350  # IG portrait 4:5
PEXELS_API_KEY = os.environ.get("PEXELS_API_KEY", "").strip()

# raw.githubusercontent.com prefix the IG poster uses. Filled at queue time.
RAW_GH_BASE = "https://raw.githubusercontent.com/GoldenHomeProject/golden-home-project/main"


def _font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    """Best-effort load a clean sans-serif. Falls back to PIL default if
    no system font is found. Works on macOS, Linux (Pi), and GH runners."""
    candidates = [
        # Linux (Pi + GH runners)
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold
        else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf" if bold
        else "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
        # macOS
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf" if bold
        else "/System/Library/Fonts/Supplemental/Arial.ttf",
        "/Library/Fonts/Arial Bold.ttf" if bold else "/Library/Fonts/Arial.ttf",
    ]
    for p in candidates:
        if os.path.exists(p):
            return ImageFont.truetype(p, size)
    return ImageFont.load_default()


def pick_asin(reg: dict, carousel_history_dir: Path) -> dict:
    """Pick the vetted/entries product whose ASIN was carousel-featured the
    longest ago (or never). Avoids back-to-back duplicates."""
    pool = list(reg.get("entries", [])) + list(reg.get("vetted", []))
    if not pool:
        raise RuntimeError("No registry entries to pick from.")
    used_at: dict[str, str] = {}
    if carousel_history_dir.exists():
        for sub in carousel_history_dir.iterdir():
            if not sub.is_dir():
                continue
            # Dir names are <YYYY-MM-DD>-<asin>
            parts = sub.name.rsplit("-", 1)
            if len(parts) == 2:
                used_at[parts[1]] = parts[0]
    # Sort by (last-used-date or zero); pick the oldest / never-used
    pool.sort(key=lambda e: used_at.get(e.get("asin", ""), ""))
    return pool[0]


def fetch_pexels(query: str, out_path: Path) -> bool:
    """Pexels portrait search. Returns True on save. Same shape as the
    reel_producer helper but isolated so this script has no cross-import."""
    if not PEXELS_API_KEY:
        print(f"  [pexels] no API key; skipping query '{query}'")
        return False
    # Non-reversible key indicator so 403s are debuggable without leaking
    # any substring of the secret.
    import hashlib
    key_id = hashlib.sha256(PEXELS_API_KEY.encode()).hexdigest()[:8]
    print(f"  [pexels] key sha256[:8]={key_id} present=True")
    enc = parse.quote(query)
    url = (
        f"https://api.pexels.com/v1/search?query={enc}"
        f"&per_page=5&orientation=portrait&size=large"
    )
    # Pexels 403s the default Python-urllib User-Agent. Verified 2026-05-29
    # by running the same key from Mac curl (200) vs Python urllib (403).
    # A browser UA round-trips fine.
    BROWSER_UA = (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/131.0.0.0 Safari/537.36"
    )
    req = request.Request(url, headers={
        "Authorization": PEXELS_API_KEY,
        "User-Agent": BROWSER_UA,
    })
    try:
        with request.urlopen(req, timeout=20) as r:
            data = json.loads(r.read())
    except Exception as e:
        print(f"  [pexels] search failed '{query}': {e}")
        return False
    photos = data.get("photos", []) or []
    if not photos:
        print(f"  [pexels] no results for '{query}'")
        return False
    src = photos[0].get("src", {}) or {}
    img_url = src.get("original") or src.get("large2x") or src.get("large")
    if not img_url:
        return False
    try:
        with request.urlopen(
            request.Request(img_url, headers={"User-Agent": "GHP-Carousel/1.0"}),
            timeout=30,
        ) as r:
            out_path.write_bytes(r.read())
        print(f"  [pexels] hit '{query}' -> {out_path.name}")
        return True
    except Exception as e:
        print(f"  [pexels] download failed '{query}': {e}")
        return False


def _wrap(draw: ImageDraw.ImageDraw, text: str, font, max_w: int) -> list[str]:
    """Greedy word wrap to fit within max_w."""
    words = text.split()
    lines, cur = [], ""
    for w in words:
        trial = (cur + " " + w).strip()
        bbox = draw.textbbox((0, 0), trial, font=font)
        if bbox[2] - bbox[0] <= max_w:
            cur = trial
        else:
            if cur:
                lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines


# Slide palette — picked per slide_num so each carousel scrolls with
# visual rhythm rather than 5 identical backgrounds. Earthy organizing-
# niche tones (terracotta, sage, deep teal, warm clay, cream).
_PALETTE = [
    (193, 92, 60),    # 1: terracotta — hook
    (90, 110, 80),    # 2: sage
    (28, 65, 50),     # 3: deep teal
    (164, 109, 67),   # 4: warm clay
    (44, 44, 44),     # 5: charcoal — CTA
]


def _vgrad(top: tuple[int, int, int], bottom: tuple[int, int, int]) -> Image.Image:
    """Vertical 2-color gradient at canvas size."""
    img = Image.new("RGB", (CANVAS_W, CANVAS_H), top)
    px = img.load()
    for y in range(CANVAS_H):
        t = y / (CANVAS_H - 1)
        r = int(top[0] * (1 - t) + bottom[0] * t)
        g = int(top[1] * (1 - t) + bottom[1] * t)
        b = int(top[2] * (1 - t) + bottom[2] * t)
        for x in range(CANVAS_W):
            px[x, y] = (r, g, b)
    return img


def compose_slide(
    bg_path: Path | None, text: str, slide_num: int, total: int,
    *, brand_block: bool = False,
) -> Image.Image:
    """One 1080x1350 carousel slide.

    Two design paths:
      A) Photo path (bg_path present) — Pexels stock photo with a dark
         translucent band over the lower 55% holding the text.
      B) Type-driven path (no photo) — full-bleed gradient with bold
         centered typography. Used as intentional design, NOT as a broken
         fallback. The carousel scrolls through a 5-color palette
         (terracotta → sage → teal → clay → charcoal) so each slide
         has its own visual identity.

    The CTA slide (brand_block=True) always uses path B with the charcoal
    color (palette[4]) so the close-out feels like a final card, not a
    photo.
    """
    has_photo = bool(bg_path and bg_path.exists())
    palette_color = _PALETTE[(slide_num - 1) % len(_PALETTE)]
    canvas: Image.Image

    if has_photo and not brand_block:
        canvas = Image.new("RGB", (CANVAS_W, CANVAS_H), palette_color)
        bg = Image.open(bg_path).convert("RGB")
        bw, bh = bg.size
        scale = max(CANVAS_W / bw, CANVAS_H / bh)
        nw, nh = int(bw * scale), int(bh * scale)
        bg = bg.resize((nw, nh), Image.LANCZOS)
        ox, oy = (nw - CANVAS_W) // 2, (nh - CANVAS_H) // 2
        bg = bg.crop((ox, oy, ox + CANVAS_W, oy + CANVAS_H))
        bg = bg.filter(ImageFilter.GaussianBlur(radius=2))
        canvas.paste(bg)
        text_color = (255, 255, 255, 245)
        # translucent band in lower 55%
        band_top = int(CANVAS_H * 0.45)
        overlay = Image.new("RGBA", (CANVAS_W, CANVAS_H - band_top), (0, 0, 0, 180))
        canvas.paste(overlay, (0, band_top), overlay)
        text_y_start = band_top + 60
        text_area_h = CANVAS_H - band_top - 120
    else:
        # Type-driven: gradient from palette color (top) to a slightly
        # deeper version (bottom). Looks intentional, not failed.
        bottom = tuple(max(0, int(c * 0.65)) for c in palette_color)
        canvas = _vgrad(palette_color, bottom)  # type: ignore[arg-type]
        text_color = (255, 250, 240, 250)  # warm cream text
        # subtle decorative accent: a thin horizontal line above the text
        text_y_start = 320
        text_area_h = CANVAS_H - text_y_start - 220

    draw = ImageDraw.Draw(canvas, "RGBA")

    # Slide counter (top-right) — small chip
    counter = f"{slide_num}/{total}"
    cf = _font(28, bold=True)
    cw = draw.textbbox((0, 0), counter, font=cf)[2]
    draw.rectangle(
        [CANVAS_W - cw - 60, 40, CANVAS_W - 30, 85],
        fill=(0, 0, 0, 140),
    )
    draw.text(
        (CANVAS_W - cw - 45, 47), counter, font=cf, fill=(255, 255, 255, 230),
    )

    # Type-driven slides get a decorative accent line above the text block
    if not has_photo:
        line_y = text_y_start - 50
        line_w = 120
        line_x = (CANVAS_W - line_w) // 2
        draw.rectangle(
            [line_x, line_y, line_x + line_w, line_y + 6],
            fill=(255, 250, 240, 200),
        )

    # Body text — wrapped + centered vertically inside the text area
    body_font_size = 60 if len(text) > 80 else 72
    bf = _font(body_font_size, bold=True)
    margin = 90
    max_w = CANVAS_W - 2 * margin
    lines = _wrap(draw, text, bf, max_w)
    line_h = int(body_font_size * 1.25)
    total_h = line_h * len(lines)
    y = text_y_start + max(0, (text_area_h - total_h) // 2)
    for ln in lines:
        bbox = draw.textbbox((0, 0), ln, font=bf)
        w = bbox[2] - bbox[0]
        x = (CANVAS_W - w) // 2
        # subtle shadow for legibility (stronger when photo, lighter on grad)
        shadow_alpha = 200 if has_photo else 90
        draw.text((x + 2, y + 2), ln, font=bf, fill=(0, 0, 0, shadow_alpha))
        draw.text((x, y), ln, font=bf, fill=text_color)
        y += line_h

    # Brand watermark bottom-left (always)
    wf = _font(28)
    draw.text(
        (60, CANVAS_H - 70), "@golden_home_project",
        font=wf, fill=(255, 255, 255, 200),
    )

    return canvas


def claude_slide_content(entry: dict) -> dict:
    """Ask Claude for the 5-slide carousel content: hook + 3 tips + CTA +
    caption + 3-5 pexels queries. Strict JSON return.

    Why Claude (vs templating from copy_library.json): templates have been
    shipping into the post queue for weeks and producing 0 engagement.
    Carousels are a new format — we want slide content matched to the
    SPECIFIC product, not a generic template substitution."""
    product = entry.get("product_name", "")
    keyword = entry.get("keyword", "LINK")
    cats = ", ".join(entry.get("categories") or [])
    asin = entry.get("asin", "")
    aff_url = f"https://www.amazon.com/dp/{asin}?tag=goldenhomep06-20"

    prompt = f"""You are a copywriter for Golden Home Project, an Amazon
affiliate IG account in the home organizing niche.

Task: write a 5-slide carousel post for this product. Carousels are
"saves" content — viewers save the post for later, then DM the keyword
to get the link via auto-reply.

Product: {product}
Affiliate URL: {aff_url}
DM keyword (must appear in CTA + caption): {keyword}
Categories: {cats}

Slides:
  1. HOOK — bold one-line promise that earns the swipe. 10-15 words MAX.
     Concrete, specific, no "I spent $X" patterns (dead format).
  2. TIP 1 — one specific tactical tip about the problem this product
     solves. 18-30 words. Useful even if reader never buys.
  3. TIP 2 — second specific tip. 18-30 words.
  4. TIP 3 — third specific tip — the one that's HARDEST to do without
     the product (set up the CTA). 18-30 words.
  5. CTA — direct save+DM prompt with the keyword. 12-20 words.

Caption (for the IG post itself, NOT a slide):
- First line is a hook that survives the IG truncation (first ~80 chars).
- 1-2 short paragraphs.
- "Save this for later" prompt early.
- DM-the-keyword line with: "Comment {keyword} or DM me {keyword} for the link"
- 3-5 hashtags at the END, home-organization-niche.
- No emojis on first line; sparing emojis elsewhere.

Pexels queries (4 strings, one per visual slide 1-4):
- Concrete, photo-searchable nouns. Examples: "modern white closet",
  "messy pantry shelves", "kitchen drawer dividers".
- 2-4 words each.
- Match the slide's subject visually.

Return STRICT JSON:
{{
  "slide_1": "<hook>",
  "slide_2": "<tip 1>",
  "slide_3": "<tip 2>",
  "slide_4": "<tip 3>",
  "slide_5": "<cta>",
  "caption": "<full caption with hashtags>",
  "pexels_queries": ["<q1>", "<q2>", "<q3>", "<q4>"]
}}"""
    return call_claude_json(prompt, max_tokens=2048, max_turns=1, timeout=180)


def main() -> int:
    if not REGISTRY_PATH.exists():
        print("ERROR: registry missing", file=sys.stderr)
        return 1
    reg = json.loads(REGISTRY_PATH.read_text())
    entry = pick_asin(reg, CAROUSELS)
    asin = entry.get("asin", "")
    keyword = entry.get("keyword", "LINK")
    date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    out_dir = CAROUSELS / f"{date_str}-{asin}"
    out_dir.mkdir(parents=True, exist_ok=True)
    print(f"[carousel] generating for {asin} ({entry.get('product_name','')[:60]!r})")

    try:
        content = claude_slide_content(entry)
    except Exception as e:
        print(f"[carousel] ERROR: Claude content failed: {e}", file=sys.stderr)
        return 1

    # Fetch 4 Pexels photos
    queries = content.get("pexels_queries", []) or []
    photos: list[Path | None] = []
    for i, q in enumerate(queries[:4]):
        out_path = out_dir / f"bg-{i+1}.jpg"
        ok = fetch_pexels(q, out_path)
        photos.append(out_path if ok else None)
    # pad if Claude gave us fewer than 4
    while len(photos) < 4:
        photos.append(None)

    # Compose 5 slides
    slide_texts = [
        content.get("slide_1", "").strip(),
        content.get("slide_2", "").strip(),
        content.get("slide_3", "").strip(),
        content.get("slide_4", "").strip(),
        content.get("slide_5", "").strip(),
    ]
    if not all(slide_texts):
        print("[carousel] ERROR: Claude returned empty slide text", file=sys.stderr)
        return 1

    slide_paths: list[Path] = []
    for i, txt in enumerate(slide_texts):
        slide_num = i + 1
        is_cta = (slide_num == 5)
        bg = None if is_cta else photos[i] if i < 4 else None
        img = compose_slide(
            bg, txt, slide_num, total=5, brand_block=is_cta,
        )
        out = out_dir / f"slide-{slide_num}.png"
        img.save(out, "PNG", optimize=True)
        slide_paths.append(out)
        print(f"  slide {slide_num}/5 -> {out.relative_to(ROOT)}")

    # Queue entry — image_urls will resolve to raw.githubusercontent.com
    # AFTER the slides are pushed to main.
    caption = content.get("caption", "").strip()
    rel_paths = [str(p.relative_to(ROOT)) for p in slide_paths]
    image_urls = [f"{RAW_GH_BASE}/{p}" for p in rel_paths]

    queue = []
    if QUEUE_PATH.exists():
        try:
            queue = json.loads(QUEUE_PATH.read_text())
        except Exception:
            queue = []
    queue.append({
        "id": f"carousel-{date_str}-{asin}",
        "media_type": "CAROUSEL_ALBUM",
        "image_urls": image_urls,
        "caption": caption,
        "asin": asin,
        "keyword": keyword,
        "queued_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "source": "carousel_generator",
    })
    QUEUE_PATH.write_text(json.dumps(queue, indent=2))
    print(f"[carousel] queued -> {QUEUE_PATH.relative_to(ROOT)}")

    append_log_entry(
        agent="Carousel Generator",
        ran=f"Generated 5-slide carousel for {asin} ({entry.get('product_name','')[:40]})",
        changed=", ".join(rel_paths + [str(QUEUE_PATH.relative_to(ROOT))]),
        external="Pexels (4 photos) + Claude CLI (slide content)",
        hint=f"IG Poster: next CAROUSEL_ALBUM slot will publish {asin} carousel.",
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
