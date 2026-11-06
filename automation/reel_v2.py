#!/usr/bin/env python3
"""reel_v2.py — GHP Reels v2, built to marketing's REEL_SPEC_v2.md (2026-11-06).

Ian, 2026-11-06: "the color schemes and mustard letters are not good, we need catchy and
trending videos that go viral and sell product". v2 looks native, not branded:
  * word-by-word karaoke captions (edge-tts word boundaries), white Montserrat ExtraBold with
    a black stroke, the current word in Coral; no boxes, no gold
  * hook in the first 1.2 s, a promise, 3 items (~5 s each), CTA + loop, 15-22 s total
  * a cut every 0.8-1.8 s, 106->100% punch-in per cut, a whip between items
  * one grade across all stock, music ducked under Ava (+10% rate)
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

HOOK_BANK = ["If your sink cabinet looks like this…", "Stop stacking your pans like this.",
             "Renters, you need these.", "POV: your closet finally works.",
             "This is why your counters never stay clean.", "Small apartment? Steal these.",
             "Things that just make sense for a tiny kitchen.", "Your entryway is doing too much."]

FORMATS = {
    "fixes3": dict(n=3, promise="{n} fixes under {band}", ask="3 complementary items that fix "
                   "one messy space together"),
    "before_after": dict(n=3, promise="Before and after, under {band}", ask="3 items that take "
                         "ONE space from messy to organized"),
    "makes_sense": dict(n=4, promise="Things that just make sense", ask="4 clever, "
                        "everyday-useful items for one room"),
    "renter": dict(n=3, promise="Renters, save this", ask="3 renter-friendly items (no drilling, "
                   "adhesive, over-the-door, tension or freestanding)"),
    "gift": dict(n=3, promise="Gifts under {band} they'll actually use", ask="3 giftable items"),
    "stop_doing": dict(n=3, promise="Stop doing this", ask="3 items that each replace a common "
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
        items = [i for i in items if re.search(r"no drill|adhesive|over the door|tension|"
                                               r"freestanding|stick|removable|renter", i["name"], re.I)]
        return items[:12]
    by = {}
    for i in items:
        if i.get("category") != "Movers":
            by.setdefault(i["category"], []).append(i)
    cats = [c for c, xs in by.items() if len(xs) >= 5]
    return by[random.choice(cats)][:12] if cats else items[:12]


def write_script(fmt: str) -> dict | None:
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
        f"Format: {fmt}. Pick {spec['ask']} (exactly {spec['n']}). Reply ONLY JSON:\n"
        '{"hook": "<scene-first, second person, under 12 words, NO digits; you may adapt one of: '
        + " | ".join(bank) + '>", "space": "<the room or spot, 1-3 words>", '
        '"items": [{"i": <index>, "type": "<generic item, 2-4 words, Title Case>", '
        '"benefit": "<one benefit from THAT title only, 3-7 words, no digits unless in the title>", '
        '"problem_query": "<2-4 word stock-video search for the messy/problem moment, no people>", '
        '"solution_query": "<2-4 word stock-video search for the organized/solved result>"}]}\n'
        "Rules: every item must directly fix the exact problem the hook shows in that space, "
        "and no two items may be the same kind of product (no two towels, no two bins). "
        "No first person, no claims beyond the titles, no prices or '$'.")
    if not got or len(got.get("items") or []) != spec["n"]:
        return None
    items = []
    for x in got["items"]:
        try:
            c = cand[int(x["i"])]
        except (KeyError, ValueError, IndexError):
            return None
        allowed = set(re.findall(r"\d+", c["name"]))
        txt = f"{x.get('type', '')} {x.get('benefit', '')}"
        if "$" in txt or fabrication_match(txt) or any(n not in allowed for n in re.findall(r"\d+", txt)):
            print(f"  [v2] rejected item text: {txt}")
            return None
        items.append({**x, "asin": c["asin"], "name": c["name"],
                      "band": price_band(str(c.get("price") or ""))})
    hook = got.get("hook", "").strip()
    if re.search(r"\d", hook) or len(hook.split()) > 12 or fabrication_match(hook):
        print(f"  [v2] rejected hook: {hook}")
        return None
    prices = [float(re.sub(r"[^\d.]", "", str(c.get("price") or "0")) or 0) for c in
              (cand[int(x["i"])] for x in got["items"])]
    band = price_band(f"${max(prices):.2f}") if prices else ""
    amt = (re.search(r"\$\d+", band) or [""])[0] if band else ""
    promise = spec["promise"].format(n=spec["n"], band=amt).replace("under  ", "").strip()
    kw = _keyword_for(items[0]["asin"])
    return {"format": fmt, "hook": hook, "promise": promise, "space": got.get("space", ""),
            "items": items, "keyword": kw}


def _keyword_for(asin: str) -> str:
    """The comment-reply funnel answers registry keywords; reuse the first item's."""
    try:
        reg = json.loads((ROOT / "social" / "dm_keyword_registry.json").read_text())
        for e in reg.get("entries", []):
            if e.get("asin") == asin and e.get("keyword"):
                return e["keyword"].upper()
    except (OSError, ValueError):
        pass
    return "LINKS"


