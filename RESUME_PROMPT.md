# Golden Home Project — Session Resume Prompt

Paste the block below at the start of each Claude Code session. Everything above the `---` is context for you; everything inside the backticks is the actual prompt.

---

## LAST SESSION DELTA (2026-04-16 — Session 3, project review)

**Full project review executed against working code. Goal: fix weaknesses, prevent future breakage, don't break anything that works.**

**What shipped (Session 3):**
- **`instagram-poster.yml` — duplicate-post defense** — added archive-URL dedupe: scheduled runs prune any queue entry whose `image_url` already appears in `posted_archive.json`; manual dispatches refuse to re-post a URL that has already been published. Also replaced deprecated `datetime.utcnow()` with `datetime.now(timezone.utc)` (Python 3.12 compat).
- **`daily-poster.yml` — workflow injection fix** — `${{ github.event.inputs.date }}` was being interpolated directly into a bash `run:` block. Moved into `env: DATE_OVERRIDE` + regex-validated `^[0-9]{4}-[0-9]{2}-[0-9]{2}$` before use.
- **`github_daily_poster.py` — silent-exit visibility** — calendar ended Apr 26 and the workflow was silently succeeding on any date past that. Now emits a GitHub Actions `::warning::` annotation and writes a `status:no_content_scheduled` log to `automation/logs/` so the gap is visible in the Actions UI.
- **`content-generator.yml` — prompt contradiction fixed** — prompt told the agent "Commit to claude/ branch. NEVER commit to main" but the workflow itself commits to main. Rewrote to match reality.
- **`engagement-monitor.yml` — regex brittleness fixed** — 4 separate regex calls were only updating 1 of 3 dates and would silently fail on any freeform trailing content. Replaced with atomic `update_row(label, value)` helper that rewrites value + date cells in one pass per row.
- **`links.html` — Featured Partners section added** — new top-of-page cards route IG clicks straight to `mammamiacovers.sjv.io/WO4g63` (24-30%) and `eliandelm.sjv.io/E092ZX` (20%) instead of only Amazon-tagged internal pages. `rel="sponsored nofollow noopener"` for FTC + security hygiene.
- **Deleted `index_old.html`** — confirmed zero references across HTML/MD/Python/YAML/JSON. Dead file gone.
- **Validated all workflow YAML + all automation Python compiles.** No syntax regressions.

**Current state:**
- All 5 workflows parse clean; all 6 automation scripts compile clean
- Queue dedupe is now the safety net even if queue gets stale again
- `impact.com` click check + Meta App Review submission still outstanding from Session 2
- No revenue work this session — pure hardening

**What to do next (ranked by $ ROI):**
1. **Check impact.com dashboard** for clicks on `mammamiacovers.sjv.io/WO4g63` + `eliandelm.sjv.io/E092ZX` — link-in-bio now routes to these directly
2. **Submit Meta App Review** for `instagram_business_manage_insights` — still the biggest blocker on the revenue feedback loop
3. **Produce 3 Reels this week** — watch time drives algorithm, static posts stuck at 0 engagement
4. **Repurpose Kitchen Makeover long-form via OpusClip** → Shorts

**New learnings worth saving to memory:**
- GitHub Actions `run:` blocks must never template `${{ github.event.inputs.* }}` directly — always route through `env:` and validate. Pattern applied in `daily-poster.yml` fix.
- When a workflow edits a markdown table, update value + date cells in a single atomic regex per row — separate-pass regexes silently desync.

---

## LAST SESSION DELTA (2026-04-16 — Session 2, evening)

**What shipped (Session 2):**
- **Post queue refreshed**: cleared the 2 already-posted items (would have been duplicated by next cron) and replaced with 6 fresh COSTAR-scripted captions across 3 brands. Order in `social/post_queue.json`:
  1. `mamma_mia_pet_hair_v1` — pet-owners angle (Mamma Mia, 24-30%)
  2. `eli_and_elm_morning_pain_v1` — side sleeper neck pain (Eli & Elm, 20%)
  3. `kitchen_gadgets_v1` — 5 daily-use items (Amazon goldenhomep06-20, 3-8%)
  4. `mamma_mia_pristine_reveal_v1` — guests-coming-over (Mamma Mia)
  5. `eli_and_elm_weighted_blanket_v1` — sleep anxiety (Eli & Elm)
- **Committed `social/ig_kitchen_gadgets.png`** so the Amazon kitchen post has a public image URL (was only living in /tmp)
- **Built `.github/workflows/ig-insights.yml`** — queries Meta Graph API for any media_id's engagement (like_count, comments_count, + attempts /insights for reach/impressions/saves/shares). Runs daily 03:00 UTC + manual dispatch. Writes `automation/logs/ig_insights_<date>.json`
- **Pulled first real engagement snapshot** on yesterday's two posts: `automation/logs/ig_insights_2026-04-16.json`
  - Mamma Mia (18084608081580290): 0 likes, 0 comments — permalink `instagram.com/p/DXNBirLGKZO/`
  - Eli & Elm (18165440092418254): 0 likes, 0 comments — permalink `instagram.com/p/DXNBrqnDglK/`
