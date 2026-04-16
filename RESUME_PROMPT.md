# Golden Home Project — Session Resume Prompt

Paste the block below at the start of each Claude Code session. Everything above the `---` is context for you; everything inside the backticks is the actual prompt.

---

## LAST SESSION DELTA (2026-04-16)

**What shipped:**
- Deployed `.github/workflows/instagram-poster.yml` (Meta Graph API posting pipeline)
- First two API-driven posts LIVE on @goldenhomeproject:
  - Mamma Mia Covers (24-30% commission) → media_id 18084608081580290
  - Eli & Elm (20% commission) → media_id 18165440092418254
- Created `automation/agents/ai_revenue_playbook.md` (COSTAR framework, 2026 AI tool stack, revenue feedback loop)
- Updated `content_generator.md` to require COSTAR for every generation
- Image hosting pattern confirmed working: commit image to repo → `raw.githubusercontent.com/...` URL works as Meta Graph `image_url`
- Daily cron scheduled: 14:00 + 22:00 UTC (10 AM + 6 PM ET) pulling from `social/post_queue.json`

**What to do next (ranked by $ ROI):**
1. **Generate 3 Reels this week** (transformation format, 15-30s). Workflow already supports `media_type=REELS` — queue them in `social/post_queue.json`
2. **Repurpose Kitchen Makeover long-form into 10 Shorts via OpusClip** — leverages the existing 6,710 YouTube subs; AdSense + affiliate stacking
3. **Set up Beacons.ai link-in-bio** with all 8 impact.com tracking links + "The $100 Apartment Refresh Checklist" email capture lead magnet
4. **Check impact.com click data for the 2 posts that went live today** — this is the first real data on whether content → clicks → revenue actually works
5. **Queue 5 more static posts** (Syruvia, REBEL, Burke Decor, Dreame, Pit Boss) so the 10am/6pm cron has content to ship for the next week

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
