# Golden Home Project — Business Brain
# ============================================================
# This file is the single source of truth for the business.
# Every agent reads it at start. Every agent updates it at end.
# Humans review it weekly. Never delete history — append only.
# Last updated: 2026-04-17
# ============================================================

---

## ZERO-COST STACK (2026-04-17 — Session 5 pivot)

**Rule: the flywheel uses subscription + free services only. No per-call API billing.**

| Layer | Primary (free) | Fallback / Notes |
|---|---|---|
| LLM (all agents) | Claude Code CLI via `CLAUDE_CODE_OAUTH_TOKEN` (Max subscription) | 5-hour rolling cap — retry logic handles throttle |
| AI scene images | Pollinations.ai FLUX (no key, unlimited) | Hugging Face / Cloudflare Workers AI as future fallbacks |
| Stock photo/video | Pexels API (key in `PEXELS_API_KEY`) — 200 req/hr, 20k/mo | Pixabay as future fallback |
| Voiceover | edge-tts `en-US-JennyNeural` (no key) | Kokoro TTS / Piper as future fallbacks |
| Background music | Pixabay Music (not yet wired) | — |
| Captions (future) | faster-whisper (CPU, open source) | — |
| Video assembly | ffmpeg Ken Burns + concat demuxer | — |
| Runtime | GitHub Actions cloud (2000 free min/mo) | — |

**Required GitHub Secrets** (all present as of 2026-04-17):
- `CLAUDE_CODE_OAUTH_TOKEN` — from `claude setup-token`, 1 yr validity, drives every Claude-using agent
- `AMAZON_ASSOCIATE_TAG` = `goldenhomep06-20`
- `META_ACCESS_TOKEN` — IG Graph posting
- `IG_BUSINESS_ACCOUNT_ID`
- `PEXELS_API_KEY` — stock photo/video
- `YT_TOKEN_JSON` — YouTube uploader

**No longer used** (remove when convenient):
- `ANTHROPIC_API_KEY` — superseded by `CLAUDE_CODE_OAUTH_TOKEN`

---

## AGENT COORDINATION PROTOCOL (2026-04-20)

**Rule: every autonomous agent — cloud workflows AND claude.ai web routines — reads this file at start and appends a log entry at end.**

This enables the 13 agents (10 cloud workflows + 3 web routines) to coordinate
without stepping on each other's work. BUSINESS_BRAIN.md is the central brain;
`AGENT_LOG.md` is the shared action journal.

### Contract (MUST follow)

1. **At start of every run** — read `BUSINESS_BRAIN.md` top-to-bottom and `AGENT_LOG.md` (last 50 entries). Use this context to decide what to do. Do NOT duplicate work another agent logged in the last 24h.

2. **During the run** — if you send an email, post content, change a status, or make any external-facing change, note it mentally for the log entry.

3. **At end of every run** — append ONE entry to `AGENT_LOG.md` in this exact format:

   ```
   ## <UTC timestamp ISO8601> — <AGENT_NAME>
   **Ran:** <short 1-line summary>
   **Changed:** <files committed OR "none">
   **External actions:** <emails sent / posts published / comments made / "none">
   **Next agent hint:** <one sentence of what the next agent reading this should know>
   ```

4. **Commit directly to `main`** with message `Agent log: <AGENT_NAME> <date>`. Do NOT create a `claude/` branch or open a PR — those never get merged and get lost.

5. **HOW TO PUSH (web routines):** The Claude Code web sandbox has NO `git push` credentials. Do NOT attempt `git push` — it will fail and you will burn the timeout. Instead: use the GitHub MCP tool `push_files` (or `create_or_update_file`) to commit ALL changed files in ONE call to branch `main`. Include `AGENT_LOG.md` plus any other modified files together. If the first call errors, retry ONCE with a 5-second backoff. If it still fails, STOP and write the log entry to a local file as a stub — do NOT loop retry until timeout.

6. **If you update BUSINESS_BRAIN.md** (e.g., new affiliate partner, metric change, strategy pivot), commit that in the SAME commit as the log entry so they're atomic.

### Brand voice (MANDATORY for any agent producing content)

Every caption, email, comment, script, or external-facing text MUST follow `docs/BRAND_VOICE.md`. This is non-negotiable — the formulaic "I spent $X and..." openers killed engagement (8 consecutive posts at zero likes, zero comments). If you're writing copy and haven't read `docs/BRAND_VOICE.md` this run, stop and read it now.

### Why this matters

- The 3 web routines (Email Monitor 8am, Strategy 9am, Affiliate Optimizer 10am) run in sequence and each one should build on what the previous one logged.
- The cloud CEO Review can read `AGENT_LOG.md` to understand what happened across the day before issuing its strategic report.
- No agent should ever "do nothing because unclear" — the log makes context explicit.

### Current agent roster reporting to this protocol

| Agent | Lives on | Schedule | Responsibilities |
|---|---|---|---|
| Email Monitor | claude.ai web routine | Daily 8:00 ET | Gmail triage, brand deal accept/decline, affiliate replies |
| Strategy & Outreach | claude.ai web routine | Daily 9:00 ET | Trend research (YT/TikTok/Pinterest), 1 outreach email/day |
| Affiliate Optimizer | claude.ai web routine | Daily 10:00 ET | Amazon/Impact/CJ/Awin dashboard check, commission tracking |
| Trend Scout | cloud `trend-scout.yml` | Daily 05:00 UTC | Reddit product opportunity scan |
| Content Engine | cloud `content-generator.yml` | Daily 06:00 UTC | 3 Reel scripts/day |
| Reel Producer | cloud `reel-producer.yml` | Daily 07:00 UTC | Render MP4s |
| Blog Writer | cloud `blog-writer.yml` | Mon 10:00 UTC | Long-form SEO post |
| Repurposer | cloud `repurpose.yml` | Mon 09:00 UTC | Multi-platform derivatives |
| IG Insights | cloud `ig-insights.yml` | Daily 05:30 UTC | Instagram metrics pull |
| IG Poster | cloud `instagram-poster.yml` | 14:00 + 22:00 UTC | Publish from queue |
| Engagement Monitor | cloud `engagement-monitor.yml` | Daily | YouTube comment replies |
| Daily Poster (YT) | cloud `daily-poster.yml` | Daily | YouTube Short upload |
| CEO Review | cloud `ceo-review.yml` | Weekly Sun | Strategic synthesis |

---

## FLYWHEEL ARCHITECTURE (2026-04-17 — Session 4 rebuild, Session 5 pivot)

The business now runs as a **closed-loop content flywheel** on GitHub Actions cloud
(runs 24/7, no local machine required). Six autonomous agents feed each other via
git-committed JSON artifacts. Each stage informs the next; analytics feed back to
the top for continuous improvement.

```
┌──────────────────────────────────────────────────────────────────┐
│  S1: Research → S2: Create → S3: Blog → S5: Distribute → S6: CEO │
│      ↑                                                      ↓    │
│      └──────────────── feedback loop ──────────────────────┘    │
└──────────────────────────────────────────────────────────────────┘
```

