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
import re
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
from _claude_api import call_claude_json, ClaudeUsageLimit  # noqa: E402
from agent_log import append_log_entry  # noqa: E402
from content_quality_gate import fabrication_match, generic_opener
import brand  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
SOCIAL = ROOT / "social"
CAROUSELS = SOCIAL / "carousels"
REGISTRY_PATH = SOCIAL / "dm_keyword_registry.json"
QUEUE_PATH = SOCIAL / "post_queue.json"

CANVAS_W, CANVAS_H = 1080, 1350  # IG portrait 4:5
PEXELS_API_KEY = os.environ.get("PEXELS_API_KEY", "").strip()

# raw.githubusercontent.com prefix the IG poster uses. Filled at queue time.
RAW_GH_BASE = "https://goldenhomeproject.com"


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
    # Live products only: a vetted-but-not-live entry has no comment keyword (the CTA
    # fell back to "LINK") and nothing stopped a $114.99 pick in a $5-35 niche.
    def _price(e):
        m = re.search(r"[\d,]+\.\d{2}", str(e.get("verified_price") or ""))
        return float(m.group().replace(",", "")) if m else None
    pool = [e for e in reg.get("entries", [])
            if e.get("status") == "live" and e.get("keyword")
            and (_price(e) is None or 5 <= _price(e) <= 35)]
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
    """One 1080x1350 carousel slide in the brand system (automation/brand.py).

    Redesigned 2026-09-26. The old slides laid bold white DejaVu over a blurred,
    darkened stock photo; photos that had nothing to do with the tip (a hole in a
    wall, car-care bottles) sat behind every line, and all of it read as a template.
    Now the carousel matches the pins:
      - photo slides: the photo stays SHARP in the top 58%, the words sit on the
        brand cream band below it in ink, under a short gold rule;
      - no-photo slides: full cream card, larger type — deliberate, not a fallback;
      - the CTA slide: ink card, cream type, gold keyword.
    """
    has_photo = bool(bg_path and bg_path.exists()) and not brand_block
    bg_col = brand.INK if brand_block else brand.CREAM
    fg_col = brand.CREAM if brand_block else brand.INK
    canvas = Image.new("RGB", (CANVAS_W, CANVAS_H), bg_col)
    draw = ImageDraw.Draw(canvas, "RGBA")

    if has_photo:
        photo_h = int(CANVAS_H * 0.58)
        bg = Image.open(bg_path).convert("RGB")
        bw, bh = bg.size
        scale = max(CANVAS_W / bw, photo_h / bh)
        nw, nh = int(bw * scale), int(bh * scale)
        bg = bg.resize((nw, nh), Image.LANCZOS)
        ox, oy = (nw - CANVAS_W) // 2, (nh - photo_h) // 2
        canvas.paste(bg.crop((ox, oy, ox + CANVAS_W, oy + photo_h)), (0, 0))
        top = photo_h + 64
    else:
        top = 300 if slide_num == 1 or brand_block else 260

    # Gold rule above the words
    draw.rectangle([brand.MARGIN + 30, top, brand.MARGIN + 30 + 96, top + 7], fill=brand.GOLD)
    top += 50

    # Counter chip, top-right
    counter = f"{slide_num}/{total}"
    cf = brand.font(26, bold=True)
    cw = draw.textbbox((0, 0), counter, font=cf)[2]
    draw.rounded_rectangle([CANVAS_W - cw - 70, 40, CANVAS_W - 36, 88], radius=24,
                           fill=(18, 18, 18, 150) if has_photo else (*brand.GOLD, 255))
    draw.text((CANVAS_W - cw - 53, 49), counter, font=cf,
              fill=brand.WHITE if has_photo else brand.INK)

    # Words: measure, shrink until they fit the space left (never run off the frame)
    left = brand.MARGIN + 30
    max_w = CANVAS_W - 2 * left
    bottom = CANVAS_H - 150
    start = (72 if slide_num == 1 else 58) if has_photo else (84 if slide_num == 1 or brand_block else 68)
    for size in range(start, 33, -2):
        f = brand.font(size, bold=True)
        lines = _wrap(draw, text, f, max_w)
        line_h = int(size * 1.28)
        if top + line_h * len(lines) <= bottom:
            break
    y = top
    for ln in lines:
        draw.text((left, y), ln, font=f, fill=fg_col)
        y += line_h

    # Footer: gold square + handle
    fy = CANVAS_H - 92
    draw.rectangle([left, fy + 8, left + 16, fy + 24], fill=brand.GOLD)
    draw.text((left + 30, fy), "@golden_home_project", font=brand.font(28, bold=False),
              fill=brand.CREAM if brand_block else brand.MUTED)
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
    aff_url = f"https://www.amazon.com/dp/{asin}?tag=goldenhomep0a-20"

    prompt = f"""You are a copywriter for Golden Home Project, an Amazon
affiliate IG account in the home organizing niche.

Task: write a 5-slide carousel post for this product. Carousels are
"saves" content — viewers save the post for later, then DM the keyword
to get the link via auto-reply.

Product: {product}
Affiliate URL: {aff_url}
DM keyword (must appear in CTA + caption): {keyword}
Categories: {cats}

WHO IS WRITING (docs/BRAND_VOICE.md, rev 2026-08-26): the desk that reads Amazon's
best-seller charts every day and keeps the prices. Nobody here has handled this product.

HONESTY RULE — NON-NEGOTIABLE: never claim first-hand use. No "I tried/I bought/I had/
I avoided", no "my kitchen/my closet", no "three weeks ago", no invented result. Write
second person ("your cabinet") or plain description. Ratings, review counts, dimensions
and price are the evidence — and they are more persuasive than a story a reader
half-suspects is fake.

BANNED OPENERS (every AI affiliate account uses these): Picture this, Imagine, Let's be
honest, Here's the thing, We've all been there, Ever wonder, Tired of, Say goodbye to,
POV:, Stop scrolling, I spent $X.

Slides:
  1. HOOK — 5-10 words, earns the swipe. NO NUMBERS (no review counts, stars,
     prices). Nobody saves a post for a statistic; they save it because it is THEIR
     cabinet. Pick ONE angle and commit: second-person scene ("The cabinet you don't
     open when guests are over") / the common mistake ("Stop buying bigger bins") /
     a real constraint ("Renting? No drilling? Try this.") / a question.
     Don't name the product in the hook.
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
- Each must name the ROOM + the SPOT the slide is about, as a photo of a real,
  attractive home: "organized under sink cabinet", "white bathroom vanity drawer",
  "tidy linen closet shelves". 3-5 words.
- Never a bare object ("spray bottles", "pipes", "bins") — bare objects return
  car-care products, construction sites and dirty dishes.
- Aim for calm, bright, aspirational photos of a HOME (add "home" or "house" to the query), not mess, damage, offices or hallways of public buildings.
- No children in the photos: add nothing that invites them (no "kids room"; say "bedroom").

Tips (slides 2-4): only claim product features stated in the product name. General
organizing advice is fine; invented specs are not. No numbers unless they are in the name.

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
    # max_turns=3 (not 1): the CLI intermittently needs an extra turn before
    # emitting the JSON and rc=1's with "Reached max turns" — this gives headroom.
    content = call_claude_json(prompt, max_tokens=2048, max_turns=3, timeout=180)
    if not content:
        return content
    # Same gate the reel path uses. The prompt asks for honesty; this enforces it,
    # because a prompt is a request and a check is a guarantee.
    blob = " ".join(str(content.get(k, "")) for k in
                    ("slide_1", "slide_2", "slide_3", "slide_4", "slide_5", "caption"))
    bad = fabrication_match(blob)
    if bad:
        print(f"[carousel] REJECTED — fabricated first-hand experience: {bad!r}")
        return None
    stock = generic_opener(str(content.get("slide_1", "")))
    if stock:
        print(f"[carousel] REJECTED — stock AI opener: {stock!r}")
        return None
    if re.search(r"\d", str(content.get("slide_1", ""))):
        print(f"[carousel] REJECTED — hook opens on a number: {content.get('slide_1')!r}")
        return None
    return content


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
    except ClaudeUsageLimit as e:
        # Out of subscription quota until a stated reset. Not our bug, and not
        # fixable by retrying in seconds. Skip today's carousel instead of failing
        # the workflow: a red email for a condition that heals itself on a clock
        # trains us to ignore the red emails that matter. Deliberately NOT falling
        # back to templated copy — see claude_slide_content(); templates shipped for
        # weeks and produced zero engagement, which is why this path uses Claude.
        resets = f" (resets {e.resets})" if e.resets else ""
        print(f"::warning::Carousel skipped — Claude subscription out of quota{resets}. "
              f"No carousel generated today; the next scheduled run will pick it up.")
        print(f"[carousel] SKIP: {e}")
        return 0
    except Exception as e:
        print(f"[carousel] ERROR: Claude content failed: {e}", file=sys.stderr)
        return 1

    if not content:
        print("[carousel] SKIP: no usable slide content today (gate rejected it)")
        return 0

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
