# GHP Business Plan — 2026-06-11 (post full-channel audit)

## 0. The one number that matters
**3 qualifying Amazon sales by ~Sept 16, 2026** or Associates closes the account
(opened Mar 20; 180-day rule). Lifetime revenue: $0. June so far: 14 clicks, 0 orders.
Everything below is ordered by probability of producing those 3 sales.

## 1. Revenue thesis (why this can work now when it has not yet)
Audit findings 6/11: every channel was running, but each had a silent revenue-fatal
defect — Pinterest re-posted 4 duplicate template pins ~26x into 0 impressions; the two
June blog posts had ZERO affiliate links; reels were letterboxed with no captions; the
YT poster died Apr 5. **The machine was never actually tested.** All four defects are
now fixed; the next 4 weeks are the first honest test of the funnel:

content (pins/posts/reels) → blog post w/ verified product CTA → Amazon
(tag goldenhomep06-20, ascsubtag per channel) → commission.

## 2. Channel playbook (probability-ranked)
**P1. Pinterest (fixed today) — the compounding free-traffic engine.**
- 2 photo pins/day (out-of-repo ledger prevents duplicates forever), every product
  ASIN-verified, pins link to a blog post when one exists, else /dp/ with
  ascsubtag=pinterest.
- Claim goldenhomeproject.com (mobile app; web claim page broken for this account) —
  every winning competitor (7/7, see social/competitive_intel.jsonl) has a claimed domain.
- Checkpoint 6/18: clean photo pins must show >0 impressions; if still 0 the account
  is burned → new account, claimed domain from day 1, same queue.

**P2. YouTube real-footage Shorts — the only content with proven organic reach.**
- Ian's existing videos: 4,147-view decor Short, 2,635-view pond video (100% likes)
  vs 5–81 views for AI content. 30–50x organic advantage, zero new filming needed.
- Plan: cut existing lake-house/decor footage into 20–40s Shorts (room reveals,
  before/after, "3 things that make this room work"), each with 1–3 verified product
  links + disclosure in the description. Target 3 Shorts/week.
- First step: autopsy the dead YT poster (no upload since Apr 5), fix or replace it.

**P3. Blog SEO — the conversion hub (fixed today).**
- Weekly post; topic MUST map to a verified registry ASIN (pick_topic enforces);
  every post ships with working CTAs. The existing 60+ pages keep compounding.
- Each new post gets a matching Pinterest pin (pin → blog → Amazon is the highest-
  converting path and builds first-party property).

**P4. IG/FB — keep on autopilot, zero new investment.**
- Daily reel/carousel + comment→DM funnel already healthy. IG organic is proven dead
  for faceless AI here (15-day zero-engagement streak in April); it stays as free
  distribution, not a growth bet.

## 3. Content quality bar (every piece, no exceptions)
1. Product is ASIN-verified live (logged-in browser; now enforced in code for pins + blog).
2. Links: /dp/ASIN?tag=goldenhomep06-20&ascsubtag=<channel>. Never search URLs.
3. FTC disclosure on every monetized surface.
4. Reels: full-frame 9:16, burned-in captions, AvaNeural en-US voice. Next iteration:
   product photo overlay while each product is named; 18–30s scripts. (Composite fixed
   + smoke-tested 6/11.)
5. Photo pins only (real Pexels photo + price chip + footer); template/gradient = trash.
6. Steal-and-improve: one mechanic per session from a measured winner, logged in
   competitive_intel.jsonl with an eval date.

## 4. Trending-product discovery loop (weekly, ~30 min CEO session)
1. Pull demand signals (all free): Pinterest Trends + Amazon Movers & Shakers in
   Home/Kitchen/Storage + the asin-discoverer Reddit/trend feed.
2. Pick 3–5 products that are (a) visual, (b) $25–$200 (meaningful commission),
   (c) home-org/decor native, (d) 4.3★+ with 1k+ ratings.
3. Verify each ASIN live in the browser → registry vetted with verified_at/price/stars.
4. Producers consume the registry automatically (pins next morning; blog Sunday;
   reels nightly).
Registry today: 21 products; all queued ones verified; organization products prioritized.

## 5. Followers & engagement (within hands-off/faceless constraints)
- Followers follow consistency + utility: 2 pins/day, daily reel, weekly post,
  3 Shorts/week.
- Pinterest: keyword-rich profile/About/board descriptions (done 6/11); boards are the
  follow unit — seed each new board with 5+ pins before promoting it.
- Engagement automation stays OFF on Pinterest (fresh account, just cleaned) and
  minimal on IG (existing comment→DM responder only). No follow/unfollow games —
  that is how faceless accounts die.
- YT: pin a comment with product links on every Short; reply to every comment (rare
  enough to handle manually in CEO sessions).

## 6. Operating cadence
- Automated daily: Pinterest generate 06:10 + post 09:40/19:25, IG carousel, presenter
  reel 23:00, engagement sweep, watchdog.
- CEO session (2–3x/week): check analytics dashboards FIRST (Pinterest, Associates,
  GSC), run the product discovery loop, one steal-and-improve, one quality iteration,
  update RESUME_PROMPT. **Rule learned 6/11: never trust "the cron ran" — check the
  OUTPUT (live pins, live CTAs, live uploads) at every session.**

## 7. Checkpoints & kill criteria
- **6/18**: Pinterest impressions > 0 or start the new-account plan. YT poster autopsy done.
- **7/09** (4 weeks of honest funnel): need a ≥200 Pinterest impressions/week trend,
  ≥3 real-footage Shorts live, clicks/30d recovering toward 60+. If clicks < 30:
  the funnel thesis is wrong → pivot the content niche (decor-reveal angle from the
  4,147-view Short) before adding ANY new channel.
- **8/15**: if 0 sales despite a healthy traffic trend, swap P1/P2 priorities and
  double the Shorts cadence (real footage is the proven asset).
- **9/16**: Associates deadline. 0 sales = account closes = the affiliate thesis is
  dead in its current form → full stop and rethink monetization, not more content.

## 8. What we will NOT do
- No paid anything (ads, SEO tools, SaaS) until the first dollar. No new platforms.
- No new pipelines/rebuilds — only fixes to provably broken output.
- No unverified ASINs, no search-URL links, no engagement-bot games, no buying followers.
