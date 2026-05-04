# Affiliate Reroute Roadmap — 2026-05-03

**Why this exists:** Amazon Associates `goldenhomep06-20` data Mar 31 → Apr 29 2026: **521 clicks / 0 orders / $0.00 / 0% conversion**. Same pattern as the dead-link incident (project memory). Search-URL fix prevented "page not found" but did not produce revenue — search→cart conversion is structurally ~10x lower than PDP→cart. Channel is broken at this traffic quality.

**Solution:** reroute every keyword whose merchant has a direct/Impact/CJ program paying ≥5%. Done today: PILLOW (Eli & Elm Impact 20%), COVER (Mamma Mia Impact 20-30%).

## CEO action — sign up for these programs (you must do, per Claude safety policy)

Use Chrome with Golden Home Project credentials. Each takes ~5 min. After signup, paste the link below — Claude will swap it into the Meta DM automation.

| Priority | Keyword | Merchant | Sign-up URL | Expected payout | Amazon baseline |
|---|---|---|---|---|---|
| 1 | STRIP | Govee | https://us.govee.com/pages/affiliate | 5-15% direct | 3% / 0% conv |
| 2 | VACUUM | FoodSaver | https://www.foodsaver.com/affiliates.html | up to 10% via CJ | 3% / 0% conv |
| 3 | PASTE | Stardrops Pink Stuff | https://usa.thepinkstuff.com/pages/affiliate | TBD (apply to find out) | 3% / 0% conv |
| 4 | KETTLE | Cosori | https://cosori.com/pages/affiliates (or Impact/CJ) | 5% direct | 3% / 0% conv |

## After signup (CEO → Claude handoff)

1. Drop a message: `STRIP affiliate URL = <link>` (etc.)
2. Claude will:
   - Edit the matching Meta DM auto-reply (reuse PILLOW/COVER pattern)
   - Update `dm_keyword_registry.json` with `affiliate_network` + `affiliate_url`
   - Verify save success via URL transition
3. Total: ~5 min per keyword once link is in hand

## No-direct-merchant keywords (stay on Amazon for now)

- LINK (Simple Houseware) — generic
- NIGHTLIGHT (LED generic) — generic
- SPONGE (Scrub Daddy) — retail brand, weak direct affiliate presence
- ROLLER (ChomChom) — small brand, no public program found

These stay Amazon until either (a) merchant launches a program, or (b) we test conversion via Impact/CJ marketplace search for adjacent products.
