#!/usr/bin/env python3
"""reel_v2.py — GHP Reels v2, built to marketing's REEL_SPEC_v2.md (2026-11-06).

Ian, 2026-11-06: "the color schemes and mustard letters are not good, we need catchy and
trending videos that go viral and sell product". v2 looks native, not branded:
  * word-by-word karaoke captions (edge-tts word boundaries), white Montserrat ExtraBold with
    a black stroke, the current word in Coral; no boxes, no gold
  * hook in the first 1.2 s, a promise, 3 items (~5 s each), CTA + loop, 15-22 s total
  * smooth, not choppy (Ian 11/06): one continuous shot per beat, no zoom pulses, 24/25 fps
    stock conformed instead of frame-duplicated, a 0.25 s dissolve between beats
  * every product shot shows that kind of product; picks without matching footage drop out
  * one keyword per reel -> goldenhomeproject.com/r/<keyword> with exactly the reel's
    products (ghpig-20), answered by pi/dm-funnel/dm-funnel.py
  * one grade across all stock, music ducked under Ava (+12% rate)
  * item cards: type + price-band chip + one benefit from the listing title (no product photo:
    Amazon product images can't be used off Amazon)

Products come from today's best-seller scan (trending only). Nothing posts from here:
    python3 automation/reel_v2.py --format fixes3 --out social/reels/v2_test
"""
from __future__ import annotations

import argparse
import asyncio
import json
import math
import random
import re
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "automation"))
import pinterest_pipeline as pp  # noqa: E402
import reel_producer as rp  # noqa: E402
import video_pin as vp  # noqa: E402
from brand import price_band  # noqa: E402
from content_quality_gate import fabrication_match  # noqa: E402

W, H = 1080, 1920
SAFE_TOP, SAFE_BOTTOM, SAFE_RIGHT = 220, 420, 140
CORAL, MINT, INK = (255, 90, 78), (61, 220, 151), (17, 20, 24)
FXB = "/usr/share/fonts/truetype/montserrat/Montserrat-ExtraBold.ttf"
FSB = "/usr/share/fonts/truetype/montserrat/Montserrat-SemiBold.ttf"
VOICE, RATE = "en-US-AvaNeural", "+12%"
HOOK_LEDGER = ROOT / "social" / "reel_v2_hooks.json"
FUNNEL = ROOT / "social" / "reel_funnel.json"      # keyword -> this reel's products (dm-funnel.py)
PAGES = ROOT / "r"                                  # goldenhomeproject.com/r/<keyword>
SITE = "https://goldenhomeproject.com"
IG_TAG = "ghpig-20"                                 # Instagram's Associates tracking ID

HOOK_BANK = ["If your sink cabinet looks like this…", "Stop stacking your pans like this.",
             "Renters, you need these.", "POV: your closet finally works.",
             "This is why your counters never stay clean.", "Small apartment? Steal these.",
             "Things that just make sense for a tiny kitchen.", "Your entryway is doing too much."]

FORMATS = {
    "fixes3": dict(n=3, promise="{n} fixes under {band}", ask="complementary items that fix "
                   "one messy space together"),
    "before_after": dict(n=3, promise="Before and after, under {band}", ask="items that take "
                         "ONE space from messy to organized"),
    "makes_sense": dict(n=3, promise="Things that just make sense", ask="clever, "
                        "everyday-useful items for one room"),
    "renter": dict(n=3, promise="Renters, save this", ask="renter-friendly items (no drilling, "
                   "adhesive, over-the-door, tension or freestanding)"),
    "gift": dict(n=3, promise="Gifts under {band} they'll actually use", ask="giftable items"),
    "stop_doing": dict(n=3, promise="Stop doing this", ask="items that each replace a common "
                       "bad habit in one room"),
}


# ------------------------------------------------------------------ script
def _claude_json(prompt: str):
    try:
        from _claude_api import _load_token_file
        _load_token_file()
    except Exception:
        pass
    for _ in range(2):
        try:
            out = subprocess.run(["claude", "-p", "--max-turns", "1"], input=prompt,
                                 capture_output=True, text=True, timeout=200).stdout
            return json.loads(re.search(r"\{.*\}", out, re.S).group())
        except Exception as e:  # noqa: BLE001
            print(f"  [v2] claude reply unusable ({str(e)[:60]})")
    return None


def _recent_hooks(days: int = 14) -> set:
    try:
        led = json.loads(HOOK_LEDGER.read_text())
    except (OSError, ValueError):
        return set()
    cut = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
    return {e["hook"].lower() for e in led if e.get("date", "") >= cut}


def candidates(fmt: str) -> list[dict]:
    if fmt == "gift":
        guides = json.loads((ROOT / "social" / "gift_guides.json").read_text())
        g = random.choice(list(guides.values()))
        return [dict(p, category="Gift") for p in g["picks"]]
    items = pp.chart_now()
    if fmt == "renter":
        # no-install items count too (stock rarely films adhesive hooks; renter failed 11/06)
        items = [i for i in items if re.search(
            r"no drill|adhesive|over the door|over-the-door|tension|freestanding|stick|removable|"
            r"renter|plug.?in|cordless|rechargeable|rolling|cart|lamp|rug|basket|stackable|"
            r"shelf|shelves|curtain|mirror|hanger", i["name"], re.I)]
        return items[:16]
    by = {}
    for i in items:
        if i.get("category") != "Movers":
            by.setdefault(i["category"], []).append(i)
    cats = [c for c, xs in by.items() if len(xs) >= 5]
    return by[random.choice(cats)][:12] if cats else items[:12]