- **Identified permissions blocker**: `/{media_id}/insights` returns OAuthException code 10 ("Application does not have permission for this action"). Meta app is in Development mode. Until App Review clears `instagram_business_manage_insights`, reach/impressions/saves/shares via API are blocked — like_count + comments_count still work.

**Current state:**
- 2 IG posts live today (Apr 16, 19:00 + 19:01 UTC), 0 engagement so far
- Cron at 22:00 UTC (6 PM ET) will pop `mamma_mia_pet_hair_v1` and publish it automatically
- Queue has 5 more posts ready for subsequent cron runs (Fri + Sat covered, Sun partial)
- Insights log workflow now part of durable infra — every morning produces fresh log

**What to do next (ranked by $ ROI):**
1. **Check impact.com dashboard for clicks on `mammamiacovers.sjv.io/WO4g63` + `eliandelm.sjv.io/E092ZX`** — this is the ONLY reliable revenue signal until Meta App Review clears. Login: goldenhomeprojectllc@gmail.com. If there are clicks, double down on that brand's creative angles.
2. **Submit Meta App for Review** to unlock `instagram_business_manage_insights` — unblocks reach/impressions/saves/shares and the real revenue feedback loop. Facebook Developer console → App Review → request `instagram_business_manage_insights`.
3. **Add branded tracking links to `links.html`** — current link-in-bio only points to internal /products/post-XXX pages (Amazon-only). Adding direct "Shop Mamma Mia Covers" + "Shop Eli & Elm" brand cards funnels IG clicks straight to 20-30% commission tracking links instead of 3-8% Amazon.
4. **Produce 3 Reels this week** (transformation format, 15-30s). Queue them via `media_type=REELS` in `post_queue.json`. Watch time is the #1 algorithm factor; static posts are currently getting 0 engagement.
5. **Repurpose Kitchen Makeover long-form via OpusClip** → 10 Shorts — leverages 6,710 YouTube subs for AdSense + affiliate stacking.
6. **Set up Beacons.ai link-in-bio** with email capture lead magnet ("The $100 Apartment Refresh Checklist"). Owned audience converts 5-10x social CTR.

**New learnings worth saving to memory:**
- `/insights` endpoint requires App Review; until then only `?fields=like_count,comments_count,permalink` work in dev mode — recorded as `reference_meta_graph_dev_limits.md`
- `post_queue.json` must be drained after manual posts too (cron will otherwise re-post) — workflow only pops queue in scheduled mode, not manual — recorded as `feedback_ig_queue_sync.md`

---

## THE PROMPT (copy-paste this in next session)

```
You are the CEO agent for Golden Home Project LLC. Your goal is revenue via affiliate marketing.

FIRST, in this order:
1. Read /Users/ianmcwherter/.claude/projects/-Users-ianmcwherter/memory/MEMORY.md and the GHP-related memories it points to (project_golden_home, feedback_self_improvement_loop, reference_ghp_ig_posting)
2. Read /private/tmp/golden-home-project/BUSINESS_BRAIN.md — single source of truth
3. Read /private/tmp/golden-home-project/RESUME_PROMPT.md "LAST SESSION DELTA" section for the current state
4. Read /private/tmp/golden-home-project/automation/agents/ai_revenue_playbook.md — your operating playbook

THEN:
- Check impact.com dashboard for clicks/conversions on yesterday's posts (Mamma Mia + Eli & Elm)
- Check Meta Graph API for engagement on media_ids 18084608081580290 and 18165440092418254
- Pick the highest-$-ROI task from RESUME_PROMPT "What to do next"
- Execute autonomously. Agents POST, they don't draft. Push commits immediately.
- Every piece of content uses the COSTAR framework (Context/Objective/Style/Tone/Audience/Response)
- Trigger .github/workflows/instagram-poster.yml to actually post — do NOT stop at "ready to post"

END OF SESSION: update LAST SESSION DELTA in RESUME_PROMPT.md with:
- What shipped (with IDs/URLs/media_ids)
- What to do next (ranked by $ ROI)
- Any new learnings worth saving to memory

Measure success in dollars generated, not tasks completed.
```

---

## Compounding Principles (how each session leaves the next one stronger)

1. **Durable artifacts over ephemeral chat**: every win gets written to `BUSINESS_BRAIN.md` or an agent doc in `automation/agents/`, never left only in conversation history
2. **Working patterns get codified**: if something worked (e.g., Meta Graph API + raw.githubusercontent URLs), the pattern goes into a reference doc so the next agent doesn't rediscover it
3. **Research → playbook → execution**: don't just learn, apply; `ai_revenue_playbook.md` is the output of research, not a reading list
4. **Automation outlives the session**: the cron-scheduled IG poster keeps shipping even when no session is active
5. **Revenue feedback loop**: post → click data → rank what works → double down next week (specified in `ai_revenue_playbook.md` "Revenue Feedback Loop" section)
6. **Memory system** captures user-specific feedback so you don't re-litigate preferences

## Tips
- Run this in Claude Code (CLI, desktop app, or web)
- The agent has access to browser automation, Gmail, file system, GitHub, and all MCP tools
- Add focus if needed: "Focus on: Reels production this session"
- All public content actions require explicit permission per session unless the user grants scope