### Agent roster (all run on GitHub Actions cloud)

| # | Agent | Workflow | Schedule (UTC) | Flywheel Stage | What it does |
|---|-------|----------|----------------|----------------|--------------|
| 1 | **Trend Scout** | `trend-scout.yml` | 05:00 daily | S1 Research | Scrapes Reddit + Claude-ranks top 5 product opportunities → `social/trend_feed.json` |
| 2 | **Content Engine** | `content-generator.yml` | 06:00 daily | S2 Create | Consumes trend feed, produces 3 Reel scripts using **AIDA + Grand Slam Offer** → `automation/scripts/` + queue |
| 3 | **Reel Producer** | `reel-producer.yml` | 07:00 daily | S2 Create | Renders scripts into 1080x1920 MP4s via Pillow+edge-tts+ffmpeg → `social/reels/`, queue `status: ready` |
| 4 | **IG Poster** | `instagram-poster.yml` | 14:00 + 22:00 | S5 Distribute | Publishes next READY Reel from queue via Meta Graph API |
| 5 | **Blog Writer** | `blog-writer.yml` | 08:00 Mon-Fri | S3 SEO | 1,800-2,400 word SEO posts with E-E-A-T + AIDA + Grand Slam → `blog/posts/` |
| 6 | **Repurposer** | `repurpose.yml` | 09:00 Mondays | S5 Multiply | 1 blog post → 5 Reels + 5 Pins + 1 Email + 10 microcopy hooks |
| 7 | **Engagement Monitor** | `engagement-monitor.yml` | 19:00 daily | S6 Measure | YouTube stats + BUSINESS_BRAIN auto-update |
| 8 | **IG Insights** | `ig-insights.yml` | 03:00 daily | S6 Measure | like_count + comments_count per media_id (insights endpoint blocked until Meta App Review) |
| 9 | **CEO Review** | `ceo-review.yml` | 10:00 Sundays | S6→S1 Feedback | Weekly analysis: what worked, what didn't, next week priorities → appends to this file |
| 10 | **Daily YT Poster** | `daily-poster.yml` | 17:00 daily | S5 Distribute | (Legacy) YouTube Shorts from APRIL_CALENDAR |

### Frameworks enforced by every content agent

**AIDA** — Attention/Interest/Desire/Action per scene (Reels) or per section (Blog)
- A: Specific $ amount in hook, ≤3s on screen
- I: Relatable problem, first-person pain
- D: Before→After transformation, value stacked
- A: Single clear CTA (link in bio / "Check price on Amazon")

**Hormozi Grand Slam Offer value equation** — embedded in every product mention
- value = (Dream_Outcome × Perceived_Likelihood) / (Time_Delay × Effort)
- Every product sold against this 4-term ratio, stated explicitly

**E-E-A-T** (blog only) — Google 2026 SEO ranking signal
- Experience: first-person "I tested", "I bought"
- Expertise: specific numbers, measurements
- Authoritativeness: brand names, model numbers
- Trustworthiness: affiliate disclosure up top, honest tradeoffs

**GHP voice rules** (non-negotiable, enforced via system prompt)
- Banned: "amazing", "game-changer", "you won't believe", "we"
- Required: specific $ amounts, first-person "I", skeptic-to-convert tone

### Data flow (how agents talk to each other)

```
trend-scout.py        →  social/trend_feed.json         ────────┐
                                                                 │
content_engine.py     →  automation/scripts/reel-*.json         │
                      →  social/post_queue.json (awaiting_video)│
                                                                 │
reel_producer.py      →  social/reels/reel-*.mp4                │
                      →  social/post_queue.json (status=ready)  │
                                                                 │
instagram-poster.yml  →  social/posted_archive.json             │
                                                                 │
ig-insights.yml       →  automation/logs/ig_insights_*.json     │
engagement-monitor.yml→  automation/logs/engagement_*.json      │
                                                                 │
blog_writer.py        →  blog/posts/*.html + *.md               │
                                                                 │
repurpose.py          →  automation/{pinterest,email,microcopy} │
                                                                 │
ceo_review.py         →  reads ALL above, writes BUSINESS_BRAIN ┘
```

### Shared helper

`automation/_claude_api.py` — single module all agents import.
- Shells out to `claude --print` CLI (from `npm install -g @anthropic-ai/claude-code`)
- Authenticates via `CLAUDE_CODE_OAUTH_TOKEN` env var (Max subscription, not API billing)
- Retry with exponential backoff on subscription cap / timeout / network errors
- JSON extraction handles fenced + unfenced responses
- Every Claude-using workflow installs Node 20 + Claude CLI as pre-step

### Image/video production (Reel Producer)

- **AI scene backgrounds**: Pollinations.ai FLUX endpoint — free, no key, style-tuned prompts ("professional product photography, warm natural lighting, 8k, editorial home magazine style")
- **Motion**: ffmpeg `zoompan` Ken Burns alternating zoom-in/zoom-out per scene
- **Voiceover**: edge-tts `en-US-JennyNeural` at +5% rate
- **Typography**: Pillow overlays with drop shadow, gold accent bars, `@goldenhomeproject` watermark
- **Future upgrades (priority order)**: (1) Pexels B-roll on scenes 1+5 for realism, (2) Pixabay music bed at -20dB, (3) faster-whisper burn-in captions

### Revenue pipeline (where $ comes from)

1. **Reel** posts to IG → hook captures attention → CTA drives to link-in-bio
2. **Link-in-bio** (`links.html`) has Featured Partners section routing directly to:
   - Mamma Mia Covers (24-30% commission)
   - Eli & Elm (20% commission)
   - Amazon category pages with `goldenhomep06-20` tag
3. **Blog** drives long-tail organic traffic → Amazon affiliate links contextually
4. **Email list** (future) → owned audience, 5-10x social CTR

### Failure isolation

Each workflow is independent. Reel Producer failing doesn't stop Blog Writer.
IG Poster skips `awaiting_video` entries until Reel Producer catches up.
No single point of failure — the flywheel keeps spinning.

---

## BUSINESS IDENTITY
- **Name**: Golden Home Project LLC
- **Model**: Amazon affiliate marketing (tag: `goldenhomep06-20`)
- **Niche**: Home organization, kitchen upgrades, bedroom/bathroom transformation
- **Mission**: Help people make their homes beautiful and functional on a budget
- **Revenue model**: Affiliate commissions from Amazon + brand partnerships via Impact/CJ/Awin

---

## LIVE METRICS (update each week)
| Metric | Value | Last Updated |
|--------|-------|--------------|
| YouTube subscribers | 6,690 | 2026-05-02 |
| YouTube total views | 20,035 | 2026-05-02 |
| YouTube videos | 126 | 2026-05-02 |
| YouTube daily poster | ✅ Working (Apr 1: v5m1cnIER4w, Apr 2: YKPHYXP5eqE) | 2026-04-02 |
| YouTube OAuth token | ✅ Refreshed 2026-04-03 | 2026-04-03 |
| Instagram followers | 0 | 2026-04-05 |
| Instagram media count | 122 (+2 today via Meta API) | 2026-04-16 |
| Instagram auto-posting pipeline | ✅ LIVE — Meta Graph API workflow deployed | 2026-04-16 |
| Facebook followers | 0 | 2026-03-31 |
| Amazon affiliate revenue (MTD) | $0 confirmed | 2026-03-31 |
| Active affiliate platforms | Amazon, Impact, CJ, Awin | 2026-03-31 |