def write_script(fmt: str, strict: bool = True) -> dict | None:
    spec = FORMATS[fmt]
    cand = candidates(fmt)
    if len(cand) < spec["n"]:
        print(f"  [v2] {fmt}: only {len(cand)} candidates")
        return None
    used = _recent_hooks()
    bank = [h for h in HOOK_BANK if h.lower() not in used]
    lst = "\n".join(f"{i}: {c['name']}" for i, c in enumerate(cand))
    got = _claude_json(
        f"Best-selling Amazon products:\n{lst}\n\nWrite a 15-20 second vertical-video script. "
        f"Format: {fmt}. Pick {spec['ask']}: rank up to {spec['n'] + 3}, best first (only the "
        f"first {spec['n']} that have matching stock footage are used). Reply ONLY JSON:\n"
        '{"keywords": ["<3 options: ONE everyday word each, 4-8 letters, naming the space, theme '
        'or a product, e.g. SHOWER, CURTAIN, COZY>"], '
        '"hook": "<scene-first, second person, under 12 words, NO digits; you may adapt one of: '
        + " | ".join(bank) + '>", "space": "<the room or spot, 1-3 words>", '
        '"items": [{"i": <index>, "type": "<generic item, 2-4 words, Title Case; keep a word for '
        'its distinctive look if the title has one, e.g. Rainbow Window Film, Velvet Hangers>", '
        '"benefit": "<what it does for the buyer in plain words, 3-6 words, from facts in THAT title '
        'only, e.g. sponge, brush and soap in one spot / warm glow for any room; not spec-sheet '
        'wording, no speed/durability/result claims the title does not make, no digits unless in the title>", '
        '"problem_query": "<2-4 word stock-video search for the messy/problem moment, no people>", '
        '"solution_query": "<2-4 word stock-video search that would show THIS kind of product or it in use>"}]}\n'
        "Rules: every item must directly fix the exact problem the hook shows in that space, "
        "and no two items may be the same kind of product (no two towels, no two bins). "
        f"Return {spec['n'] + 3} items (at least {spec['n'] + 2}) if the list allows. The video uses real stock footage of each "
        "kind of product, so prefer items that are commonly filmed (hangers, baskets, bins, "
        "jars, towels, blankets, mugs, candles, lamps, plants, rugs, pillows, organizers on a "
        "shelf) over parts rarely filmed (rods, brackets, squeegees, hooks, adapters). "
        "No first person, no claims beyond the titles, no prices or '$'.")
    if not got or len(got.get("items") or []) < spec["n"]:
        return None
    items, seen, kinds = [], set(), set()
    for x in got["items"]:
        try:
            c = cand[int(x["i"])]
        except (KeyError, ValueError, IndexError):
            continue
        allowed = set(re.findall(r"\d+", c["name"]))
        txt = f"{x.get('type', '')} {x.get('benefit', '')}"
        # one of each kind: "Clear String Lights" + "Fairy Lights" both ran on 11/06
        kind = re.sub(r"s$", "", (x.get("type", "").split() or [""])[-1].lower())
        # "Similar to Silk" is satin: never name a product after what it only resembles
        like = {w.lower() for w in re.findall(r"(?:similar to|like|faux|imitation)\s+(\w+)", c["name"], re.I)}
        if like & set(re.findall(r"\w+", txt.lower())):
            print(f"  [v2] skipped item (resemblance named as material): {txt}")
            continue
        if ("$" in txt or fabrication_match(txt) or c["asin"] in seen or kind in kinds
                or any(n not in allowed for n in re.findall(r"\d+", txt))):
            print(f"  [v2] skipped item: {txt}")
            continue
        seen.add(c["asin"])
        kinds.add(kind)
        items.append({**x, "asin": c["asin"], "name": c["name"], "rating": c.get("rating"),
                      "reviews": c.get("reviews"), "chart_rank": c.get("rank"),
                      "price": c.get("price"), "band": price_band(str(c.get("price") or ""))})
    # more ranked picks than slots: footage decides which ones make it (match_footage)
    if len(items) < spec["n"] + (2 if strict else 0):
        print(f"  [v2] only {len(items)} usable picks ranked")
        return None
    # Ian 11/06: only trending products we sell. Every pick must be on today's chart scan
    # (gift reels: on a gift-guide page, which is itself built from the chart + vetted list).
    ok = ({i["asin"] for i in pp.chart_now()} if fmt != "gift"
          else {p["asin"] for g in json.loads((ROOT / "social" / "gift_guides.json").read_text()).values()
                for p in g["picks"]})
    if any(i["asin"] not in ok for i in items):
        print("  [v2] a pick is not on today's chart - rejected")
        return None
    hook = got.get("hook", "").strip()
    if re.search(r"\d", hook) or len(hook.split()) > 12 or fabrication_match(hook):
        print(f"  [v2] rejected hook: {hook}")
        return None
    promise = _promise(fmt, items[:spec["n"]])
    kw = _unique_keyword(got.get("keywords") or [got.get("keyword", "")], got.get("space", ""), fmt,
                         [i["type"] for i in items])
    return {"format": fmt, "hook": hook, "promise": promise, "space": got.get("space", ""),
            "items": items, "keyword": kw}


def rewrite_benefits(items: list) -> None:
    """Older test scripts carry spec-sheet benefits ("precise tare function weighing");
    Marketing 11/06 wants plain buyer language from the title facts only, same gates."""
    lst = "\n".join(f"{n}: {i['name']}" for n, i in enumerate(items))
    got = _claude_json(f"Amazon listing titles:\n{lst}\n\nFor each, write what it does for the buyer in "
                       "plain words, 3-6 words, from facts in THAT title only (e.g. 'sponge, brush and "
                       "soap in one spot', 'warm glow for any room'). No spec-sheet wording, no speed, "
                       "durability or result claims the title doesn't make, no first person, no digits "
                       "unless in the title, no '$'. Reply ONLY JSON: {\"benefits\": [\"...\"]}")
    for i, b in zip(items, (got or {}).get("benefits") or []):
        allowed = set(re.findall(r"\d+", i["name"]))
        claims = set(re.findall(r"\b(longer|faster|seconds?|instantly|never|lasts?|forever|"
                                r"durable|guaranteed|best|perfect|fresh(?:er)?)\b", b.lower()))
        if (b and "$" not in b and not fabrication_match(b) and len(b.split()) <= 7
                and not (claims - set(re.findall(r"\w+", i["name"].lower())))
                and all(n in allowed for n in re.findall(r"\d+", b))):
            i["benefit"] = b.strip().rstrip(".")


def _promise(fmt: str, items: list) -> str:
    """Price band of the dearest pick that made the reel (band only, never exact)."""
    spec = FORMATS[fmt]
    prices = [float(re.sub(r"[^\d.]", "", str(i.get("price") or "0")) or 0) for i in items]
    band = price_band(f"${max(prices):.2f}") if prices else ""
    amt = (re.search(r"\$\d+", band) or [""])[0] if band else ""
    return spec["promise"].format(n=len(items), band=amt).replace("under  ", "").strip()


def _taken_keywords(days: int = 60, fmt: str = "") -> set:
    """Keywords the comment-reply bot already answers: registry (one product each) and
    reel keywords from the last `days` (each answers with that reel's own page)."""
    taken = set()
    try:
        reg = json.loads((ROOT / "social" / "dm_keyword_registry.json").read_text())
        taken |= {str(e.get("keyword") or "").upper() for e in reg.get("entries", [])}
    except (OSError, ValueError):
        pass
    cut = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
    try:
        # every rendered reel holds its keyword: two test reels both took KITCHEN on 11/06
        # and the second overwrote the first one's /r/kitchen page (wrong products)
        # ...except an unposted test of the SAME format: a re-render replaces it (and its page)
        taken |= {k for k, e in json.loads(FUNNEL.read_text()).items() if e.get("date", "") >= cut
                  and (e.get("posted") or e.get("format") != fmt)}
    except (OSError, ValueError):
        pass
    return taken