def segments(s: dict) -> list[dict]:
    segs = [{"kind": "hook", "say": s["hook"]},
            {"kind": "promise", "say": s["promise"]}]
    for n, it in enumerate(s["items"], 1):
        band = it["band"].lower()
        segs.append({"kind": "item", "n": n, "item": it,
                     "say": f"{it['type']}, {band}. {it['benefit']}."})
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
def find_clip(queries, visual: str, work: Path, need: float = 2.6) -> Path | None:
    """Specific search first, then broader ones (stock libraries rarely have the exact
    micro-moment: "stained bare mattress" found nothing usable on 2026-11-06)."""
    if isinstance(queries, str):
        queries = [queries]
    judged_total = 0
    for q in dict.fromkeys(q for q in queries if q):
        judged = 0
        for v in vp._search(q):
            if judged >= 3 or judged_total >= 10:
                break
            vid = v.get("id")
            if (vid in vp._used() or vid in rp._SEEN_THIS_REEL or float(v.get("duration") or 0) < need
                    or vp._slug_words(v) & set(vp.UNSAFE) or not vp._best_file(v)):
                continue
            rp._SEEN_THIS_REEL.add(vid)
            lo, sheet = work / f"v{vid}-lo.mp4", work / f"v{vid}-sheet.jpg"
            small = vp._small_file(v)
            if not small or not vp._get(small, lo) or not vp._contact_sheet(lo, need, sheet):
                continue
            judged += 1
            judged_total += 1
            d = rp._judge_scene(vp, sheet, visual)
            ok = d.get("fits") and d.get("face_visible") is False and int(d.get("score") or 0) >= 7
            print(f"    clip {vid} ({q!r}): {'OK' if ok else 'reject'} — {str(d.get('note'))[:50]}")
            if not ok:
                continue
            hd = work / f"v{vid}.mp4"
            if vp._get(vp._best_file(v), hd):
                vp._mark_used(vid)
                return hd
    return None


GRADE = ("eq=contrast=1.08:saturation=1.06:brightness=0.0,"
         "colorbalance=rs=0.03:gs=0.01:bs=-0.03:rm=0.02:bm=-0.02")


def shot(src: Path, start: float, dur: float, out: Path) -> Path:
    """One cut: crop to 9:16, 106->100% punch-in over 0.4 s, the shared grade."""
    frames = 12
    vf = (f"scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},fps=30,"
          f"zoompan=z='if(lt(on,{frames}),1.06-0.06*on/{frames},1)':d=1:"
          f"x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s={W}x{H}:fps=30,{GRADE},format=yuv420p")
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-ss", f"{start:.2f}", "-t", f"{dur:.2f}",
                    "-i", str(src), "-vf", vf, "-an", "-r", "30", "-c:v", "libx264", "-preset",
                    "veryfast", "-crf", "20", str(out)], check=True)
    return out