---

## CONTENT STRATEGY (current — do not change without reason)
### What works (data-backed):
- **Transformation format** "before → after → products": 5,779 views vs 200 for product roundups
- Specific dollar amounts in hooks ("$47", "$34") dramatically increase click-through
- Series content ("Room by Room Ep 1, 2, 3") builds subscribers over time
- Voiceover + Ken Burns animation on AI frames = professional enough for current stage

### Posting cadence:
- YouTube Shorts: 4/week (Tue, Thu, Sat, Sun) via GitHub Actions at noon ET
- Instagram Reels: Saturdays only (rate-limit recovery, then rebuild)
- Long-form YouTube: bi-weekly (highest revenue per video — 15-20 affiliate links)

### Content formats ranked by revenue:
1. Transformation before/after + specific cost
2. "I tested $X vs $Y" comparison
3. "I use this every morning" daily utility
4. Weird/surprising finds — high share rate
5. Room series episodes — subscriber compounding

### Hooks that convert:
- "My [room] looked like this. Same [room]. $[amount]."
- "I've been doing [X] wrong for [N] years. This fixed it."
- "I was skeptical. I was wrong."
- "I use this every single morning."

### Spring 2026 Trend Insights (updated 2026-04-02):
- **Floral kitchen accents** trending hard — florals on appliances, cookware, Dutch ovens
- **Glass-enclosed pantries** — turning storage into a design feature (great for transformation content)
- **Warm textured minimalism** — layered textures, natural wood tones, calm elevated spaces
- **Multi-functional appliances** — "do more with less" resonates with our budget audience
- **Epoxy flooring transformations** — viral on TikTok, satisfying before/after format
- **Electric food composters** (Lomi) — trending as kitchen staple, eco-angle

### Competitor Analysis (updated 2026-04-02):
- Lone Fox (1.5M subs): budget thrifted makeovers, rolling storage hacks
- Kristen McGowan (1.8M subs): interior design hacks, buying trip content
- Alexandra Gater (600K subs): millennial rental makeovers, affordable focus
- At Home With Nikki (650K subs): storage, organization, efficient spaces
- **Our edge**: specific dollar amounts + affiliate links in every video. Competitors rarely show exact costs.

### Proposed Video Concepts (April 2026):
1. **"I transformed my kitchen with florals. $67."** — ride the floral trend, show before (bland) → after (floral accents: towels, Dutch oven, canisters)
2. **"Glass pantry hack. $120. My friends think I renovated."** — DIY glass-front pantry door + organization products
3. **"I tested a $35 BISSELL vs my old vacuum."** — comparison format, high engagement, BISSELL affiliate tie-in
4. **"Epoxy countertop. $89. Same kitchen."** — ride TikTok's epoxy trend, transformation format
5. **"5 things I use every morning. All under $25."** — daily utility format with multiple affiliate links

---

## STRATEGIC UPDATE (2026-04-13) — Research-Driven Improvements

### Problem Identified
120 IG posts, 2 followers, $0 revenue. The pipeline was broken: brands approved on impact.com but NO content created for them, NO tracking links used, NO coherent link-in-bio. Revenue requires: Brand -> Content -> Tracking Link -> Post -> Click -> Sale.

### Pipeline Built (2026-04-13)
1. Generated tracking links for ALL 8 active impact.com brands
2. Created brand-specific HTML templates + 1080x1080 images for Mamma Mia + Eli and Elm
3. Wrote optimized captions with tracking links
4. Images hosted on GitHub: raw.githubusercontent.com/GoldenHomeProject/golden-home-project/main/social/
5. Ready-to-post queue: social/ready_to_post.md

### 2026 Research Findings Applied
- **Reels-first strategy**: Static posts get minimal reach. Reels are 2-3x discovery. Must shift to 80% Reels.
- **Hashtag strategy changed**: 3-5 hashtags max (not 20-30). Keywords in captions matter more.
- **Micro-influencers win**: Accounts under 50K drive 60%+ of affiliate sales. Our size is actually an advantage in niche.
- **Watch time is #1**: First 3 seconds must hook. 15-30 second Reels optimal for completion rate.
- **Link-in-bio upgrade needed**: Current setup is basic. Beacons.ai or Stan Store for monetization-focused bio with multiple brand links.
- **Content calendar**: Consistent daily posting builds algorithmic favor. Mix Reels (4/week) + Static brand posts (2/week) + Carousel (1/week).
- **Native product tagging**: Instagram now supports affiliate product tags directly in Reels — direct purchase path.

### Immediate Revenue Actions
1. Post Mamma Mia + Eli and Elm static posts (ready in social/ready_to_post.md)
2. Set up Beacons.ai link-in-bio with ALL brand tracking links
3. Start creating 15-30 second Reels (transformation format) featuring brand products
4. Enable native product tagging on IG for brand partnerships
5. Cross-post Reels to YouTube Shorts + Facebook

---

## SESSION 2026-04-16 (evening, session 2) — Queue Refresh + Insights Infra + Permissions Blocker

### Shipped
- `social/post_queue.json` refreshed: cleared 2 stale already-posted items, added 5 fresh COSTAR-scripted captions. Cron at 22:00 UTC will publish `mamma_mia_pet_hair_v1` (pet owners angle, Mamma Mia 24-30%) instead of a duplicate of this morning's post.
- `.github/workflows/ig-insights.yml` built + deployed + verified working. Pulls Meta Graph API data for posts in the last 14 days. Daily 03:00 UTC + manual dispatch.
- First engagement snapshot committed at `automation/logs/ig_insights_2026-04-16.json`:
  - Mamma Mia (18084608081580290): 0 likes, 0 comments, permalink `instagram.com/p/DXNBirLGKZO/`
  - Eli & Elm (18165440092418254): 0 likes, 0 comments, permalink `instagram.com/p/DXNBrqnDglK/`

### Blocker discovered (CRITICAL)
- `/{media_id}/insights` API returns `OAuthException #10 ("Application does not have permission for this action")`
- Root cause: Meta app is in Development mode. `instagram_business_manage_insights` requires Facebook App Review.
- Impact: revenue feedback loop cannot use reach/impressions/saves/shares until App Review. `like_count` + `comments_count` + impact.com clicks are the only signals until then.
- See `reference_meta_graph_dev_limits.md` memory for API-level detail.

### Revenue implications
- impact.com clicks are now the highest-signal metric in our stack until App Review clears. Pull them weekly for $-ROI decisions.
- Adding direct brand tracking links to `links.html` is a likely high-ROI unlock: currently all IG clicks funnel through internal /products/post-XXX pages (Amazon 3-8%) instead of direct brand links (Mamma Mia 24-30%, Eli & Elm 20%).