def _unique_keyword(kws, space: str, fmt: str, types: list | None = None) -> str:
    """One word per reel, so a comment gets exactly this reel's links. 2026-11-06: test
    reels said "Comment LINKS" (no bot answers it) and "CLOTHES" (answered with an
    unrelated product) - a dead funnel."""
    taken = _taken_keywords(fmt=fmt)
    kws = [kws] if isinstance(kws, str) else list(kws or [])
    kw = kws[0] if kws else ""
    words = (kws + space.split()[::-1] + [{"gift": "GIFTS", "renter": "RENTER"}.get(fmt, "")]
             + [(t.split() or [""])[-1] for t in (types or [])])
    for w in words:
        w = re.sub(r"[^A-Za-z]", "", w or "").upper()
        if 4 <= len(w) <= 9 and w not in taken:
            return w
    base = re.sub(r"[^A-Za-z]", "", kw or space or "HOME").upper()[:7] or "HOME"
    for suffix in "SXYZ":
        if base + suffix not in taken:
            return base + suffix
    return base + datetime.now().strftime("%d")


def publish_links(s: dict, reel: str) -> str:
    """goldenhomeproject.com/r/<keyword>: exactly this reel's products, Instagram-tagged,
    plus the funnel entry the comment-reply bot answers. Returns the page URL."""
    import html
    kw = s["keyword"]
    slug = kw.lower()
    PAGES.mkdir(exist_ok=True)
    head = (ROOT / "blog" / "posts" / "best-bathroom-essentials.html").read_text().split("<body>")[0]
    title = f"{s['promise'].rstrip('.')}: the picks from our video"
    url = f"{SITE}/r/{slug}"
    head = re.sub(r"<title>.*?</title>", f"<title>{html.escape(title)} | Golden Home Project</title>",
                  head, flags=re.S)
    head = re.sub(r'(<link rel="canonical" href=")[^"]*', lambda m: m.group(1) + url, head)
    head = re.sub(r'(<meta property="og:title" content=")[^"]*', lambda m: m.group(1) + html.escape(title), head)
    head = re.sub(r'(<meta property="og:url" content=")[^"]*', lambda m: m.group(1) + url, head)
    head = head.replace("<head>", '<head>\n  <meta name="robots" content="noindex">', 1)
    sub = f"reel_{slug}_{datetime.now():%Y%m%d}"
    cards = []
    for n, it in enumerate(s["items"], 1):
        facts = " &middot; ".join(x for x in (
            f"{it['rating']}&#9733;" if it.get("rating") else "",
            f"{int(it['reviews']):,}+ ratings" if it.get("reviews") else "",
            html.escape(it["band"].lower())) if x)
        cards.append(f"""    <div class="product-card">
      <span class="pick-badge">{n}. {html.escape(it['type'])}</span>
      <div class="product-name">{html.escape(it['name'])}</div>
      <div class="product-rating">{facts}</div>
      <ul class="value-stack"><li>{html.escape(it['benefit'])}</li></ul>
      <a class="cta" href="https://www.amazon.com/dp/{it['asin']}?tag={IG_TAG}&amp;ascsubtag={sub}" rel="sponsored nofollow noopener" target="_blank">See it on Amazon &rarr;</a>
    </div>""")
    (PAGES / f"{slug}.html").write_text(f"""{head}<body>
<div class="wrap">
  <h1>{html.escape(title)}</h1>
  <div class="affiliate-disclosure">As an Amazon Associate, Golden Home Project earns from qualifying purchases. Prices change often; check the live listing.</div>
  <div class="intro"><p>Every product in the video, in order. Each one is a current Amazon best-seller with thousands of ratings. We have not tested these ourselves; the ratings are the evidence.</p></div>
  <section class="post-section">
{chr(10).join(cards)}
  </section>
  <a class="back-link" href="/links.html">&larr; More finds from our videos</a>
</div>
</body>
</html>
""")
    try:
        fun = json.loads(FUNNEL.read_text()) if FUNNEL.exists() else {}
    except ValueError:
        fun = {}
    fun[kw] = {"date": datetime.now().strftime("%Y-%m-%d"), "reel": reel, "page": url,
               "format": s["format"], "posted": False,
               "items": [{k: it.get(k) for k in ("asin", "type", "band")} for it in s["items"]]}
    FUNNEL.write_text(json.dumps(fun, indent=1))
    return url


def segments(s: dict) -> list[dict]:
    segs = [{"kind": "hook", "say": s["hook"]},
            {"kind": "promise", "say": s["promise"]}]
    for n, it in enumerate(s["items"], 1):
        band = it["band"].lower()
        # "things that just make sense" is rapid-fire (spec: ~1 s per item): name + band
        # spoken, the benefit lives on the card. 4 full items ran 26.8 s on 2026-11-06.
        say = (f"{it['type']}, {band}." if s["format"] == "makes_sense"
               else f"{it['type']}, {band}. {it['benefit']}.")
        segs.append({"kind": "item", "n": n, "item": it, "say": say})
    segs.append({"kind": "cta", "say": f"Comment {s['keyword']} and we'll reply with the links."})
    return segs


# ------------------------------------------------------------------ voice
async def _tts(text: str, out: Path) -> list:
    import edge_tts
    words = []
    comm = edge_tts.Communicate(text, VOICE, rate=RATE, boundary="WordBoundary")
    with open(out, "wb") as f:
        async for ch in comm.stream():
            if ch["type"] == "audio":
                f.write(ch["data"])
            elif ch["type"] == "WordBoundary":
                words.append((ch["offset"] / 1e7, ch["duration"] / 1e7, ch["text"]))
    return words


def _dur(p: Path) -> float:
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of",
                        "csv=p=0", str(p)], capture_output=True, text=True)
    return float(r.stdout.strip() or 0)


def voice(segs: list, work: Path) -> Path:
    """One Ava clip per segment so the cut points land exactly on the spoken beats."""
    t = 0.0
    parts = []
    for i, sg in enumerate(segs):
        mp3 = work / f"vo{i}.mp3"
        words = asyncio.run(_tts(sg["say"], mp3))
        if not mp3.exists() or mp3.stat().st_size < 2000 or not words:
            raise RuntimeError(f"voice failed on segment {i}")
        d = _dur(mp3)
        gap = 0.08
        sg.update(start=t, dur=max(d + gap, 1.0 if sg["kind"] == "hook" else 1.2),
                  words=[(t + o, du, w) for o, du, w in words])
        if sg["kind"] == "cta":
            sg["dur"] = max(sg["dur"], 2.6)
        wav = work / f"vo{i}.wav"
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(mp3), "-af",
                        f"apad=whole_dur={sg['dur']}", "-ar", "44100", "-ac", "2", str(wav)], check=True)
        parts.append(wav)
        t += sg["dur"]
    lst = work / "vo.txt"
    lst.write_text("".join(f"file '{p}'\n" for p in parts))
    vo = work / "vo.wav"
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i",
                    str(lst), "-c", "copy", str(vo)], check=True)
    return vo


