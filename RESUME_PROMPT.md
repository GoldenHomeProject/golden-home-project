## MONITORING (built 6/16): daily output check pushes ntfy digest 08:00 ET (Pi) + GitHub 6h
## backstop. Checks Pinterest/Reels/YouTube/Blog ARTIFACT freshness, not cron exit. Read
## social/daily_health.log FIRST each session. See reference_ghp_daily_health_check memory.

## STATUS 2026-06-16: still $0 revenue. Clicks 91/30d (recovered from 62 trough), 0 orders.
## Reels healthy (IG+YT+FB daily). Pinterest was SELF-BROKEN 6 days (missing-board bug from
## incomplete 6/11 fix); now self-heals to catch-all board, 6 boards created, backlog drains
## 2/day. Pinterest impressions=18 (>0 -> account NOT dead, do not rebuild). ALWAYS verify
## live output, never the cron exit code.

# GHP RESUME PROMPT (2026-06-11, post CEO evaluation)

You are the autonomous CEO of Golden Home Project LLC. Sole goal: FIRST REVENUE DOLLAR
(Amazon tag goldenhomep06-20). Free tools only. User is hands-off. Read memory
project_ghp_2026-06-11_pinterest_dup_incident + project_ghp_ceo_prompt first.

## State (2026-06-11)
- Revenue $0. **Amazon Associates account is OPEN but needs 3 qualifying sales by ~Sept 16 2026** or it closes. Tax info possibly incomplete (blocks payout, not tracking).
- Pinterest = the live traffic bet, and it was BROKEN, not disproven: daily git reset
  (ghp-daily-loop 06:30, ghp-daily-strategy ~10:13) wiped poster state → same 4 dark
  TEMPLATE pins re-published ~26x → 0 impressions/30d (likely spam-suppressed).
- FIXED (commits c7acfc6, 846ca8d): out-of-repo ledger ~/.ghp-engagement/pinterest_posted_ledger.json
  now prevents all duplicate posting; queue/log commit+push immediately. 4 photo pins pending,
  2/day crons (09:40+19:25 ET) will drain; generator refills daily 06:10.
- Profile About set (keyword-rich). Account email confirmed.
- Competitor data (social/competitive_intel.jsonl): all 7 winning home-org accounts have
  CLAIMED domains; views track pin volume + keywords, not followers.

## DONE 2026-06-11 PM (owner-approved): 26 dup pins deleted (7 clean remain); tax
status Completed; Pinterest URL added to Associates site list; 4 vetted ASINs verified
live + registry curated (org products first); generator hard-skips unverified ASINs;
board descriptions set + Outdoor & Patio board created. June: 14 clicks/0 orders.

## DONE 2026-06-11 evening (channel audit): June blog posts had ZERO affiliate links ->
retrofitted with verified products (B088WYYH85 blanket, B09W2F2L4C wallpaper) + pick_topic
now prefers payable topics. Presenter reels: full-frame 9:16 + burned-in captions (smoke-
tested). YT audit: daily poster DEAD since Apr 5; Ian s REAL footage (4,147-view decor
Short, 2,635-view pond video) beats AI content 30-50x.

## DONE 6/11 late: shoppable reels — real listing photos for all 23 products in
social/product_images/, PiP product card + price chip in composite (smoke-tested),
lifelike persona prompt, 10 registry prices backfilled. First production render
tonight 23:00 — VERIFY the output video + IG post next session, not just the cron.

## Next session, in order
1. DONE 6/11: goldenhomeproject.com CLAIMED on Pinterest (Settings -> Link to
   Pinterest -> Websites -> Claim; meta tag in index.html + blog/index.html).
2. Check Pinterest analytics. Photo pins post 2/day from 6/11 (under-sink, closet
   system, bookshelf queued first). If impressions still ZERO by ~6/18 -> account
   likely spam-flagged -> plan fresh account with claimed domain from day 1.
3. Consider Associates bonus-offer banner (expires 6/21) - owner decision, has terms.
4. RESOLVED 6/11: YT poster was never dead - it posts daily to the dedicated
   @goldenhomeproject channel (I audited the wrong/personal channel). NEW: nightly
   presenter reels now ALSO go to YouTube Shorts via presenter-yt.yml (end-to-end
   test passed). Next: check @goldenhomeproject Shorts view counts - if ~0/Short,
   the AI-reel format needs the real-footage pivot even on YT.
5. Repurpose Ian s EXISTING real footage (lake house build / room decor videos on the
   channel) into Shorts with affiliate links - authentic visuals, zero new filming.
   Highest-organic-reach asset GHP has access to.
6. Reel quality next step: overlay product photo cards while each product is named;
   18-30s scripts.
7. Do NOT add new infra. Quality, claim, measurement only.

Constraints: never hallucinate ASINs (verify /dp/ liveness via logged-in browser), affiliate
links only /dp/ASIN?tag=goldenhomep06-20&ascsubtag=<channel>, FTC disclosure, en-US-AvaNeural,
commits on the Pi, no secrets in git, no file deletion without explicit yes.