---

## STRATEGIC UPDATE (2026-04-16) — Pipeline Live, Revenue Lanes Opened

### Milestone: Automated Instagram Posting LIVE
Built and deployed `.github/workflows/instagram-poster.yml` using Meta Graph API. Published two revenue-generating posts:
- Mamma Mia Covers (24-30% commission) — media_id=18084608081580290
- Eli & Elm (20% commission) — media_id=18165440092418254

Both workflow runs returned 200 OK from Meta. First real posts from an automated pipeline end-to-end: content generation → HTML render → PNG hosting → public URL → Meta Graph API → live IG post.

### 2026 AI Revenue Research Applied
New agent spec: `automation/agents/ai_revenue_playbook.md` (COSTAR prompt framework, AI tool stack, Reel algorithm rules, revenue feedback loop, self-improvement loop).

**Top-earning AI patterns adopted:**
1. Faceless YouTube repurposing (existing 6,710 subs + OpusClip = 10x posting surface)
2. AI Reel automation (Invideo AI / OpusClip) for higher cadence
3. Email list capture via link-in-bio lead magnet ("The $100 Apartment Refresh Checklist")
4. Multi-platform cut-down: 1 long-form → 10 shorts
5. Owned-audience > borrowed-audience (email > social)

### Next Execution Priorities (ranked by revenue ROI)
1. **Post 3 Reels this week** (Mamma Mia transformation, kitchen makeover, sleep setup)
2. **Set up Beacons.ai** with all 8 brand tracking links + email capture
3. **Repurpose Kitchen Makeover long-form** into 10 YouTube Shorts (OpusClip free tier)
4. **Schedule post_queue.json** daily at 10 AM + 6 PM ET (workflow cron already set)
5. **Add Reel to post_queue.json** format (media_type=REELS branch already coded)

### Revenue Accountability (new)
- Daily check: posts shipped count, queue depth
- Weekly check: impact.com click-through per brand, IG Insights per post
- Monthly check: $ revenue, kill underperforming brands, double down on winners

---

## AFFILIATE PARTNERSHIPS (active)
| Platform | Brand | Commission | Status | Notes |
|----------|-------|------------|--------|-------|
| Amazon | All home categories | 3-8% | Active | Tag: goldenhomep06-20 |
| Impact | Syruvia Syrups | 20% | Active | ACCEPTED 2026-03-31 — highest commission rate |
| Impact | HermanRx | $250 CPA | Declined | Off-niche (telehealth/GLP-1) |
| Impact | Best Choice Products | 15% + free product | Pre-approved | Home niche (baskets, garden, benches) — JOIN |
| CJ | AliExpress | 9% interior/garden | Active | April Yang confirmed: 9% on interior accessories + garden supplies, 3-day cookie, 90-day lock |
| Impact | Rewarx (AI photo studio) | 50% | Account issue | Keble can't find our account — reply sent 2026-04-02 to troubleshoot |
| Awin | OKUN (US) | TBD | Invited | HOME IMPROVEMENT — on-niche! Accept via Awin (needs browser login) |
| Impact | BISSELL | up to 8.4% | Outreach sent 2026-04-02 | Home cleaning — perfect for transformation "first step" content |
| Direct | Canoly (3-in-1 juicer) | TBD | Reply sent 2026-03-31 | April 30 IG Reel, free sample, awaiting details |
| Impact | AARP | $35+ CPA | Skipped | Off-niche (senior membership org) — not home content |
| Impact | Dreame | 5%+ | Reply drafted 2026-04-03 | Robot vacuums/mops — ON-NICHE, Easter Sale 60% off thru Apr 12, HIGH-AOV ($200-800) |
| Impact | Promeed | TBD | Received promo 2026-04-03 | Silk pillowcases/bedding — ON-NICHE (bedroom), Spring Sale 20% off code PM20 |
| Awin | Oedro (US) | TBD | Skipped | Off-niche (car parts — floor mats, tonneau covers) |
| Impact | Homary | TBD | Outreach drafted 2026-04-02 | Home furniture — ON-NICHE (drafted by web agent) |

---

## CONTENT PIPELINE STATUS
| Item | Status | Location |
|------|--------|----------|
| Posts 001-060 | ✅ Published | YouTube + FB + IG |
| Posts 061-070 | ✅ YouTube published | IG rate-limited (retry) |
| April Shorts 001-013, 015 | ✅ Generated + in repo | /videos/transformation/ |
| April Shorts 014, 016 | ✅ Generated + in repo | /videos/transformation/ |
| April Shorts posting | ✅ Automated | GitHub Actions daily-poster.yml |
| Long-form video (Kitchen) | ✅ UPLOADED TO YOUTUBE | Video ID: UDZ14ww196k — 4:58min, 17 affiliate links, thumbnail set, affiliate comment posted |
| Long-form video (Bathroom) | ✅ UPLOADED TO YOUTUBE | Video ID: ELIWkGUDTPQ — 3:28min, 15 affiliate links, thumbnail set, affiliate comment posted |
| Long-form video (Apt tour) | ❌ Not started | April 22 scheduled |
| Apr 27 Short (Ep 5 Entryway) | ✅ Script ready | automation/scripts/script-2026-04-27.py |
| Apr 28 Short (Syruvia kitchen) | ✅ Script ready | automation/scripts/script-2026-04-28.py — 20% commission partner |
| Apr 29 Short (Bathroom comparison) | ✅ Script ready | automation/scripts/script-2026-04-29.py |
| Apr 30 Short (Canoly IG Reel) | ✅ Script ready | automation/scripts/script-2026-04-30.py — partner commitment |
| May 1 Short (Floral kitchen) | ✅ Script ready | automation/scripts/script-2026-05-01.py — floral trend, $67 |
| May 3 Short (Robot vacuum test) | ✅ Script ready | automation/scripts/script-2026-05-03.py — Dreame 5%+ partner |
| May 4 Short (Glass pantry) | ✅ Script ready | automation/scripts/script-2026-05-04.py — Syruvia 20% integration |

---

## PLATFORM CREDENTIALS (reference — actual secrets in GitHub + .env)
| Service | Account | Notes |
|---------|---------|-------|
| YouTube | goldenhomeprojectllc@gmail.com | OAuth token in yt_token.json |
| Instagram | @goldenhomeproject | Meta Graph API, IG ID: 17841444356554286 |
| Amazon Associates | goldenhomep06-20 | Dashboard: affiliate.amazon.com |
| Impact.com | goldenhomeprojectllc@gmail.com | Syruvia ACTIVE (20%), Best Choice pre-approved |
| CJ Affiliate | goldenhomeprojectllc@gmail.com | AliExpress ACCEPTED (5.8%) |
| Awin | goldenhomeprojectllc@gmail.com | Pending: review invitations |
| Pexels | goldenhomeprojectllc@gmail.com | API key in .env |

---

## AGENT ROLES & RESPONSIBILITIES