# ------------------------------------------------------------------ footage
def find_clip(queries, visual: str, work: Path, need: float = 2.6, cap: int = 10) -> Path | None:
    """Specific search first, then broader ones (stock libraries rarely have the exact
    micro-moment: "stained bare mattress" found nothing usable on 2026-11-06)."""
    if isinstance(queries, str):
        queries = [queries]
    judged_total = 0
    visual += ". Reject it if readable brand names, logos or on-screen text are visible."
    for q in dict.fromkeys(q for q in queries if q):
        judged = 0
        # 30/60 fps first: they play with no conform at all (24/25 fps get sped up 1.2x)
        for v in sorted(vp._search(q), key=lambda v: 0 if _native30(v) else 1):
            if judged >= 3 or judged_total >= cap:
                break
            vid = v.get("id")
            if (_blocked(vid) or vid in rp._SEEN_THIS_REEL or float(v.get("duration") or 0) < need
                    or vp._slug_words(v) & set(vp.UNSAFE) or not vp._best_file(v)):
                continue
            rp._SEEN_THIS_REEL.add(vid)
            lo, sheet = work / f"v{vid}-lo.mp4", work / f"v{vid}-sheet.jpg"
            small = vp._small_file(v)
            if not small or not vp._get(small, lo) or not vp._contact_sheet(lo, need, sheet):
                continue
            judged += 1
            judged_total += 1
            d = _judge_shot(sheet, visual)
            note = str(d.get("note") or "").lower()
            ok = (d.get("fits") and d.get("face_visible") is False and d.get("text_visible") is False
                  and not d.get("nsfw") and int(d.get("score") or 0) >= 7
                  and not re.search(r"\breject|(?<!no )visible (brand|logo|label|text)|brand (label|name)s? "
                                    r"(is |are )?visible|readable (brand|label|text)", note))
            print(f"    clip {vid} ({q!r}): {'OK' if ok else 'reject'} — {str(d.get('note'))[:50]}")
            if not ok:
                continue
            hd = work / f"v{vid}.mp4"
            if vp._get(vp._best_file(v), hd):
                _mark_test(vid)
                return hd
    return None


def _ask_json(prompt: str) -> dict:
    try:
        from _claude_api import _load_token_file
        _load_token_file()
    except Exception:
        pass
    try:
        out = subprocess.run(["claude", "-p", "--allowedTools", "Read", "--max-turns", "3"],
                             input=prompt, capture_output=True, text=True, timeout=150).stdout
        m = re.search(r"\{.*\}", out, re.S)
        return json.loads(m.group()) if m else {}
    except Exception as e:  # noqa: BLE001
        return {"note": f"check failed: {e}"}


def _judge_shot(sheet: Path, visual: str) -> dict:
    """Scene shots (hook / after): same structured flags as product shots. rp._judge_scene
    has no text flag; a candle with a readable "TUSCANY" label opened the 11/06 gift reel."""
    return _ask_json(
        f"Read the image file {sheet}: three frames (start, middle, end) of a stock clip. "
        f"Wanted shot: {visual}\nReply ONLY JSON: {{\"fits\": true/false (the clip shows that "
        "shot in most frames), \"face_visible\": true/false (a person's face is clearly "
        "visible), \"text_visible\": true/false (readable brand names, labels, logos or "
        "on-screen text anywhere, including product labels and screens), \"nsfw\": true/false, "
        "\"score\": 1-10 appeal as an Instagram home reel shot, \"note\": \"<10 words>\"}}")


def _judge_kinds(sheet: Path, kinds: list, space: str) -> dict:
    """One look per clip, answered against every still-unfilled product kind: a sheer
    curtain clip rejected for "blackout curtains" is exactly what "sheer curtains" needs."""
    prompt = (f"Read the image file {sheet}: three frames (start, middle, end) of a stock clip "
              f"for a home-products reel set in a {space}.\nProduct kinds:\n"
              + "\n".join(f"{i}: {k}" for i, k in enumerate(kinds)) +
              "\nThe object itself must be clearly visible and recognizable in most frames (a room "
              "it could belong in is NOT enough), and its colour/material must not contradict the "
              "listing: colour, pattern, style and design must match (gold tinsel is not silver "
              "tinsel; frosted film is not a rainbow stained-glass film). The product must be the "
              "main subject, not a small or blurry part of the frame. It must be the PRODUCT "
              "ITSELF, not what it holds or works with: a sponge is not a sponge holder, a jug of oil "
              "is not an oil sprayer, a plant is not a planter."
              "\nReply ONLY JSON: {\"shows\": <index of the ONE kind the clip clearly shows "
              "(that kind of object, or one being used), or -1 if none>, "
              "\"face_visible\": true/false (a person's face is clearly visible), "
              "\"text_visible\": true/false (readable brand names, logos or on-screen text), "
              "\"nsfw\": true/false (nudity, underwear, suggestive), "
              "\"score\": 1-10 appeal as an Instagram home reel shot, \"note\": \"<10 words>\"}")
    try:
        from _claude_api import _load_token_file
        _load_token_file()
    except Exception:
        pass
    try:
        out = subprocess.run(["claude", "-p", "--allowedTools", "Read", "--max-turns", "3"],
                             input=prompt, capture_output=True, text=True, timeout=150).stdout
        m = re.search(r"\{.*\}", out, re.S)
        return json.loads(m.group()) if m else {}
    except Exception as e:  # noqa: BLE001
        return {"note": f"check failed: {e}"}