def segment_video(sg: dict, clips: list[Path], work: Path, idx: int, tail: float) -> Path:
    """Cut the segment into 0.8-1.8 s shots across its clips; pad `tail` for the transition."""
    # +0.2 s spare: shots round down to whole frames, and an xfade whose first input is even
    # one frame short of offset+duration silently drops the rest (fixes3 froze its CTA 11/06)
    total = sg["dur"] + tail + 0.2
    n = max(len(clips), math.ceil(total / 1.6))
    each = total / n
    shots = []
    for k in range(n):
        c = clips[k % len(clips)]
        cd = _dur(c)
        st = min(max(0.2, (k // len(clips)) * each * 1.1 + 0.3), max(0.0, cd - each - 0.1))
        shots.append(shot(c, st, each, work / f"s{idx}_{k}.mp4"))
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
    s = "or shop at goldenhomeproject.com"
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
Style: Hook,Montserrat ExtraBold,104,&H00FFFFFF,&H00FFFFFF,&H00000000,&H64000000,0,0,0,0,100,100,0,0,1,8,3,8,80,{SAFE_RIGHT + 60},{SAFE_TOP + 120},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    ev = []
    for sg in segs:
        if sg["kind"] == "cta":
            continue
        style = "Hook" if sg["kind"] in ("hook", "promise") else "Cap"
        ws = sg["words"]
        lines, cur = [], []
        for k, w in enumerate(ws):
            # a spoken pause (comma / full stop) starts a new line, so "under $10" and the
            # benefit never share one caption
            if cur and w[0] - (ws[k - 1][0] + ws[k - 1][1]) > 0.18:
                lines.append(cur)
                cur = []
            cur.append(w)
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
                        parts.append("{\\c&H4E5AFF&\\fscx85\\fscy85\\t(0,80,\\fscx100\\fscy100)}"
                                     + w2 + "{\\r}")
                    else:
                        parts.append(w2)
                ev.append(f"Dialogue: 0,{_ass_time(t0)},{_ass_time(max(t1, t0 + 0.08))},{style},,0,0,0,,"
                          + " ".join(parts))
    out.write_text(hdr + "\n".join(ev) + "\n")
    return out


# ------------------------------------------------------------------ assemble
def build(s: dict, out_path: Path, work: Path) -> Path:
    work.mkdir(parents=True, exist_ok=True)
    rp._SEEN_THIS_REEL.clear()
    segs = segments(s)
    vo = voice(segs, work)
    # footage
    space = s.get("space") or "home"
    pq = s["items"][0]["problem_query"]
    hook_clip = (find_clip([pq], f"{pq} in a {space} (the problem the hook names)", work)
                 or find_clip([f"messy {space}", f"cluttered {space}", f"{space} interior"],
                              f"a {space}, ideally lived-in or a bit messy", work)
                 # fixes3 "shower" 2026-11-06: nothing judged usable; any real room of that kind
                 or find_clip([i["problem_query"] for i in s["items"][1:]]
                              + [f"{space}", "home interior", "apartment interior"],
                              f"any real {space} or home interior, no people in focus", work))
    if not hook_clip:
        raise RuntimeError("no usable opening clip")
    for sg in segs:
        if sg["kind"] == "hook":
            sg["clips"] = [hook_clip]
        elif sg["kind"] == "promise":
            c = find_clip([f"organized {space}", f"clean {space}", f"{space} interior"],
                          f"a tidy, organized {space}", work)
            sg["clips"] = [c] if c else [hook_clip]
        elif sg["kind"] == "item":
            it = sg["item"]
            a = find_clip([it["problem_query"], f"messy {space}"],
                          f"the everyday problem a {it['type'].lower()} solves, in a {space}", work)
            b = find_clip([it["solution_query"], it["type"].lower(), f"organized {space}"],
                          f"a {it['type'].lower()} or the tidy result it gives, in a {space}", work)
            sg["clips"] = [c for c in (a, b) if c] or [hook_clip]
        else:
            sg["clips"] = [hook_clip]          # CTA on the hook clip: the reel loops
    real = sum(1 for sg in segs for c in sg["clips"] if c is not hook_clip) + 1
    print(f"    footage: {real} real clips")
    # per-segment video with transition tails
    trans = []
    for i, sg in enumerate(segs[:-1]):
        nxt = segs[i + 1]
        trans.append(("slideleft", 0.2) if sg["kind"] == "item" and nxt["kind"] == "item" else ("fade", 0.05))
    vids = [segment_video(sg, sg["clips"], work, i, trans[i][1] if i < len(trans) else 0.0)
            for i, sg in enumerate(segs)]
    # join with xfade at the exact spoken boundaries
    inputs, fc, prev, off = [], [], "[0:v]", 0.0
    for v in vids:
        inputs += ["-i", str(v)]
    for i in range(1, len(vids)):
        kind, td = trans[i - 1]
        off += segs[i - 1]["dur"]
        lab = f"[x{i}]"
        fc.append(f"{prev}[{i}:v]xfade=transition={kind}:duration={td}:offset={off:.3f}{lab}")
        prev = lab
    joined = work / "joined.mp4"
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", *inputs, "-filter_complex", ";".join(fc),
                    "-map", prev, "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", str(joined)],
                   check=True)
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
        ov_fc.append(f"[{k}:v]format=rgba,fade=in:st={t0:.2f}:d=0.18:alpha=1[o{k}]")
        ov_fc.append(f"{last}[o{k}]overlay=0:'40*max(0,1-(t-{t0:.2f})/0.18)':"
                     f"enable='between(t,{t0:.2f},{t1:.2f})'[v{k}]")
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
    args = ap.parse_args()
    s = None
    for _ in range(3):
        s = write_script(args.format)
        if s:
            break
    if not s:
        print("[v2] could not write a script")
        return 1
    print(json.dumps({k: s[k] for k in ("format", "hook", "promise", "keyword")}),
          [(i["type"], i["band"], i["benefit"]) for i in s["items"]])
    stamp = datetime.now().strftime("%Y%m%d-%H%M")
    out = Path(args.out) / f"v2-{args.format}-{stamp}.mp4"
    work = Path("/tmp") / f"reelv2-{args.format}-{stamp}"
    build(s, out, work)
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
