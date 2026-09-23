"""Embed REAL renders in the design system — a spec that shows mockups can lie."""
import base64, sys
from pathlib import Path
sys.path.insert(0, "/home/ianmcwherter/golden-home-project/automation")
from product_pin import build_product_pin
from collage_pin import build_collage_pin

OUT = Path(sys.argv[1]); (OUT / "components").mkdir(parents=True, exist_ok=True)
ROOT = Path("/home/ianmcwherter/golden-home-project")
bgs = sorted(ROOT.glob("social/pinterest/bg-2026-09-2*.jpg"))

p1 = build_product_pin("Blackout Curtains Under $15", "NICETOWN 2-Panel Thermal Grommet Set",
                       "$14.58", bgs[0] if bgs else None, Path("/tmp/ds_product.png"),
                       kicker="bedroom storage ideas", updated="Updated September 2026")
cells = [{"image": b, "price": p} for b, p in zip(bgs[:4], ["$29.99", "$18.89", "$12.99", "$7.99"])]
p2 = build_collage_pin("4 Storage Bin Picks Under $30", "Verified 4.5 stars and up",
                       cells, Path("/tmp/ds_collage.png"),
                       updated="Updated September 2026", kicker="home storage")

def card(title, note, png, group):
    b64 = base64.b64encode(Path(png).read_bytes()).decode()
    return f"""<!-- @dsCard group="{group}" -->
<style>
 body{{margin:0;font-family:Inter,system-ui,sans-serif;background:#fff;color:#121212}}
 .wrap{{padding:28px}} h2{{font-size:15px;letter-spacing:.08em;text-transform:uppercase;
 color:#5A5854;margin:0 0 6px}} p{{font-size:13px;color:#77736E;margin:0 0 18px;max-width:560px;line-height:1.5}}
 img{{width:330px;max-width:100%;border-radius:10px;border:1px solid #E6E3DE;display:block}}
 @media (prefers-color-scheme:dark){{body{{background:#141414;color:#F2F0EC}}
  h2,p{{color:#A8A49E}} img{{border-color:#2C2A27}}}}
</style>
<div class="wrap"><h2>{title}</h2><p>{note}</p>
<img src="data:image/png;base64,{b64}" alt="{title}"></div>"""

(OUT / "components" / "pin-product.html").write_text(card(
    "Single-product pin",
    "Type never sits on the photo — it owns a cream band. Kicker with gold square, "
    "left-aligned editorial headline, gold rule, photo as a rounded card, price chip. "
    "The band height is MEASURED from the text, clamped 20–40% of canvas, so a short "
    "headline yields a bigger picture. Rendered live from product_pin.py.",
    p1, "Components"))
(OUT / "components" / "pin-collage.html").write_text(card(
    "Collage pin",
    "Saved ~2x more often than single-product pins, so it ranks in band 0 with price "
    "drops. Same header band, gold numbered badges 01–04, white price chips, identical "
    "footer. Links to the hub, since the pin promises several products. "
    "Rendered live from collage_pin.py.",
    p2, "Components"))
print("wrote pin-product.html, pin-collage.html")
