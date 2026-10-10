"""Read per-pin stats (views / saves / outbound clicks) off our own Pinterest board pages."""
import json, re, sys, time
from pathlib import Path
sys.path.insert(0, "/home/ianmcwherter/golden-home-project/automation")
import post_pinterest as pp
from playwright.sync_api import sync_playwright
USER = "goldenhomeprojectllc"
out = []
with sync_playwright() as p:
    c = p.chromium.launch_persistent_context(str(pp.PROFILE_DIR), executable_path=pp.CHROMIUM_BIN,
                                             headless=False, viewport={"width": 1400, "height": 1200})
    pg = c.new_page()
    pg.goto(f"https://www.pinterest.com/{USER}/_saved/", wait_until="domcontentloaded"); time.sleep(8)
    boards = sorted({h for h in (a.get_attribute("href") for a in pg.locator(f"a[href^='/{USER}/']").all())
                     if h and h.count("/") == 3 and not h.endswith(("_saved/", "_created/", "_profile/"))})
    print("boards:", len(boards))
    for b in boards:
        pg.goto("https://www.pinterest.com" + b, wait_until="domcontentloaded"); time.sleep(6)
        for _ in range(6):
            pg.mouse.wheel(0, 2500); time.sleep(1.5)
        body = pg.locator("body").inner_text()
        L = [l.strip() for l in body.split("\n") if l.strip()]
        num = lambda s: re.fullmatch(r"[\d.,]+[kKmM]?", s) is not None
        # Under each pin Pinterest prints three numbers (views, saves, outbound clicks)
        # followed by the pin title.
        for i in range(len(L) - 3):
            if num(L[i]) and num(L[i + 1]) and num(L[i + 2]) and not num(L[i + 3]):
                out.append({"board": b, "title": L[i + 3][:70], "views": L[i],
                            "saves": L[i + 1], "clicks": L[i + 2]})
    c.close()
import datetime as _dt
hist = Path.home() / ".ghp-engagement" / "pin_stats_history.jsonl"
with open(hist, "a") as fh:
    fh.write(json.dumps({"date": _dt.date.today().isoformat(), "pins": out}) + "\n")
json.dump(out, open("/home/ianmcwherter/.ghp-engagement/pin_stats.json", "w"), indent=1)
def n(x):
    x = x.replace(",", ""); m = 1000 if x[-1:].lower() == "k" else 1
    return float(x.rstrip("kK")) * m
print("pins read:", len(out), "| total views:", int(sum(n(o["views"]) for o in out)),
      "saves:", int(sum(n(o["saves"]) for o in out)), "clicks:", int(sum(n(o["clicks"]) for o in out)))
for o in sorted(out, key=lambda o: (-n(o["clicks"]), -n(o["views"])))[:12]:
    print(f"  views {o['views']:>5} saves {o['saves']:>3} clicks {o['clicks']:>3} | {o['board'][len(USER)+2:-1][:22]:22} | {o['title']}")
