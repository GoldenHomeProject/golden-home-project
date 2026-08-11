#!/usr/bin/env python3
"""GHP Pinterest pin generator — the traffic engine half of the strategy.

Why Pinterest (added 2026-05-30): home-organizing is Pinterest's #1 category,
faceless content is normal there, pins are evergreen + keyword-searchable
(behaves like SEO, not a feed), and it is fully automatable. It is the single
best-fit FREE traffic lever for this niche, and until now we only READ
Pinterest RSS for trend signals — we never posted.

Funnel: pin (2:3 vertical graphic) -> BLOG article (our conversion hub) when
one exists for the product, else straight to a monetizable /dp/ affiliate URL.
Driving to the blog builds first-party audience, shows multiple products per
visit, and keeps us inside Pinterest's affiliate-link guidelines.

This script only GENERATES pins + a queue. The actual posting happens on the
Pi via automation/post_pinterest.py (Playwright on the persistent Chromium
profile), mirroring send_ig_dm.py — because a logged-in Pinterest business
account is required and Pinterest, like Meta, blocks scripted sends from the
Mac Chrome MCP path.

Run (local seed):
    PEXELS_API_KEY=xxx CLAUDE_CODE_OAUTH_TOKEN=yyy \
        python3 automation/pinterest_pipeline.py --max 10
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib import parse, request

try:
    from PIL import Image, ImageDraw, ImageFilter, ImageFont
except ImportError:
    print("ERROR: Pillow not installed. pip install Pillow", file=sys.stderr)
    sys.exit(2)

sys.path.insert(0, str(Path(__file__).parent))
from affiliate_links import build_affiliate_url  # noqa: E402
from agent_log import append_log_entry  # noqa: E402

PEXELS_API_KEY = os.environ.get("PEXELS_API_KEY", "").strip()
_BROWSER_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)


def _font(size: int, bold: bool = False):
    """Best-effort clean sans-serif across macOS / Linux (Pi + GH runners)."""
    candidates = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold
        else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf" if bold
        else "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf" if bold
        else "/System/Library/Fonts/Supplemental/Arial.ttf",
    ]
    for p in candidates:
        if os.path.exists(p):
            return ImageFont.truetype(p, size)
    return ImageFont.load_default()


def _wrap(draw, text: str, font, max_w: int) -> list[str]:
    """Greedy word wrap to fit within max_w."""
    lines, cur = [], ""
    for w in text.split():
        trial = (cur + " " + w).strip()
        if draw.textbbox((0, 0), trial, font=font)[2] <= max_w:
            cur = trial
        else:
            if cur:
                lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines


def fetch_pexels(query: str, out_path: Path) -> bool:
    """Portrait Pexels search -> save first hit. Pexels 403s the default
    Python urllib UA, so we send a browser UA (verified 2026-05-29)."""
    if not PEXELS_API_KEY:
        print(f"  [pexels] no API key; gradient fallback for '{query}'")
        return False
    key_id = hashlib.sha256(PEXELS_API_KEY.encode()).hexdigest()[:8]
    print(f"  [pexels] key sha256[:8]={key_id}")
    url = (f"https://api.pexels.com/v1/search?query={parse.quote(query)}"
           f"&per_page=5&orientation=portrait&size=large")
    try:
        req = request.Request(url, headers={
            "Authorization": PEXELS_API_KEY, "User-Agent": _BROWSER_UA})
        with request.urlopen(req, timeout=20) as r:
            data = json.loads(r.read())
    except Exception as e:
        print(f"  [pexels] search failed '{query}': {e}")
        return False
    photos = data.get("photos") or []
    if not photos:
        print(f"  [pexels] no results for '{query}'")
        return False
    src = photos[0].get("src", {}) or {}
    img_url = src.get("portrait") or src.get("large2x") or src.get("large") or src.get("original")
    if not img_url:
        return False
    try:
        with request.urlopen(request.Request(
                img_url, headers={"User-Agent": "GHP-Pinterest/1.0"}), timeout=30) as r:
            out_path.write_bytes(r.read())
        print(f"  [pexels] hit '{query}' -> {out_path.name}")
        return True
    except Exception as e:
        print(f"  [pexels] download failed '{query}': {e}")
        return False

ROOT = Path(__file__).resolve().parent.parent
SOCIAL = ROOT / "social"
REGISTRY_PATH = SOCIAL / "dm_keyword_registry.json"
PINS_DIR = SOCIAL / "pinterest"
QUEUE_PATH = SOCIAL / "pinterest_queue.json"
SITE = "https://goldenhomeproject.com"
RAW_GH_BASE = "https://goldenhomeproject.com"

# Pinterest standard pin is 2:3 (1000x1500).
PIN_W, PIN_H = 1000, 1500

# category token -> (board name, pexels query seed). First match wins, so
# order most-specific first.
BOARD_MAP = [
    ("under-sink", "Under-Sink Organization", "under sink storage"),
    ("closet", "Closet Organization Ideas", "organized closet shelves"),
    ("pantry", "Pantry Organization", "organized pantry shelves"),
    ("kitchen", "Kitchen Organization Ideas", "organized kitchen drawer"),
    ("bathroom", "Bathroom Storage Ideas", "tidy bathroom counter"),
    ("lazy-susan", "Cabinet Organization", "kitchen cabinet turntable"),
    ("shelf-liner", "Shelf & Drawer Liners", "neat lined kitchen drawer"),
    ("patio", "Outdoor & Patio", "cozy patio furniture set"),
    ("outdoor", "Outdoor & Patio", "tidy backyard patio"),
    ("storage", "Home Storage Solutions", "minimal storage baskets"),
]
DEFAULT_BOARD = ("Home Organization Finds", "minimal organized home")


def load_json(p: Path, default):
    if p.exists():
        try:
            return json.loads(p.read_text())
        except Exception:
            return default
    return default


def trending_entries(days: int = 21) -> list[dict]:
    """Products from the daily trending scrape, shaped like registry entries.

    Pinterest went silent 2026-08-03..08-07 because the vetted registry is a FIXED pool:
    once every ASIN in it has been pinned, `already_queued` skips them all and the
    generator emits 0 new pins forever. The queue read "46 total, 0 unposted" while the
    poster logged "queue empty" every day.

    social/trending_picks_<date>.json is refreshed daily by trending_daily.py with
    products scraped off Amazon's live best-seller charts and price/rating verified at
    scrape time, so it is a renewing supply of pinnable, genuinely-selling products.
    Marked status="live" because that verification is what the gate exists to prove.
    """
    out = []
    for path in sorted(SOCIAL.glob("trending_picks_*.json"), reverse=True)[:days]:
        try:
            data = json.loads(path.read_text())
        except (json.JSONDecodeError, OSError):
            continue
        picks = data if isinstance(data, list) else data.get("picks", [])
        for pk in picks:
            asin = (pk.get("asin") or "").strip()
            if not asin:
                continue
            out.append({
                "asin": asin,
                "product_name": pk.get("title") or pk.get("name") or "",
                "categories": [c for c in [pk.get("cat_group"), pk.get("cat_label")] if c],
                "status": "live",
                "verified_price": pk.get("price"),
                "verified_stars": str(pk.get("rating") or ""),
                "verified_reviews": pk.get("reviews"),
                "source": "trending",
            })
    return out


DROPS: dict = {}


def _drop_title(title: str, drop: dict | None) -> str:
    """Front-load a REAL, observed price drop. Never invent or round it up."""
    if not drop:
        return title
    return f"Price drop ${drop['was']:.2f} -> ${drop['now']:.2f}: {title}"


def _drop_desc(desc: str, drop: dict | None) -> str:
    if not drop:
        return desc
    note = (f"Tracked daily: this was ${drop['was']:.2f} on {drop['observed_from']} and "
            f"${drop['now']:.2f} on {drop['observed_to']} ({drop['pct']:.0f}% lower). "
            f"Amazon prices move, so check the live listing. ")
    return note + desc


def _blocked_product(name: str) -> str | None:
    """Apply the SAME standards the trending engine enforces.

    Pinterest had no product filter at all, so it queued Lysol spray and Terro ant
    traps — consumables and pest control on a home-ORGANIZATION brand, the categories
    trending_daily explicitly blocks. One bar for what we promote, not one per channel.
    """
    try:
        from trending_daily import COMMODITY_BLOCK, OFF_BRAND_BLOCK, TITLE_HEAD_CHARS
    except Exception:  # noqa: BLE001 — never let a filter import stop the pipeline
        return None
    head = (name or "")[:TITLE_HEAD_CHARS]
    if COMMODITY_BLOCK.search(head):
        return "commodity/consumable"
    if OFF_BRAND_BLOCK.search(head):
        return "off-brand (health/beauty)"
    if re.search(r"\b(ant|roach|insect|pest|rodent|mouse|bug)\s*(bait|trap|killer|spray)", head, re.I):
        return "pest control"
    return None


def price_drops_map() -> dict:
    """asin -> observed drop, from our own dated snapshots (automation/price_drops.py).

    A verified "was $13.99, now $10.99" is the highest buyer-intent hook we can honestly
    make, and it is the one thing on this site a competitor cannot reproduce with an AI
    prompt — it comes from price history we scraped ourselves, day after day. Research on
    the 2026 core updates is explicit that replicable content is what gets demoted.
    """
    path = SOCIAL / "price_drops.json"
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text())
    except (json.JSONDecodeError, OSError):
        return {}
    return {d["asin"]: d for d in data.get("drops", []) if d.get("asin")}


def registry_entries(reg: dict) -> list[dict]:
    seen, out = set(), []
    # Registry first (DM-funnel entries convert best), then the renewing trending pool.
    for e in (list(reg.get("entries", [])) + list(reg.get("vetted", []))
              + trending_entries()):
        a = (e.get("asin") or "").strip()
        if a and a not in seen:
            seen.add(a)
            out.append(e)
    return out


def board_for(entry: dict) -> tuple[str, str]:
    cats = [c.lower() for c in (entry.get("categories") or [])]
    name = (entry.get("product_name") or "").lower()
    for token, board, q in BOARD_MAP:
        if token in cats or token.replace("-", " ") in name:
            return board, q
    return DEFAULT_BOARD


def _hub_containing(asin: str) -> str | None:
    """The evergreen hub page that ACTUALLY lists this ASIN right now, if any.

    Pinterest best practice (and Pinterest's own preference) is to send traffic to a
    content page rather than straight to a merchant link: the reader gets comparison
    context before deciding, and the click builds signals for a site that currently has
    almost no visitors at all.

    The containment check is the honest part. Sending someone who tapped a food-scale pin
    to a page that does not show that food scale is bait-and-switch — it wastes the click
    and it is exactly the kind of thing that gets a Pinterest account limited. So we only
    route to a hub that genuinely features the product, and fall back to the direct
    affiliate link otherwise.
    """
    posts = ROOT / "blog" / "posts"
    if not posts.exists():
        return None
    for page in sorted(posts.glob("best-*.html")):
        try:
            if asin in page.read_text():
                return f"{SITE}/blog/posts/{page.name}"
        except OSError:
            continue
    return None


def blog_url_for(entry: dict) -> str | None:
    """Prefer an on-site page that really features this product, else None."""
    for u in entry.get("used_in") or []:
        if "blog/posts/" in u and u.endswith(".html"):
            return f"{SITE}/{u.lstrip('/')}"
    return _hub_containing((entry.get("asin") or "").strip())


# Fallback image hooks per board — used only when Claude is unavailable, so
# a down LLM still produces a benefit-led pin (not just the product name).
_BOARD_HOOK = {
    "Under-Sink Organization": "Reclaim Your Cabinet Space",
    "Closet Organization Ideas": "A Closet That Stays Tidy",
    "Pantry Organization": "Finally Find Everything",
    "Kitchen Organization Ideas": "Tame the Kitchen Chaos",
    "Bathroom Storage Ideas": "Clear the Counter Clutter",
    "Cabinet Organization": "No More Digging in Cabinets",
    "Shelf & Drawer Liners": "Protect Every Shelf",
    "Outdoor & Patio": "Make the Patio Yours",
    "Home Storage Solutions": "Storage That Works",
    "Home Organization Finds": "The Find Worth Sharing",
}


def _short_name(name: str) -> str:
    """Trim the brand-y product title to a clean human pin subject.
    Cuts at the first comma OR parenthetical so we never leave a dangling
    '(chrome' fragment."""
    n = name.split(",")[0].split(" (")[0].strip().rstrip("(-– ")
    return (n[:58].rstrip() + "…") if len(n) > 59 else n


def template_copy(entry: dict, board: str) -> dict:
    """Deterministic SEO copy — used when Claude is unavailable so the
    pipeline never hard-fails on cron."""
    name = _short_name(entry.get("product_name", "this organizer"))
    price = entry.get("verified_price", "")
    stars = entry.get("verified_stars", "")
    revs = entry.get("verified_reviews", "")
    topic = board.replace(" Ideas", "").replace(" Finds", "").lower()
    title = f"{name}: {board.replace(' Ideas','').replace(' Finds','')}"[:100]
    overlay = _BOARD_HOOK.get(board, "An Organizing Win")
    bits = [f"{name} is the {topic} upgrade I wish I'd found sooner."]
    if stars and revs:
        bits.append(f"{stars}★ from {revs:,} reviews{(' · ' + price) if price else ''}.")
    bits.append("Tap through for the full breakdown and where to get it.")
    bits.append("Amazon affiliate — I may earn a small commission at no extra cost to you.")
    desc = " ".join(bits)[:480]
    return {
        "title": title,
        "description": desc,
        "overlay_hook": overlay,
        "pexels_query": "",  # filled by board seed
    }


def claude_copy(entry: dict, board: str) -> dict | None:
    """SEO pin copy via the Claude CLI (subscription, not an API key).
    Returns None on any failure so the caller falls back to templates."""
    try:
        from _claude_api import call_claude_json
    except Exception:
        return None
    product = entry.get("product_name", "")
    cats = ", ".join(entry.get("categories") or [])
    price = entry.get("verified_price", "")
    prompt = f"""You write Pinterest pin copy for Golden Home Project, a home
organizing affiliate brand. Pinterest is a SEARCH engine — titles and
descriptions must be keyword-rich and helpful, never clickbait.

Product: {product}
Board: {board}
Categories: {cats}
Price: {price}

Return STRICT JSON:
{{
  "title": "<pin title, <=100 chars, front-load the buyer-intent keyword e.g. 'under sink organizer'>",
  "description": "<200-450 chars, keyword-rich, genuinely useful, one soft CTA to tap through, END with: 'Amazon affiliate — small commission at no extra cost to you.'>",
  "overlay_hook": "<<=6 words for the image text overlay, punchy benefit>",
  "pexels_query": "<2-4 word concrete photo search matching the product context>"
}}"""
    try:
        out = call_claude_json(prompt, max_tokens=1024, max_turns=1, timeout=150)
    except Exception as e:
        print(f"  [claude] copy failed ({e}); using template")
        return None
    if not isinstance(out, dict) or not out.get("title") or not out.get("description"):
        return None
    return out


def _vgrad(top, bottom, w, h) -> Image.Image:
    img = Image.new("RGB", (w, h), top)
    px = img.load()
    for y in range(h):
        t = y / (h - 1)
        px_row = (
            int(top[0] * (1 - t) + bottom[0] * t),
            int(top[1] * (1 - t) + bottom[1] * t),
            int(top[2] * (1 - t) + bottom[2] * t),
        )
        for x in range(w):
            px[x, y] = px_row
    return img


def compose_pin(bg_path: Path | None, overlay_hook: str, subtitle: str,
                price: str) -> Image.Image:
    """One 1000x1500 vertical pin. Photo path = Pexels portrait with a dark
    lower band; type path = warm gradient. Either way the brand domain sits
    at the bottom so the pin is recognizable when re-pinned."""
    base = (28, 65, 50)  # deep teal brand tone
    if bg_path and bg_path.exists():
        canvas = Image.new("RGB", (PIN_W, PIN_H), base)
        bg = Image.open(bg_path).convert("RGB")
        bw, bh = bg.size
        scale = max(PIN_W / bw, PIN_H / bh)
        bg = bg.resize((int(bw * scale), int(bh * scale)), Image.LANCZOS)
        ox, oy = (bg.size[0] - PIN_W) // 2, (bg.size[1] - PIN_H) // 2
        bg = bg.crop((ox, oy, ox + PIN_W, oy + PIN_H)).filter(
            ImageFilter.GaussianBlur(radius=1))
        canvas.paste(bg)
        band_top = int(PIN_H * 0.52)
        overlay = Image.new("RGBA", (PIN_W, PIN_H - band_top), (0, 0, 0, 175))
        canvas.paste(overlay, (0, band_top), overlay)
        text_top = band_top + 70
    else:
        canvas = _vgrad(base, tuple(int(c * 0.6) for c in base), PIN_W, PIN_H)
        text_top = 480

    draw = ImageDraw.Draw(canvas, "RGBA")
    margin = 80
    max_w = PIN_W - 2 * margin

    # hook (big bold)
    hf = _font(86, bold=True)
    lines = _wrap(draw, overlay_hook, hf, max_w)
    y = text_top
    for ln in lines:
        w = draw.textbbox((0, 0), ln, font=hf)[2]
        x = (PIN_W - w) // 2
        draw.text((x + 2, y + 2), ln, font=hf, fill=(0, 0, 0, 160))
        draw.text((x, y), ln, font=hf, fill=(255, 250, 240, 250))
        y += int(86 * 1.18)

    # subtitle (product name, smaller)
    if subtitle:
        sf = _font(40)
        for ln in _wrap(draw, subtitle, sf, max_w)[:3]:
            w = draw.textbbox((0, 0), ln, font=sf)[2]
            draw.text(((PIN_W - w) // 2, y + 14), ln, font=sf, fill=(255, 255, 255, 225))
            y += int(40 * 1.25)

    # price chip
    if price:
        pf = _font(44, bold=True)
        pw = draw.textbbox((0, 0), price, font=pf)[2]
        cx = (PIN_W - pw) // 2
        draw.rounded_rectangle([cx - 28, y + 28, cx + pw + 28, y + 92],
                               radius=14, fill=(193, 92, 60, 255))
        draw.text((cx, y + 36), price, font=pf, fill=(255, 255, 255, 255))

    # brand domain footer
    bf = _font(34, bold=True)
    dom = "goldenhomeproject.com"
    dw = draw.textbbox((0, 0), dom, font=bf)[2]
    draw.text(((PIN_W - dw) // 2, PIN_H - 70), dom, font=bf, fill=(255, 255, 255, 235))
    return canvas


def already_queued(asin: str, queue: list[dict]) -> bool:
    return any(p.get("asin") == asin for p in queue)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--max", type=int, default=10, help="max new pins this run")
    ap.add_argument("--force", action="store_true", help="re-pin even if queued")
    args = ap.parse_args()

    global DROPS
    DROPS = price_drops_map()
    reg = load_json(REGISTRY_PATH, {})
    entries = registry_entries(reg)
    # Priority for the back-to-college sprint (Associates deadline ~2026-09-17):
    #   1. verified price drops  — highest intent, and data only we have
    #   2. dorm/college products — mid-August is peak move-in and it is the one moment
    #      our category, real search demand and buying season line up
    #   3. everything else
    # Without this the generator just walks the registry in insertion order, so the dorm
    # products (newest, therefore last) never got pinned at all.
    def _priority(e):
        if e.get("asin") in DROPS:
            return 0
        cats = [c.lower() for c in (e.get("categories") or [])]
        if "dorm" in cats or "college" in cats:
            return 1
        return 2
    entries.sort(key=_priority)
    if not entries:
        print("ERROR: no registry entries", file=sys.stderr)
        return 1

    PINS_DIR.mkdir(parents=True, exist_ok=True)
    queue = load_json(QUEUE_PATH, [])
    date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    made = 0

    for entry in entries:
        if made >= args.max:
            break
        asin = entry["asin"]
        # Hard gate: only ASIN-verified products may become pins (April 2026
        # dead-ASIN incident). status="live" is set by the verification flow.
        if entry.get("status") != "live":
            print(f"  [skip] {asin} status={entry.get('status')!r} — not ASIN-verified")
            continue
        # A verified price drop is NEW information about a product we may already have
        # pinned at the old price, so it earns a fresh pin. Without this, the two most
        # compelling drops we had were silently skipped for being "already queued".
        why = _blocked_product(entry.get("product_name") or "")
        if why:
            print(f"  [skip] {asin} {why} — {(entry.get('product_name') or '')[:44]}")
            continue
        drop = DROPS.get(asin)
        if not args.force and already_queued(asin, queue) and not drop:
            continue
        if drop and any(p.get("asin") == asin
                        and p.get("drop_observed_to") == drop.get("observed_to")
                        for p in queue):
            continue          # already pinned THIS drop; don't repeat it
        board, board_q = board_for(entry)
        copy = claude_copy(entry, board) or template_copy(entry, board)
        pexels_q = (copy.get("pexels_query") or "").strip() or board_q

        bg_path = PINS_DIR / f"bg-{date_str}-{asin}.jpg"
        bg_ok = fetch_pexels(pexels_q, bg_path)

        price = entry.get("verified_price", "")
        img = compose_pin(
            bg_path if bg_ok else None,
            copy.get("overlay_hook") or _short_name(entry.get("product_name", "")),
            _short_name(entry.get("product_name", "")),
            price,
        )
        img_path = PINS_DIR / f"pin-{date_str}-{asin}.png"
        img.save(img_path, "PNG", optimize=True)

        link = blog_url_for(entry) or build_affiliate_url(asin, "pinterest")
        rel = str(img_path.relative_to(ROOT))
        queue.append({
            "id": f"pin-{date_str}-{asin}",
            "asin": asin,
            "board": board,
            "title": _drop_title(copy["title"], DROPS.get(asin))[:100],
            "description": _drop_desc(copy["description"], DROPS.get(asin))[:500],
            "link": link,
            "image_path": rel,
            "image_url": f"{RAW_GH_BASE}/{rel}",
            "queued_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "posted": False,
            "source": "pinterest_pipeline",
            "drop_observed_to": (DROPS.get(asin) or {}).get("observed_to"),
        })
        made += 1
        print(f"  [pin] {asin} board={board!r} link={'blog' if link.startswith(SITE) else 'amazon'} -> {rel}")

    QUEUE_PATH.write_text(json.dumps(queue, indent=2))
    print(f"[pinterest] generated {made} new pin(s); queue now {len(queue)} total -> {QUEUE_PATH.relative_to(ROOT)}")

    # Commit+push the queue right away: the 06:30 ghp-daily-loop and the
    # ~10:13 ghp-daily-strategy jobs `git reset --hard origin/main`, which
    # silently deleted freshly generated (uncommitted) queue entries.
    if made:
        import subprocess
        def _git(*a):
            return subprocess.run(["git", "-C", str(ROOT), *a],
                                  capture_output=True, text=True, timeout=120)
        try:
            _git("add", str(QUEUE_PATH))
            c = _git("commit", "-m", f"pinterest: queue +{made} pin(s) [generator]")
            if c.returncode == 0:
                _git("pull", "--rebase", "--autostash", "--quiet", "origin", "main")
                p = _git("push", "--quiet", "origin", "main")
                if p.returncode != 0:
                    print(f"[pinterest] queue push failed: {p.stderr.strip()[:200]}")
        except Exception as e:
            print(f"[pinterest] queue git sync error (non-fatal): {e}")

    if made:
        append_log_entry(
            agent="Pinterest Pipeline",
            ran=f"Generated {made} pin(s) for the Pinterest traffic engine",
            changed=str(QUEUE_PATH.relative_to(ROOT)),
            external="Pexels (backgrounds) + Claude CLI (pin copy)",
            hint="post_pinterest.py (Pi) drains pinterest_queue.json once a Pinterest business account is logged into the Pi Chromium profile.",
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