### Session Resume
User pastes prompt from `/private/tmp/golden-home-project/RESUME_PROMPT.md` at start of each session.
Agent configs live in `/private/tmp/golden-home-project/automation/agents/`.

### Claude Code CLI (per-session, browser automation + full autonomy)
| Agent | Config File | Primary Job | Authority |
|-------|-------------|-------------|-----------|
| CEO Orchestrator | `ceo_orchestrator.md` | Master coordinator — reads BUSINESS_BRAIN, prioritizes, delegates | ALL |
| IG/FB Content Manager | `social_ig_fb.md` | Create & publish posts on Instagram + Facebook | POST content, manage captions |
| Impact.com Affiliate Mgr | `affiliate_impact.md` | Check approvals, apply to brands, track commissions | APPLY to programs, JOIN brands |
| Engagement & Community | `engagement_community.md` | Like, comment, follow on IG/FB/YT to grow followers | ENGAGE on all platforms |
| Pinterest Growth | `pinterest_growth.md` | Pin affiliate content, manage boards | PIN content (needs account created by user) |

### Claude Code Web (3 slots — daily, full send authority)
| Agent | Frequency | Primary Job | Authority |
|-------|-----------|-------------|-----------|
| Email Monitor | Daily 8am ET | Brand deals, reply to partners, affiliate alerts | SEND emails, accept/decline deals |
| Strategy & Outreach | Daily 9am ET | Trend research, brand pitches, outreach emails | SEND outreach, pitch brands |
| Affiliate Optimizer | Daily 10am ET | Revenue optimization, commission tracking, join programs | JOIN programs, SEND partner emails |

### GitHub Actions (permanent, unlimited)
| Agent | Frequency | Primary Job | Workflow |
|-------|-----------|-------------|----------|
| Daily Poster | Daily noon ET | Post pre-generated Shorts to YouTube | daily-poster.yml |
| Content Generator | Daily 11am ET | Generate transformation video scripts | content-generator.yml |
| Engagement Monitor | Daily 2pm ET | YouTube analytics, comment tracking, metrics | engagement-monitor.yml |

---

## WHAT'S WORKING (validated by data)
- Pollinations.ai: reliable at <3 concurrent requests
- Ken Burns animation + text overlays: professional-looking output
- edge-tts voiceover: natural, free, multiple voices
- GitHub Actions posting: CONFIRMED LIVE — Apr 1 (v5m1cnIER4w) + Apr 2 (YKPHYXP5eqE) both uploaded to YouTube
- Pexels API: now integrated for BEFORE frames (real footage > AI)
- Gmail MCP: connected, agents have FULL SEND authority
- Claude Code web agents: 3 daily agents running with full autonomy
- GitHub Actions agents: Content Generator + Engagement Monitor deployed
- All 16 April Shorts in repo and auto-posting daily

## WHAT'S NOT WORKING / NEEDS FIX
- Instagram/Facebook: 0 followers, API rate-limited (bulk posting)
- No affiliate revenue confirmed (check Associates dashboard)
- IG rate limit: retry posts 061-070 after rate limit clears
- Best Choice Products: Join button needs manual click on Impact.com
- Claude Code web: 3 daily session limit — can't add more agents there
- GitHub Actions workflows can't push logs back — needs `permissions: contents: write` (FIX APPLIED 2026-04-02)
- YouTube Studio/Analytics not accessible via browser automation — need API-based monitoring
- YouTube OAuth token expires ~7 days — needs periodic refresh (last refreshed 2026-04-03)
- macOS Desktop folder: ✅ ACCESSIBLE (fixed 2026-04-04)
- Meta app in DEVELOPMENT mode — only test users can see IG posts (need to submit for App Review for public access)

---

## LESSONS LEARNED (never forget)
1. **Bulk posting kills Meta accounts** — max 1 IG post/day, Saturdays only for now
2. **Product roundups fail** — 50-200 views. Transformation format = 5,779 views. Never revert.
3. **Pollinations 429** — only 1-2 concurrent requests max. Add sleep(8) between calls.
4. **Specific dollar amounts convert** — "$47" > "affordable". Always use exact cost.
5. **Series content compounds** — Room by Room series drives follows, not just views.
6. **Long-form = real money** — 15-20 affiliate links per video vs 3-4 in Shorts.
7. **Off-niche deals hurt trust** — declined HermanRx (telehealth). Stick to home.
8. **GitHub Actions need `permissions: contents: write`** — without it, workflows can post to YouTube but can't push logs back to repo.
9. **Daily posting confirmed working** — 2 consecutive successful posts (Apr 1-2). Automation is reliable.
10. **Competitor channels don't show exact prices** — this is our differentiation. Lone Fox (1.5M), Kristen McGowan (1.8M) don't put dollar amounts in hooks. We do. Keep it.

---

## WEEKLY REVIEW LOG
### 2026-W13 (week of 2026-03-31)
- Full strategy pivot to transformation format
- April 2026 content calendar created (16 Shorts + 2 long-form)
- GitHub Actions daily poster deployed — no Mac dependency for posting
- Claude Code cloud agents set up — no API key dependency
- Pexels API integrated for real BEFORE footage
- Weekly trend research automation built (cron + cloud)
- Email drafts: AliExpress accepted (CJ), HermanRx declined, Canoly draft ready
- Syruvia contract pending acceptance on Impact.com (20% commission — high priority)
- All secrets added to GitHub Actions

### 2026-W14 (week of 2026-04-01) — Opus 4.6 sessions
- Syruvia contract ACCEPTED on Impact.com (20% commission — our highest rate)
- Canoly collaboration reply SENT (April 30 IG Reel, free sample)
- Syruvia thank-you reply SENT to David at sales@syruvia.com
- AliExpress/CJ acceptance reply SENT to April Yang (5.8% commission, CID 7711902)
- HermanRx decline SENT to Mary (off-niche telehealth — stay focused on home)
- Rewarx AI photo studio partnership reply SENT to Keble (50% commission via Impact!)
- 3 cloud agents updated with BUSINESS_BRAIN.md-centered prompts (daily email, weekly strategy+outreach, weekly affiliate)
- ALL 3 cloud agents upgraded: daily frequency + FULL SEND authority (not draft-only)
- GitHub Actions daily poster VERIFIED: workflow correct, all 16 videos in repo, first run April 1 noon ET
- Old failed workflows confirmed cleaned up (only daily-poster.yml remains)
- Best Choice Products identified as pre-approved on Impact.com (15% + free product, perfect home niche)
- trans_014 and trans_016 confirmed in repo (all 16 complete)
- Long-form Kitchen Makeover video PLANNED: 7min, 7 sections, 29 frames, 17 affiliate links + Syruvia integration
- Kitchen Makeover script + video generator created in automation/longform/
- All email drafts cleared (0 remaining)
- Content Generator agent deployed to GitHub Actions (daily 11am ET)
- Engagement Monitor agent deployed to GitHub Actions (daily 2pm ET)
- Claude Code web hit 3-daily-session limit — remaining agents on GitHub Actions
- 4 Canva YouTube thumbnail candidates generated for Kitchen Makeover video
- Kitchen Makeover video: 3:14 duration, 17 affiliate links, $148 product cost, $0 production cost
- EMAIL MONITOR RUN 2026-04-02:
  - April Yang (CJ): AliExpress interior/garden = 9% commission (upgrade from 5.8%!) — reply drafted
  - Rewarx account issue: Keble can't find our account to add credits — reply drafted to troubleshoot
  - OKUN (US) invited us on Awin: HOME IMPROVEMENT brand — on-niche, needs browser accept
  - AARP via Impact: $35+ CPA — off-niche (senior membership), skipped
  - Amazon Associates: Operating Agreement update effective Apr 14, 2026 — informational only
  - Kings Camo (CJ): off-niche (hunting/camo), skipped