def match_footage(items: list, space: str, n: int, work: Path, budget: int = 36) -> dict:
    """Ranked picks -> {index: clip} for the picks real stock footage actually shows."""
    got, judged = {}, 0
    for idx, it in enumerate(items):
        if len(got) >= n or judged >= budget:
            break
        for q in dict.fromkeys([it["solution_query"], it["type"].lower()]):
            per_q = 0
            for v in sorted(vp._search(q), key=lambda v: 0 if _native30(v) else 1):
                if idx in got or per_q >= 3 or judged >= budget:
                    break
                vid = v.get("id")
                if (_blocked(vid) or vid in rp._SEEN_THIS_REEL or float(v.get("duration") or 0) < 4.5
                        or vp._slug_words(v) & set(vp.UNSAFE) or not vp._best_file(v)):
                    continue
                rp._SEEN_THIS_REEL.add(vid)
                lo, sheet = work / f"v{vid}-lo.mp4", work / f"v{vid}-sheet.jpg"
                small = vp._small_file(v)
                if not small or not vp._get(small, lo) or not vp._contact_sheet(lo, 4.5, sheet):
                    continue
                per_q += 1
                judged += 1
                open_idx = [j for j in range(len(items)) if j not in got]
                d = _judge_kinds(sheet, [f"{items[j]['type'].lower()} (listing: {items[j]['name'][:90]})"
                                         for j in open_idx], space)
                k = d.get("shows")
                ok = (isinstance(k, int) and 0 <= k < len(open_idx) and d.get("face_visible") is False
                      and d.get("text_visible") is False and not d.get("nsfw")
                      and int(d.get("score") or 0) >= 6)     # relevance first; 6 = a fine shot
                who = items[open_idx[k]]["type"] if ok else "-"
                print(f"    clip {vid} ({q!r}): {'-> ' + who if ok else 'reject'} — {str(d.get('note'))[:50]}")
                if ok:
                    hd = work / f"v{vid}.mp4"
                    # one retry: a TLS timeout lost a matched clip on 11/06
                    if vp._get(vp._best_file(v), hd) or vp._get(vp._best_file(v), hd):
                        _mark_test(vid)
                        got[open_idx[k]] = hd
            if idx in got:
                break
    return got


TEST_CLIPS = ROOT / "social" / "reel_v2_test_clips.json"


def _test_clips() -> set:
    try:
        return set(json.loads(TEST_CLIPS.read_text()))
    except (OSError, ValueError):
        return set()


def _blocked(vid) -> bool:
    """Used by a POSTED video elsewhere. Unposted v2 test renders keep their own ledger, so
    re-rendering a test doesn't burn the best clips (KITCHEN found 1 of 4 on 11/06 because
    its earlier test clips were all marked used)."""
    return vid in vp._used() and vid not in _test_clips()


def _mark_test(vid) -> None:
    TEST_CLIPS.write_text(json.dumps(sorted(_test_clips() | {vid})))


def _native30(v: dict) -> bool:
    fps = [f.get("fps") or 0 for f in v.get("video_files") or [] if f.get("fps")]
    return bool(fps) and any(abs(x - 30) < 1 or abs(x - 60) < 1.5 for x in fps)


GRADE = ("eq=contrast=1.08:saturation=1.06:brightness=0.0,"
         "colorbalance=rs=0.03:gs=0.01:bs=-0.03:rm=0.02:bm=-0.02")


def _fps(p: Path) -> float:
    r = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v", "-show_entries",
                        "stream=r_frame_rate", "-of", "csv=p=0", str(p)], capture_output=True, text=True)
    try:
        a, b = (r.stdout.strip() or "30/1").split("/")
        return float(a) / float(b)
    except ValueError:
        return 30.0


def _conform(src: Path) -> tuple[str, float]:
    """Filter that plays every source frame once at 30 fps, and the speed it implies.
    Ian 2026-11-06, v2 renter: "the video seems choppy". Half of Pexels is 24/25 fps;
    fps=30 duplicated every 5th frame (judder). 50/60 fps halve cleanly; 24/25 fps
    are conformed (played 1.2-1.25x) instead of padded with repeated frames."""
    r = _fps(src)
    pre = ""
    if r > 40:
        pre, r = f"fps={r / 2:.3f}:round=near,", r / 2
    speed = 30.0 / r if abs(r - 30) > 0.5 else 1.0
    return pre + (f"setpts=PTS/{speed:.4f}," if speed != 1.0 else ""), speed


def shot(src: Path, start: float, dur: float, out: Path, speed: float | None = None) -> Path:
    """One continuous cut: crop to 9:16, the shared grade, no zoom (the 106->100% punch-in
    on every cut read as the picture jumping in and out). `speed` < 1 slows a clip that is
    too short (smooth slow motion beats a freeze); tpad only guards the frame count."""
    pre, native = _conform(src)
    speed = speed or native
    if speed != native:
        pre = pre.split("setpts")[0] + f"setpts=PTS/{speed:.4f},"
    vf = (f"{pre}scale={W}:{H}:force_original_aspect_ratio=increase:flags=lanczos,crop={W}:{H},"
          f"fps=30,{GRADE},scale=out_range=tv,format=yuv420p,tpad=stop_mode=clone:stop_duration=1")
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-ss", f"{start:.2f}", "-t",
                    f"{dur * speed + 0.1:.2f}", "-i", str(src), "-vf", vf, "-an", "-t", f"{dur:.3f}",
                    "-r", "30", "-c:v", "libx264", "-preset", "veryfast", "-crf", "18",
                    "-color_range", "tv", str(out)], check=True)
    return out


_CURSOR: dict = {}          # clip -> next unused source second, so a reused clip moves on


def segment_video(sg: dict, clips: list[Path], work: Path, idx: int, tail: float) -> Path:
    """One continuous shot per clip (problem, then solution on the benefit line); never
    ping-pong between clips. Pad `tail` for the dissolve into the next beat."""
    # +0.2 s spare: an xfade whose first input is one frame short drops the rest
    total = sg["dur"] + tail + 0.2
    if len(clips) == 2 and sg.get("split"):
        lens = [sg["split"], total - sg["split"]]
    else:
        clips = clips[:1]
        lens = [total]
    shots = []
    for k, (c, ln) in enumerate(zip(clips, lens)):
        speed = _conform(c)[1]
        cd = _dur(c)
        st = _CURSOR.get(c, 0.3)
        if st + ln * speed > cd - 0.1:
            st = max(0.0, min(0.3, cd - ln * speed - 0.1))
        if st + ln * speed > cd - 0.1:            # clip shorter than the beat: slow it down
            speed = max(0.5, (cd - st - 0.1) / ln)
        # advance by what is SEEN (not the transition padding), so the same clip continues
        # seamlessly in the next beat (hook -> promise)
        seen = ln - (tail + 0.2 if k == len(lens) - 1 else 0.0)
        _CURSOR[c] = st + seen * speed
        shots.append(shot(c, st, ln, work / f"s{idx}_{k}.mp4", speed))
    lst = work / f"seg{idx}.txt"
    lst.write_text("".join(f"file '{s}'\n" for s in shots))
    out = work / f"seg{idx}.mp4"
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i",
                    str(lst), "-c", "copy", str(out)], check=True)
    return out


# ------------------------------------------------------------------ graphics
def _font(path, size):
    return ImageFont.truetype(path, size)


