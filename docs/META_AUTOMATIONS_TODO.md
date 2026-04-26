# Meta Business Suite — DM Automations to Add

8 comment-to-DM automations need to be created in Meta Business Suite. Each one unlocks one product category for the content engine — without these, the engine has only 2 keyword choices (LINK, PILLOW) and most reels can't ship.

**Where:** https://business.facebook.com/latest/inbox/automated_responses?asset_id=973754055831729&business_id=1580899273211540

**Per automation, the flow is:**
1. Click `Create automation`
2. Choose template `Comment to message`
3. Pick post: **Apply to all current and future posts** (or "Specific posts" if you want narrower)
4. Channels: **Instagram + Messenger** (both)
5. Trigger keyword: see `KEYWORD` below
6. Comment reply (recommended): leave default `Sent you a message!`
7. DM message: paste the `DM TEXT` block below
8. Save

After each one is live, run:
```bash
python3 - <<'PY'
import json, pathlib
p = pathlib.Path('social/dm_keyword_registry.json')
r = json.loads(p.read_text())
for e in r['entries']:
    if e['keyword'] in {'COVER','KETTLE','NIGHTLIGHT','SPONGE','STRIP','VACUUM','PASTE','ROLLER'}:
        # flip whichever ones you actually shipped
        if e['keyword'] == 'COVER': e['status'] = 'live'  # repeat per keyword
p.write_text(json.dumps(r, indent=2))
PY
```

Or just edit `social/dm_keyword_registry.json` and change `status: "pending_meta_automation"` → `status: "live"` for whichever keywords you shipped.

---

## 1. COVER → Paulato Stretch Sofa Cover

**KEYWORD:** `COVER`

**DM TEXT:**
```
Here's the link 👇

Paulato by GA.I.CO. waterproof stretch sofa cover (the one I used):
https://www.amazon.com/dp/B0B4SPP3ZN?tag=goldenhomep06-20

Amazon affiliate link — I earn a small commission at no extra cost to you. Hope it works as well for your couch as it did for mine!
```

---

## 2. KETTLE → Cosori Electric Kettle

**KEYWORD:** `KETTLE`

**DM TEXT:**
```
Here's the link 👇

Cosori electric kettle (no-plastic contact, the one I use):
https://www.amazon.com/dp/B08PP48979?tag=goldenhomep06-20

Amazon affiliate link — I earn a small commission at no extra cost to you. Wide-mouth design makes it easy to clean!
```

---

## 3. NIGHTLIGHT → LED Motion Sensor Plug-In Night Light

**KEYWORD:** `NIGHTLIGHT`

**DM TEXT:**
```
Here's the link 👇

LED motion-sensor plug-in night light (the one in the video):
https://www.amazon.com/dp/B08RRRX5P5?tag=goldenhomep06-20

Amazon affiliate link — I earn a small commission at no extra cost to you. The motion sensor is way more sensitive than I expected.
```

---

## 4. SPONGE → Scrub Daddy

**KEYWORD:** `SPONGE`

**DM TEXT:**
```
Here's the link 👇

Scrub Daddy sponge (dye-free, scratch-free):
https://www.amazon.com/dp/B07ZL2BFMP?tag=goldenhomep06-20

Amazon affiliate link — I earn a small commission at no extra cost to you. The temperature-controlled texture is the part nobody talks about.
```

---

## 5. STRIP → Govee LED Strip Lights

**KEYWORD:** `STRIP`

**DM TEXT:**
```
Here's the link 👇

Govee RGBIC LED strip lights (32.8ft, the smart-home ones):
https://www.amazon.com/dp/B099S9DXT7?tag=goldenhomep06-20

Amazon affiliate link — I earn a small commission at no extra cost to you. The RGBIC = each segment can be a different color, not the older single-color version.
```

---

## 6. VACUUM → FoodSaver Vacuum Sealing System

**KEYWORD:** `VACUUM`

**DM TEXT:**
```
Here's the link 👇

FoodSaver VS2150 vacuum sealing system (the one I use):
https://www.amazon.com/dp/B099NTSWD9?tag=goldenhomep06-20

Amazon affiliate link — I earn a small commission at no extra cost to you. Worth it just for cutting down freezer-burn waste.
```

---

## 7. PASTE → The Pink Stuff Cleaning Paste

**KEYWORD:** `PASTE`

**DM TEXT:**
```
Here's the link 👇

Stardrops "The Pink Stuff" cleaning paste:
https://www.amazon.com/dp/B00DU5SRIY?tag=goldenhomep06-20

Amazon affiliate link — I earn a small commission at no extra cost to you. This is the multi-purpose one — works on stovetops, tubs, sinks, grout.
```

---

## 8. ROLLER → ChomChom Pet Hair Roller

**KEYWORD:** `ROLLER`

**DM TEXT:**
```
Here's the link 👇

ChomChom roller pet hair remover (reusable, no sticky sheets):
https://www.amazon.com/dp/B00BAGTNAQ?tag=goldenhomep06-20

Amazon affiliate link — I earn a small commission at no extra cost to you. The "no refills" thing is what sold me — the original sticky rollers were costing me more than this thing did.
```

---

## Why this matters

Right now only 2 of every 3 reels has a working DM funnel (the LINK and PILLOW pair). The other reels say "Comment X and I'll DM you the link" with X being a keyword that has no automation behind it — 0% conversion path.

After all 8 are live, every reel the content engine produces will route to a working DM with a verified-alive ASIN. This is the single biggest conversion lever GHP has on Instagram.

All 8 ASINs were Chrome-verified alive on amazon.com on 2026-04-25.