- STRATEGY & OUTREACH RUN 2026-04-02:
  - BISSELL outreach pitch DRAFTED (up to 8.4% on Impact, home cleaning — on-niche)
  - Spring 2026 trend research: floral accents, glass pantries, warm minimalism, epoxy floors, multi-functional appliances
  - Competitor analysis: Lone Fox (1.5M), Kristen McGowan (1.8M), Alexandra Gater (600K), At Home With Nikki (650K)
  - Our competitive edge: specific dollar amounts + affiliate links (competitors don't show exact costs)
  - 5 new video concepts proposed based on trending topics
  - Content strategy updated with trend insights and competitor data
- CONTENT GENERATOR RUN 2026-04-02:
  - 4 new scripts created for April 27-30 (gap in calendar filled)
  - Apr 27: Room by Room Ep 5 — Entryway ($41, 3 products)
  - Apr 28: Syruvia kitchen morning routine ($53, 20% commission partner integration + floral trend)
  - Apr 29: Budget vs premium bathroom organizer comparison ($15 vs $55)
  - Apr 30: Canoly 3-in-1 juicer IG Reel (PARTNER COMMITMENT — must deliver)
  - Calendar now covers full April 1-30 (20 Shorts + 2 long-form)
  - Syruvia integrated into content for first time (Apr 28 — highest commission partner)
- ENGAGEMENT MONITOR RUN 2026-04-02:
  - Daily poster CONFIRMED: Apr 1 (v5m1cnIER4w) + Apr 2 (YKPHYXP5eqE) both posted to YouTube
  - Video count now 95 (93 + 2 new automated posts)
  - Git push for logs failing — fixed by adding `permissions: contents: write` to all 3 workflows
  - Competitor analysis: our price-in-hook strategy is unique (Lone Fox, Kristen McGowan, Alexandra Gater don't do it)
  - Instagram recovery strategy: resume 1 post/Saturday when rate limit clears, focus on Reels cross-posts
  - Growth target: 10K subs by Q2 end requires ~110 net subs/week — need viral content or consistent Shorts cadence
- EMAIL MONITOR + STRATEGY RUN 2026-04-03:
  - Dreame (Impact): Easter Sale 60% off robot vacuums/mops — ON-NICHE, reply drafted to Jenny, high-AOV ($200-800)
  - Promeed (Impact): Silk pillowcase Spring Sale 20% off — ON-NICHE (bedroom), promo code PM20
  - Oedro (Awin): Car parts — OFF-NICHE, skipped
  - Homary outreach already drafted by web agent (home furniture — ON-NICHE)
  - 5 total email drafts pending send: April Yang, Rewarx, BISSELL, Dreame, Homary
  - Claude Code web agents CONFIRMED WORKING: Homary outreach was auto-generated by daily agent
- CEO SESSION 2026-04-03:
  - 5 emails SENT via Gmail browser: Dreame, Homary, BISSELL, Keble/Rewarx, April Yang/CJ
  - GitHub Actions workflow fix PUSHED: removed ref:claude from engagement-monitor + content-generator
  - Kitchen Makeover video generated (23.9 MB) but lost to temp dir cleanup — needs re-run
  - Best Choice Products Join blocked by Impact.com Vue.js isTrusted check — needs manual click
  - 3 new content scripts created: May 1 (floral kitchen $67), May 3 (Dreame robot vacuum), May 4 (glass pantry $120 + Syruvia)
  - Content pipeline now extends through May 4
  - YouTube OAuth token REFRESHED via browser OAuth flow — new Bearer token + refresh_token obtained
  - YT_TOKEN_JSON GitHub secret UPDATED (2026-04-03T22:45:39Z)
  - Engagement Monitor re-run CONFIRMED SUCCESS with new token — real analytics flowing again
  - Channel stats confirmed: 6,710 subs, 18,357 views, 106 videos
  - Top performing video: "I Used the Wrong Pantry Organizers for 3 Years" — 109 views
  - Desktop folder still TCC-blocked (macOS permission cached per-process, won't apply until restart)
  - All YouTube automation (Daily Poster, Engagement Monitor, Content Generator) now auth'd and operational

---

## NEXT ACTIONS (priority order)
- [x] Accept Syruvia contract on Impact.com — DONE 2026-03-31 (20% commission!)
- [x] Send Canoly reply — DONE 2026-03-31 (awaiting sample + commission details)
- [x] Set up cloud agents — DONE 2026-03-31 (3 Claude Code web + 2 GitHub Actions = 5 total agents)
- [x] Upgrade all agents to daily + full SEND authority — DONE 2026-04-01
- [ ] Join Best Choice Products on Impact.com (15% + free product, HOME NICHE)
- [x] Accept AliExpress on CJ Affiliate — DONE 2026-03-31 (reply sent, 5.8% commission)
- [x] Send HermanRx decline — DONE 2026-03-31 (off-niche, stay focused on home)
- [x] Accept Rewarx partnership — DONE 2026-03-31 (50% commission via Impact, registered at rewarx.com)
- [x] Plan Kitchen Makeover long-form video — DONE 2026-03-31 (script + generator in automation/longform/)
- [ ] Accept OKUN (US) on Awin — home improvement, ON-NICHE (needs browser login)
- [x] Send 5 emails: April Yang, Rewarx, BISSELL, Dreame, Homary — ALL SENT 2026-04-03
- [ ] Promote Dreame Easter Sale in upcoming content (60% off thru Apr 12, high-AOV)
- [ ] Feature Promeed silk pillowcases in bedroom transformation content (code PM20)
- [ ] Review Amazon Associates Operating Agreement changes (effective Apr 14)
- [x] Refresh YouTube OAuth token — DONE 2026-04-03 (YT_TOKEN_JSON secret updated)
- [x] Verify Engagement Monitor with new token — DONE 2026-04-03 (SUCCESS — real data)
- [x] Generate Kitchen Makeover video + thumbnail — DONE 2026-04-04 (saved to Desktop + repo)
- [x] Upload Kitchen Makeover to YouTube — DONE 2026-04-04 (Video ID: UDZ14ww196k, thumbnail set, affiliate comment posted)
- [x] Create Canva thumbnail for Kitchen Makeover — DONE 2026-04-04 (Candidate 2, design DAHF2va2miI)
- [x] IG rate limit cleared — Meta OAuth refreshed 2026-04-04, 2 Reels posted successfully (trans_003, trans_004)
- [ ] Continue IG Reels: 1/day max to rebuild algo trust
- [ ] Create Syruvia-featured kitchen content (20% commission — prioritize)
- [ ] Refresh YouTube OAuth token again ~2026-04-10 (7-day expiry)

---
*This file is automatically updated by agents. Human review recommended weekly.*
*Agents: always read this file first. Always update relevant sections. Commit to claude/ branch.*

### CEO SESSION 2026-04-04:
- Kitchen Makeover long-form video REGENERATED (previous lost to /tmp/ cleanup)
  - 28 frames via Pollinations.ai + 7 voiceover segments via edge-tts
  - Composed via ffmpeg (moviepy had PIL compatibility bug)
  - Final: 4:58 min, 12.3MB, 1920x1080, 24fps
  - Saved to: ~/Desktop/Golden Home Project Content files/Kitchen_Makeover_LongForm.mp4
  - Also saved: thumbnail.jpg + description.txt with 17 affiliate links
- 4 Canva YouTube thumbnail candidates generated, Candidate 2 selected (diagonal split, $148 centered)
  - Exported to JPG 1280x720, saved to Desktop folder
  - Design ID: DAHF2va2miI in Canva
- Generator scripts committed to repo: automation/longform/ (generate + compose + description)
- Desktop folder TCC access CONFIRMED WORKING (was blocked last session)
- Best Choice Products Join button still blocked by Vue.js isTrusted — NEEDS MANUAL CLICK
- OKUN on Awin — user denied browser navigation (revisit later)
- Gmail: 0 unread emails (inbox clear)
- Content Generator workflow still failing (ref:claude in checkout) — was already fixed, needs next scheduled run to verify
- Established new protocol: always save work to BOTH repo AND Desktop folder immediately
- Kitchen Makeover long-form UPLOADED to YouTube: Video ID UDZ14ww196k
  - Title: "I Transformed My Entire Kitchen for $148 — Every Product Linked"
  - Thumbnail set (Canva diagonal split design)
  - Affiliate comment posted with all 17 Amazon links + Syruvia (comment ID: Ugz0gGQu3-c2anCCR4J4AaABAg)
  - Description has timestamps, all 17 affiliate links, Syruvia link, hashtags
  - This is our HIGHEST-REVENUE single video (17 affiliate links, 20% Syruvia commission)
  - Comment pinning needs YouTube Studio (API doesn't support pin via REST)

### CEO SESSION 2026-04-05 (Week 2 kickoff):
- WEEK 1 BUSINESS REVIEW completed — $0 revenue, but infrastructure fully operational
- Bathroom Makeover long-form video GENERATED + UPLOADED to YouTube
  - Video ID: ELIWkGUDTPQ, 3:28 min, 15 affiliate links, $297 total
  - Thumbnail set (Canva design DAHGBYkD0dY)
  - Affiliate comment posted (Ugyrr36AqC6PhjePKQ14AaABAg)
  - All files backed up to Desktop folder
  - Generator committed to repo: automation/longform/generate_bathroom_makeover.py
- Meta/Instagram OAuth REFRESHED — long-lived token (60-day expiry ~June 3)
  - META_ACCESS_TOKEN GitHub secret updated
  - IG posting confirmed working: 2 Reels published (trans_003 + trans_004)
  - IG strategy: max 1/day to rebuild algorithm trust (bulk posting killed us)
  - Meta tokens backed up to Desktop folder
- Rewarx reply SENT to Keble (50% commission — registered at goldenhomeprojectllc@gmail.com)
- Content Generator workflow CONFIRMED WORKING (was failing, now fixed)
- Daily Poster CONFIRMED: Apr 5 video posted successfully
- All 3 GitHub Actions workflows operational: Daily Poster, Content Generator, Engagement Monitor
- NOW HAVE 2 long-form videos with 32 total affiliate links (Kitchen 17 + Bathroom 15)
- Instagram: 120 media posts, 0 followers — algorithm trust rebuild in progress


---

Now I have enough context to write the review.

---

## WEEKLY REVIEW — 2026-04-19

### What worked (ranked by $ signal)

**Data caveat up front:** YouTube likes are reported as `0` across all 114+ videos all week — this is almost certainly a YouTube API data gap (likes are hidden or not returned in the channel analytics endpoint), not a real signal. IG insights are blocked by the Meta App Review permissions wall (`OAuthException code 10`). There is no measurable $ signal this week. Rankings below are by comment count, the only engagement proxy available.

1. **"My Kitchen Looks Like a Magazine Now — $34 Total"** — 231 views, 4 comments. Budget-reveal hook with a specific low dollar amount ($34) in the title is the clear channel leader. Kitchen category + extreme affordability framing = highest intent.

2. **"I Transformed My Entire Bathroom for $297 — Every Product Linked"** — 81 views, 4 comments. Despite lower views than the air purifier video, this tied for most comments. "Every product linked" CTA in the title signals high purchase intent traffic — people clicking to shop, not just browse.

3. **"The Shower Caddy I Wasted $40 On (And What I Use Now)"** — entered the top 10 at 17 views Apr 16, climbed to 39 by Apr 17. Newest entrant showing fastest velocity. Negative framing ("wasted $40 on") is an underused hook format worth doubling down on.

**Angles that outperformed:** (a) specific dollar amount in title, (b) "every product linked" trust signal, (c) mistake/regret framing.

---

### What didn't work

1. **Subscriber growth: zero.** Flat at 6,690 all seven days. Channel is generating views (145 net new this week) but not converting to subscribers. No subscribe CTA in scripts or end screens is the likely culprit.

2. **"Room by Room" series (Ep 1 & 2)** — 72 and 45 views respectively, zero comments either episode. Series format is underperforming single-topic shorts. The hook lacks the immediate dollar specificity that drives clicks ("The Cabinet Nobody Looks In" = no pain, no price, no promise).

3. **Engagement Monitor comment response: 0 all week.** The agent runs daily and logs `"comments_responded": 0` every single day. Unanswered comments are dead affiliate conversion opportunities. The agent is monitoring but not acting.

---

### Flywheel health

- **Trend Scout:** Cannot assess — no `social/trend_feed.json` output was available for review. Need to verify the workflow is committing artifacts.

- **Content Engine:** Scripts confirming AIDA + Grand Slam structure (confirmed via `reel-2026-04-19-001.json` — proper attention/interest/desire/action breakdown + 4-term value equation). Firing correctly.

- **Reel Producer:** Healthy. Six MP4s committed this week across two batches (Apr 18: 3 reels, Apr 19: 3 reels). `reel-producer.yml` is the most reliable agent in the stack.

- **Blog Writer:** **Not firing.** `blog/posts/` is empty. No SEO content has been produced. This is the biggest flywheel gap — zero long-tail search surface and no content for the Repurposer to consume.

- **Repurposer:** Dependent on Blog Writer output, so also producing nothing. The 1→20 multiplier is completely dormant.

---

### Next week priorities (ranked by $ ROI)

1. **Fix Blog Writer agent** (`blog-writer.yml`) — highest leverage gap. Zero blog posts = zero Google indexing, zero Repurposer fuel. Diagnose whether the workflow is failing silently or the output path is misconfigured. Target: 5 posts by Friday.

2. **Fix IG Insights permissions** — submit or escalate the Meta App Review for `instagram_manage_insights`. Without it, IG content is flying blind. This blocks the entire IG feedback loop.

3. **Add subscribe CTA to Content Engine scripts** — one line change to the script prompt: require scene 6 to include "subscribe for weekly home upgrades" overlay. Flat sub count at 6,690 with consistent views means the funnel has a hole.

4. **Wire comment-response logic into Engagement Monitor** — the agent logs `comments_responded: 0` every day. Add a response step: pull comments on top-10 videos, reply with a pinned affiliate link. Even 5 replies/week compounds.

5. **Double down on negative-framing hooks** ("I Wasted $X on...", "I Used the Wrong...") — "Shower Caddy I Wasted $40 On" is the fastest-climbing video this week. Brief the Content Engine to generate at least one "mistake/regret" script per daily batch.

---

### Hypothesis to test next week

**Bet:** Adding "Every Product Linked" to video titles increases comment-to-click conversion rate. The bathroom video ($297) has identical view-to-comment ratio as the kitchen video ($34 total) despite having 3x fewer views — the "every product linked" trust signal may be driving higher intent engagement.

**Measure:** Publish two shorts this week — one with "Every Product Linked" in title, one without. Compare comments-per-100-views at 72 hours. If the linked variant is ≥2x, standardize the suffix across all product-stack titles.


---

Now I have everything needed. Here is the strategic weekly review:

---

## WEEKLY REVIEW — 2026-04-26

### What worked (ranked by $ signal)

**Data caveat:** YouTube OAuth expired April 20 — only April 19 has real data. All YouTube likes report as `0` (API limitation, not actual). IG insights remain fully blocked (`OAuthException code 10`, Meta App Review still pending). The only valid $ proxies this week are **view count** and **comment count**.

1. **"I Made My Living Room Look Twice as Expensive for $67"** — 221 views, 0 comments. Channel's top performer. Specific dollar amount + aspirational outcome in title. Living room is the highest-traffic content category; budget-vs-outcome framing is working.

2. **"I Tested $25 vs $120 Air Purifiers. Here's the Truth."** — 196 views, 1 comment. Comparison/"I tested" format is the second-strongest angle. No prior link to a brand partnership — next version should have a clear affiliate call-to-action.

3. **"I Transformed My Entire Bathroom for $297 — Every Product Linked"** — 81 views, 4 comments. **Highest intent signal in the dataset.** Fewer views than the top two but tied for most comments. "Every Product Linked" in the title is drawing purchase-ready traffic. This is the closest thing to a $ signal we have this week.

**Angles that outperformed:** specific dollar amount in hook, "I tested X vs Y" comparison, "every product linked" trust signal.

---

### What didn't work

1. **"Room by Room" Ep 1 and Ep 2** — 72 and 45 views, zero comments each. Ep 3 outperformed both (130 views). The series hook lacks price and pain specificity: "The Cabinet Nobody Looks In" and "The Junk Drawer Doesn't Have to Exist" are descriptive but not clickable. No dollar amount = no urgency.

2. **"My Nightstand Was a Disaster. $28 Fixed It."** — 1 view after multiple days live. Either a posting failure (wrong publish time, not indexed) or the nightstand category has near-zero search demand. Pattern: bedroom single-product shorts underperform multi-product transformation format.

3. **Comment response rate: 0 all week, every day.** The Engagement Monitor logs `comments_responded: 0` on every single run. Comments sitting unanswered on the bathroom video ($297, 4 comments) are direct affiliate conversion opportunities being abandoned.

---

### Flywheel health

- **Trend Scout:** Firing daily (Apr 22–26, confirmed in AGENT_LOG), but **scanning 0 subreddits every run**. It is generating opportunity ideas from thin air — not real Reddit data. The Reddit scraper is broken. The "opportunities" it surfaces are internally recycled, not market-derived. This needs a fix before the Content Engine can be data-driven.

- **Content Engine:** Assumed firing (Reel Producer receiving inputs), but no AGENT_LOG entry this week to confirm. Cannot verify AIDA + Grand Slam compliance without inspecting this week's scripts directly.

- **Reel Producer:** Six IG Reels posted this week (Mamma Mia couch cover, bathroom cabinet, pillow — confirmed in IG insights data). MP4s are rendering and publishing. Most reliable agent in the stack.

- **Blog Writer:** One post confirmed in repo (`2026-04-23-mamma-mia-waterproof-stretch-sofa-cover-review.md`). Up from zero last week — this is real progress. Not yet indexed in GSC (no data available); first indexing typically takes 1–2 weeks.

- **Repurposer:** Cannot confirm it fired this week — no AGENT_LOG entry. With only 1 blog post available, even if it ran, the 1→20 multiplier has minimal input to work with.

---

### Next week priorities (ranked by $ ROI)

1. **Fix YouTube OAuth token immediately** (`engagement-monitor.yml` has been dark since Apr 20). This is the second time the token has expired. Implement a refresh-token rotation in the workflow so it doesn't require a manual reset every 7 days. Until fixed, we are flying blind on channel analytics.

2. **Fix the Reddit scraper in Trend Scout** (`trend-scout.py`). It has scanned 0 posts for 5 consecutive days. Every Content Engine run this week was built on fabricated signals. Diagnose the praw/API auth or rate-limit issue, add a sanity check that aborts and alerts if post count = 0.

3. **Submit Meta App Review for `instagram_manage_insights`**. This has been a known blocker since April 16. Without it, we cannot measure IG at all. Check `docs/META_APP_REVIEW_SUBMISSION.md` for current submission status — if not submitted, do it this week.

4. **Wire comment-response logic into Engagement Monitor** — add a step that pulls comments on top-10 videos and posts a reply with the relevant affiliate link. Target: ≥5 replies on the $297 bathroom video's 4 open comments this week.

5. **Brief Content Engine on "comparison" format** — "I Tested $25 vs $120" is the second-best performer and has the clearest affiliate structure (winner gets the link). Request at least one comparison script per daily batch.

---

### Hypothesis to test next week

**Bet:** The "I tested $X vs $Y" comparison format drives higher affiliate click intent than the single-product transformation format, because it creates a clear "winner" the viewer wants to buy.

**Measure:** Publish one comparison short and one transformation short in the same week with equivalent view counts (100+ views threshold). Compare comments-per-100-views at 72 hours. If the comparison format is ≥1.5x, shift Content Engine to 2 comparison scripts per 3-script daily batch.

---

*Total infrastructure failures this week: 2 critical (YouTube OAuth blackout 6/7 days, Trend Scout scanning 0 posts 5/5 days). Revenue data: $0 confirmed. One blog post is a real milestone — Repurposer needs to consume it immediately.*