def item_card(it: dict, n: int, out: Path) -> Path:
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    x0, y0, x1 = 70, SAFE_TOP + 40, W - SAFE_RIGHT
    tf, bf, cf, nf = _font(FXB, 60), _font(FSB, 40), _font(FXB, 40), _font(FXB, 44)
    lines = rp._wrap_lines(it["type"], tf, x1 - x0 - 140)[:2]
    blines = rp._wrap_lines(it["benefit"], bf, x1 - x0 - 200)[:2]
    h = 60 + 72 * len(lines) + 70 + 20 + 52 * len(blines) + 30
    d.rounded_rectangle([x0, y0, x1, y0 + h], radius=34, fill=INK + (217,))
    d.ellipse([x0 + 34, y0 + 34, x0 + 106, y0 + 106], fill=CORAL)
    d.text((x0 + 70 - d.textlength(str(n), font=nf) / 2, y0 + 44), str(n), font=nf, fill=(255, 255, 255))
    y = y0 + 40
    for ln in lines:
        d.text((x0 + 130, y), ln, font=tf, fill=(255, 255, 255))
        y += 72
    band = it["band"]
    bw = d.textlength(band, font=cf)
    d.rounded_rectangle([x0 + 130, y + 10, x0 + 130 + bw + 44, y + 70], radius=30, fill=CORAL)
    d.text((x0 + 152, y + 18), band, font=cf, fill=(255, 255, 255))
    y += 90
    # Montserrat has no ✓ glyph (rendered as a box on 2026-11-06), so draw the tick.
    d.line([(x0 + 132, y + 26), (x0 + 145, y + 39), (x0 + 166, y + 12)], fill=MINT, width=7,
           joint="curve")
    for bl in blines:
        d.text((x0 + 185, y + 2), bl, font=bf, fill=(255, 255, 255, 230))
        y += 52
    img.save(out)
    return out


def cta_card(kw: str, out: Path) -> Path:
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    big, small, wm = _font(FXB, 96), _font(FSB, 44), _font(FXB, 34)
    cy = 760
    for txt, fill in (("Comment", (255, 255, 255)), (kw, CORAL), ("for the links", (255, 255, 255))):
        tw = d.textlength(txt, font=big)
        d.text(((W - SAFE_RIGHT + 60 - tw) / 2, cy), txt, font=big, fill=fill,
               stroke_width=8, stroke_fill=(0, 0, 0))
        cy += 118
    s = f"or goldenhomeproject.com/r/{kw.lower()}"
    d.text(((W - SAFE_RIGHT + 60 - d.textlength(s, font=small)) / 2, cy + 30), s, font=small,
           fill=(255, 255, 255), stroke_width=5, stroke_fill=(0, 0, 0))
    w = "golden home"
    d.text(((W - d.textlength(w, font=wm)) / 2, H - SAFE_BOTTOM - 70), w, font=wm, fill=(255, 255, 255, 153))
    img.save(out)
    return out


def _ass_time(t: float) -> str:
    return f"{int(t // 3600)}:{int(t % 3600 // 60):02d}:{t % 60:05.2f}"


def captions(segs: list, out: Path) -> Path:
    """Karaoke: each word shows its whole line, current word in Coral, popping 85->100%."""
    hdr = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {W}
PlayResY: {H}
WrapStyle: 0

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Cap,Montserrat ExtraBold,82,&H00FFFFFF,&H00FFFFFF,&H00000000,&H64000000,0,0,0,0,100,100,0,0,1,7,3,2,80,{SAFE_RIGHT + 60},560,1
Style: Tag,Montserrat ExtraBold,64,&H0097DC3D,&H0097DC3D,&H00000000,&H64000000,0,0,0,0,100,100,6,0,1,6,2,7,80,{SAFE_RIGHT + 60},{SAFE_TOP + 10},1
Style: Hook,Montserrat ExtraBold,104,&H00FFFFFF,&H00FFFFFF,&H00000000,&H64000000,0,0,0,0,100,100,0,0,1,8,3,8,80,{SAFE_RIGHT + 60},{SAFE_TOP + 120},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    ev = []
    for sg in segs:
        if sg.get("tag"):
            ev.append(f"Dialogue: 1,{_ass_time(sg['start'])},{_ass_time(sg['start'] + sg['dur'])},"
                      f"Tag,,0,0,0,,{sg['tag']}")
        if sg["kind"] == "cta":
            continue
        style = "Hook" if sg["kind"] in ("hook", "promise") else "Cap"
        ws = sg["words"]
        # Caption lines never cross a comma or full stop ("Hooks under" / "$15 heavy duty"
        # read badly on 11/06): phrase lengths come from the script text, word times from TTS.
        stops, acc = set(), 0
        for ph in re.split(r"[,.!?:;]", sg["say"]):
            acc += len(ph.split())
            stops.add(acc)
        if acc != len(ws):
            stops = set()               # TTS split words differently; fall back to length only
        if sg["kind"] == "item":
            # Marketing 11/06: the card already says name + price; the caption is the benefit
            sl = sorted(stops)
            skip = sl[1] if len(sl) > 2 else len(ws)
            ws = ws[skip:]
            stops = {x - skip for x in stops if x > skip}
        lines, cur = [], []
        for k, w in enumerate(ws):
            cur.append(w)
            if style == "Cap" and (k + 1) in stops:
                lines.append(cur)
                cur = []
                continue
            if style == "Cap" and (len(cur) >= 4 or len(" ".join(x[2] for x in cur)) > 22):
                lines.append(cur)
                cur = []
        if cur:
            lines.append(cur)
        seg_end = sg["start"] + sg["dur"]
        for li, line in enumerate(lines):
            nxt = lines[li + 1][0][0] if li + 1 < len(lines) else seg_end
            for wi, (t0, du, w) in enumerate(line):
                t1 = line[wi + 1][0] if wi + 1 < len(line) else nxt
                parts = []
                for wj, (_, _, w2) in enumerate(line):
                    w2 = w2.replace("{", "").replace("}", "")
                    if wj == wi:
                        parts.append("{\\c&H4E5AFF&\\fscx94\\fscy94\\t(0,100,\\fscx100\\fscy100)}"
                                     + w2 + "{\\r}")
                    else:
                        parts.append(w2)
                ev.append(f"Dialogue: 0,{_ass_time(t0)},{_ass_time(max(t1, t0 + 0.08))},{style},,0,0,0,,"
                          + " ".join(parts))
    out.write_text(hdr + "\n".join(ev) + "\n")
    return out


# ------------------------------------------------------------------ assemble
CLIP_CACHE = Path.home() / ".ghp-engagement" / "reel_v2_clips"


def _vid_of(p: Path) -> int:
    return int(re.search(r"v(\d+)", p.name).group(1))


def _cached(vid) -> Path:
    """A locked clip: the cached HD file, or the same Pexels video fetched again by id."""
    CLIP_CACHE.mkdir(parents=True, exist_ok=True)
    dest = CLIP_CACHE / f"v{vid}.mp4"
    if not dest.exists():
        from urllib import request
        req = request.Request(f"https://api.pexels.com/videos/videos/{vid}",
                              headers={"Authorization": vp.PEXELS_API_KEY, "User-Agent": vp.UA})
        v = json.loads(request.urlopen(req, timeout=20).read())
        if not vp._get(vp._best_file(v), dest):
            raise RuntimeError(f"locked clip {vid} unavailable")
    return dest


