#!/usr/bin/env python3
"""Hold back queued pins whose photo card is the blank placeholder (kept, not deleted)."""
import json, sys
from pathlib import Path
from PIL import Image, ImageStat
R = Path("/home/ianmcwherter/golden-home-project")
sys.path.insert(0, str(R / "automation"))
from brand import PLACEHOLDER
def blank(png: Path) -> bool:
    im = Image.open(png).convert("RGB")
    w, h = im.size
    box = im.crop((int(w*.25), int(h*.55), int(w*.75), int(h*.75)))   # middle of the photo card
    st = ImageStat.Stat(box)
    mean = [round(x) for x in st.mean]; spread = max(st.stddev)
    return spread < 6 and all(abs(m - p) < 12 for m, p in zip(mean, PLACEHOLDER))
q = json.loads((R / "social/pinterest_queue.json").read_text())
n = 0
for p in q:
    if p.get("posted") or p.get("blocked"): continue
    img = p.get("fallback_image_path") if p.get("media") == "video" else p.get("image_path")
    if p.get("media") == "video" or not img or not (R / img).exists() or not img.endswith(".png"): continue
    if blank(R / img):
        p["blocked"] = True; p["blocked_reason"] = "blank photo card (no matching photo found) — 2026-10-03"
        n += 1; print("held:", p["id"], "|", p["title"][:60])
(R / "social/pinterest_queue.json").write_text(json.dumps(q, indent=2))
print("held back", n)
