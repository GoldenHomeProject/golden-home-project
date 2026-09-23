"""Generate the design-system previews FROM brand.py, so spec and code cannot disagree."""
import sys
from pathlib import Path
sys.path.insert(0, "/home/ianmcwherter/golden-home-project/automation")
import brand as B

OUT = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("ds")
(OUT / "components").mkdir(parents=True, exist_ok=True)

SHELL = """<!-- @dsCard group="{group}" -->
<style>
 body{{margin:0;font-family:Inter,system-ui,sans-serif;background:#fff;color:#121212}}
 .wrap{{padding:28px}} h2{{font-size:15px;letter-spacing:.08em;text-transform:uppercase;
 color:#5A5854;margin:0 0 18px}} .row{{display:flex;flex-wrap:wrap;gap:14px}}
 .sw{{width:150px}} .chip{{height:78px;border-radius:10px;border:1px solid #E6E3DE}}
 .nm{{font-size:13px;margin-top:7px;font-weight:600}} .hx{{font-size:12px;color:#77736E;font-family:ui-monospace,monospace}}
 .rl{{font-size:11px;color:#8A8680;margin-top:2px}}
 table{{border-collapse:collapse;width:100%}} td{{padding:9px 10px;border-bottom:1px solid #EFEDE9;vertical-align:baseline}}
 .k{{font-size:12px;color:#77736E;width:110px}} .v{{font-family:ui-monospace,monospace;font-size:12px;color:#77736E;width:60px}}
 @media (prefers-color-scheme:dark){{body{{background:#141414;color:#F2F0EC}}
  h2,.rl,.hx,.k,.v{{color:#A8A49E}} .chip{{border-color:#2C2A27}} td{{border-bottom-color:#232220}}}}
</style>
<div class="wrap">{body}</div>"""

# ---- colour roles ----------------------------------------------------------
roles = [("GOLD", B.GOLD, "rules, kicker square, footer domain, number badges"),
         ("CREAM", B.CREAM, "the text band — a calm zone type can sit on"),
         ("INK", B.INK, "headline"),
         ("MUTED", B.MUTED, "kicker + supporting caption"),
         ("GREY", B.GREY, "secondary — 'Updated September 2026'"),
         ("WHITE", B.WHITE, "footer, price chips"),
         ("PLACEHOLDER", B.PLACEHOLDER, "stands in for a missing photo")]
sw = "".join(
    f'<div class="sw"><div class="chip" style="background:{B.hex_of(c)}"></div>'
    f'<div class="nm">{n}</div><div class="hx">{B.hex_of(c)}</div>'
    f'<div class="rl">{d}</div></div>' for n, c, d in roles)
(OUT / "components" / "colors.html").write_text(
    SHELL.format(group="Brand", body=f'<h2>Colour roles</h2><div class="row">{sw}</div>'))

# ---- type scale ------------------------------------------------------------
rows = "".join(
    f'<tr><td class="k">{k}</td><td class="v">{v}px</td>'
    f'<td style="font-size:{min(v,44)}px;font-weight:{700 if k in ("headline","price","footer","badge") else 400}">'
    f'The quick brown fox</td></tr>' for k, v in B.TYPE.items())
(OUT / "components" / "type.html").write_text(
    SHELL.format(group="Brand", body=f'<h2>Type scale</h2><table>{rows}</table>'))

# ---- layout tokens ---------------------------------------------------------
lay = (f'<tr><td class="k">canvas</td><td class="v">{B.PIN_W}&times;{B.PIN_H}</td>'
       f'<td>Pinterest 2:3 — the ratio it gives most height to</td></tr>'
       f'<tr><td class="k">margin</td><td class="v">{B.MARGIN}px</td><td>every surface</td></tr>')
lay += "".join(f'<tr><td class="k">band.{k}</td><td class="v">{v}</td>'
               f'<td>{int(v*B.PIN_H)}px of {B.PIN_H}</td></tr>' for k, v in B.BAND.items())
lay += "".join(f'<tr><td class="k">radius.{k}</td><td class="v">{v}px</td><td></td></tr>'
               for k, v in B.RADIUS.items())
(OUT / "components" / "layout.html").write_text(
    SHELL.format(group="Brand", body=f'<h2>Layout tokens</h2><table>{lay}</table>'))
print("wrote colors.html, type.html, layout.html")