def _lock(s: dict, hook_clip: Path, promise_clip: Path, clip_for: dict, problem_shot: bool) -> None:
    """Remember the exact shots, so a copy-only re-render (--from-script) keeps the footage:
    the judge varies run to run, and KITCHEN lost its sponge-holder clip on a re-render 11/06."""
    import shutil
    CLIP_CACHE.mkdir(parents=True, exist_ok=True)
    for c in [hook_clip, promise_clip, *clip_for.values()]:
        if c.parent != CLIP_CACHE and not (CLIP_CACHE / c.name).exists():
            shutil.copy2(c, CLIP_CACHE / c.name)
    s["clip_ids"] = {"hook": _vid_of(hook_clip), "promise": _vid_of(promise_clip),
                     "problem_shot": problem_shot,
                     "items": {a: _vid_of(c) for a, c in clip_for.items()}}


def build(s: dict, out_path: Path, work: Path) -> Path:
    work.mkdir(parents=True, exist_ok=True)
    rp._SEEN_THIS_REEL.clear()
    _CURSOR.clear()
    space = s.get("space") or "home"
    n = FORMATS[s["format"]]["n"]
    # Footage decides which ranked picks make the reel. Ian 11/06: "make sure ... everything
    # matches". Each product needs a clip that shows that kind of product (or it in use);
    # stock rarely has e.g. a tension shower rod, so those picks drop out rather than
    # sitting over an unrelated shot.
    lock = s.get("clip_ids")
    if lock:
        chosen = [(it, _cached(lock["items"][it["asin"]])) for it in s["items"] if it["asin"] in lock["items"]]
    else:
        got = match_footage(s["items"], space, n, work)
        chosen = [(s["items"][j], got[j]) for j in sorted(got)][:n]
    for it in s["items"]:
        print(f"    {'matched' if any(it is c[0] for c in chosen) else 'no footage'}: {it['type']}")
    if len(chosen) < max(2, n - 1):         # "2 fixes" beats a product over the wrong shot
        raise RuntimeError(f"only {len(chosen)} of {n} picks have matching footage")
    s["items"] = [it for it, _ in chosen]
    s["promise"] = _promise(s["format"], s["items"])
    # the keyword must name something on screen: "WRAP" survived after the hair wrap dropped
    shown = " ".join([space, s["hook"]] + [i["type"] for i in s["items"]]).lower()
    if s["keyword"].lower().rstrip("s") not in shown:
        s["keyword"] = _unique_keyword([(i["type"].split() or [""])[-1] for i in s["items"]],
                                       space, s["format"], [i["type"] for i in s["items"]])
    clip_for = {it["asin"]: c for it, c in chosen}
    hook_clip = _cached(lock["hook"]) if lock else (find_clip([s["items"][0]["problem_query"], f"messy {space}", f"{space} interior", space],
                           f"a real {space} that fits this opening line: \"{s['hook']}\". If the "
                           "line points at a problem (looks like this, doing too much, stop doing "
                           "this), the shot must SHOW that problem: messy, cluttered, bare or "
                           "disorganized. A spotless styled showroom does NOT fit. No people in "
                           "focus", work, need=5.0))
    problem_shot = lock.get("problem_shot", True) if lock else bool(hook_clip)
    if not hook_clip:
        # No shot of the problem: open on an inviting shot of its own (reusing product 1's
        # clip held one white cup on screen for 9 s, gift 11/06), and drop any hook line
        # that promises a mess ("If your porch looks like this..." over a tidy wreath).
        gift = s["format"] == "gift"
        hook_clip = (find_clip(["wrapping gifts", "christmas gifts", "gift box"] if gift
                               else [f"cozy {space}", f"{space} interior", "home interior"],
                               "hands wrapping gifts or wrapped gifts, warm and inviting" if gift
                               else f"a real, lived-in {space} (ordinary or a bit cluttered; not a "
                               "staged showroom and not a close-up of a product)", work, need=5.0))
        if not hook_clip:
            # opening on product 1's clip held one shot ~9 s (before_after 11/06); only the
            # rapid-fire format can afford it. Others retry with a fresh script.
            raise RuntimeError("no usable opening shot")
        if gift or re.search(r"looks? like this|doing too much|stop |never stay|this is why|bare|messy|cluttered", s["hook"], re.I):
            s["hook"] = ("The easiest yes on their list." if gift
                         else f"Your {space.lower()} needs these.")
        if s["format"] in ("stop_doing", "before_after", "fixes3"):
            # nothing on screen to stop / fix / be "before": promise upgrades instead
            amt = (re.search(r"\$\d+", _promise("fixes3", s["items"])) or [""])[0]
            s["promise"] = f"{len(s['items'])} upgrades under {amt}" if amt else "Upgrades that make sense"
    # Ian 11/06: "just makes sense is repeated twice?" - hook and promise may not share a phrase
    def _bigrams(t):
        w = re.findall(r"[a-z']+", t.lower())
        return {" ".join(w[k:k + 2]) for k in range(len(w) - 1)}
    if _bigrams(s["hook"]) & _bigrams(s["promise"]) or (
            {w for w in re.findall(r"[a-z]+", s["hook"].lower()) if len(w) > 4}
            & {w for w in re.findall(r"[a-z]+", s["promise"].lower()) if len(w) > 4}):
        s["hook"] = f"Your {space.lower()} needs these." if "needs these" not in s["promise"].lower() else "Steal these."
    segs = segments(s)
    vo = voice(segs, work)
    # Marketing 11/06: the opening shot held ~5 s across hook + promise; the promise beat
    # gets a second lived-in shot so no opening shot holds much past 2 s
    gift = s["format"] == "gift"
    promise_clip = _cached(lock["promise"]) if lock and lock.get("promise") else find_clip(["wrapped gifts pile", "christmas presents", "gifts under tree"] if gift
                             else [f"cozy {space}", f"lived in {space}", f"{space} morning"],
                             "a pile of wrapped gifts or a cozy holiday room, no people in focus" if gift
                             else f"a different real, lived-in {space} (not a staged showroom, not a "
                             "product close-up)", work, need=3.0) or hook_clip
    _lock(s, hook_clip, promise_clip, clip_for, problem_shot)
    for sg in segs:
        if sg["kind"] == "item":
            sg["clips"] = [clip_for[sg["item"]["asin"]]]   # one continuous, matching shot
        elif sg["kind"] == "promise":
            sg["clips"] = [promise_clip]
        else:
            sg["clips"] = [hook_clip]   # CTA returns to the opening shot (loop)
    if s["format"] == "before_after" and problem_shot:
        # the format promises a reveal: BEFORE on the opening shot, AFTER on a finished space
        after = find_clip([f"organized {space}", f"styled {space}", f"clean {space}", f"decorated {space}"],
                          f"the same kind of space ({space}) looking tidy, styled and finished: "
                          "the 'after' shot", work, need=4.0)
        for sg in segs:
            if sg["kind"] in ("hook", "promise"):
                sg["tag"] = "BEFORE"
            elif sg["kind"] == "cta" and after:
                sg["clips"], sg["tag"] = [after], "AFTER"
    real = sum(1 for sg in segs for c in sg["clips"] if c is not hook_clip) + 1
    print(f"    footage: {real} real clips")
    # per-segment video with transition tails
    trans = []
    for i, sg in enumerate(segs[:-1]):
        nxt = segs[i + 1]
        # hard cut (1 frame): 0.25 s and 0.12 s dissolves both showed double exposures
        trans.append(("fade", 0.04))
    vids = [segment_video(sg, sg["clips"], work, i, trans[i][1] if i < len(trans) else 0.0)
            for i, sg in enumerate(segs)]
    # join with xfade at the exact spoken boundaries
    inputs, fc, prev, off = [], [], "[0:v]", 0.0
    for v in vids:
        inputs += ["-i", str(v)]
    # Trim every segment to exactly what its xfade consumes: leftover frames after a
    # transition deadlocked ffmpeg 7.1 for 40 min (renter, 2026-11-06).
    for i in range(len(vids)):
        keep = segs[i]["dur"] + (trans[i][1] if i < len(trans) else 0.0) + 0.04
        fc.append(f"[{i}:v]trim=duration={keep:.3f},setpts=PTS-STARTPTS,fps=30[t{i}]")
    prev = "[t0]"
    for i in range(1, len(vids)):
        kind, td = trans[i - 1]
        off += segs[i - 1]["dur"]
        lab = f"[x{i}]"
        fc.append(f"{prev}[t{i}]xfade=transition={kind}:duration={td}:offset={off:.3f}{lab}")
        prev = lab
    joined = work / "joined.mp4"
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", *inputs, "-filter_complex", ";".join(fc),
                    "-map", prev, "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", str(joined)],
                   check=True, timeout=600)
    # overlays: item cards (slide up 40 px, 180 ms), CTA card, karaoke captions
    ass = captions(segs, work / "caps.ass")
    ov_in, ov_fc, last, k = [], [], "[0:v]", 1
    for sg in segs:
        if sg["kind"] == "item":
            png = item_card(sg["item"], sg["n"], work / f"card{sg['n']}.png")
        elif sg["kind"] == "cta":
            png = cta_card(s["keyword"], work / "cta.png")
        else:
            continue
        t0, t1 = sg["start"], sg["start"] + sg["dur"]
        ov_in += ["-loop", "1", "-t", f"{t1 + 0.5:.2f}", "-i", str(png)]
        t0 += 0.1                        # after the cut has landed
        fo = max(t0 + 0.3, t1 - 0.15)    # gone before the next transition starts
        ov_fc.append(f"[{k}:v]format=rgba,fade=in:st={t0:.2f}:d=0.15:alpha=1,"
                     f"fade=out:st={fo:.2f}:d=0.15:alpha=1[o{k}]")
        ov_fc.append(f"{last}[o{k}]overlay=0:0:enable='between(t,{t0:.2f},{t1:.2f})'[v{k}]")
        last, k = f"[v{k}]", k + 1
    ov_fc.append(f"{last}ass={ass}[vout]")
    # audio: Ava over a ducked music bed
    music = rp.pick_music_bed({"hook": s["hook"]}) or next(iter((ROOT / "social" / "music").glob("*.mp3")))
    total = segs[-1]["start"] + segs[-1]["dur"]
    a_in = ["-i", str(vo), "-stream_loop", "-1", "-i", str(music)]
    ai, mi = k, k + 1
    ov_fc.append(f"[{ai}:a]asplit=2[vo1][vo2]")
    ov_fc.append(f"[{mi}:a]volume=0.25,atrim=0:{total:.2f}[mb]")
    ov_fc.append("[mb][vo1]sidechaincompress=threshold=0.02:ratio=5:attack=15:release=220[md]")
    ov_fc.append("[vo2][md]amix=inputs=2:duration=first:normalize=0,alimiter=limit=0.95[aout]")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(joined), *ov_in, *a_in,
                    "-filter_complex", ";".join(ov_fc), "-map", "[vout]", "-map", "[aout]",
                    "-t", f"{total:.2f}", "-c:v", "libx264", "-preset", "medium", "-crf", "20",
                    "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "160k", "-movflags", "+faststart",
                    str(out_path)], check=True)
    vol = rp.mean_volume_db(out_path)
    if vol is not None and vol < -30:
        raise RuntimeError(f"audio too quiet ({vol:.1f} dB)")
    print(f"  ✓ {out_path} {total:.1f}s, {vol} dB mean")
    return out_path


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--format", default="fixes3", choices=list(FORMATS))
    ap.add_argument("--out", default=str(ROOT / "social" / "reels" / "v2_test"))
    ap.add_argument("--from-script", help="re-render an earlier test's script JSON (same products)")
    ap.add_argument("--drop", nargs="*", default=[], help="ASINs to leave out of --from-script")
    args = ap.parse_args()
    s = None
    if args.from_script:
        s = json.loads(Path(args.from_script).read_text())
        s["items"] = [i for i in s["items"] if i["asin"] not in set(args.drop)]
        args.format = s["format"]
        if not s.get("clip_ids"):
            rewrite_benefits(s["items"])
    for attempt in range(4):
        if s:
            break
        s = write_script(args.format, strict=attempt < 3)
    if not s:
        print("[v2] could not write a script")
        return 1
    print(json.dumps({k: s[k] for k in ("format", "hook", "promise", "keyword")}),
          [(i["type"], i["band"], i["benefit"]) for i in s["items"]])
    stamp = datetime.now().strftime("%Y%m%d-%H%M")
    out = Path(args.out) / f"v2-{args.format}-{stamp}.mp4"
    work = Path("/tmp") / f"reelv2-{args.format}-{stamp}"
    build(s, out, work)
    s["page"] = publish_links(s, out.name)
    (out.with_suffix(".json")).write_text(json.dumps(s, indent=1))
    try:
        led = json.loads(HOOK_LEDGER.read_text()) if HOOK_LEDGER.exists() else []
        led.append({"date": datetime.now().strftime("%Y-%m-%d"), "hook": s["hook"], "test": True})
        HOOK_LEDGER.write_text(json.dumps(led[-200:], indent=1))
    except (OSError, ValueError):
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
