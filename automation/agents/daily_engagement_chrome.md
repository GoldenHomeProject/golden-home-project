# Daily Engagement Agent — Chrome MCP Playbook

**Account:** @golden_home_project
**Goal:** Compound followers + algorithmic surface area through real human-pattern engagement on niche-adjacent viral content. Required because IG Business Graph API does NOT allow following/liking/commenting on others' posts.

**Runtime:** Chrome MCP (browser automation). Requires user logged into IG in Chrome with the Claude browser extension connected. NOT runnable from GitHub Actions cloud.

**Schedule:** Once per day. Best window 14:00–22:00 UTC (peak US activity).

---

## Daily action budget (stay under IG action-block thresholds)

| Action | Daily cap | Pacing |
|---|---|---|
| Follow new accounts | 10 | 30–60 sec between |
| Like reels/posts | 30 | 8–15 sec between |
| Comment on reels | 5 | 60–120 sec between |
| Reply to own DMs | unlimited | natural |

**Hard rule:** if any action returns "action blocked" or 429, STOP for 24h. Log the incident.

---

## Niche targets

**Hashtags to seed Explore:**
- `#homeorganization`, `#organizingtips`, `#decluttering`
- `#kitchenorganization`, `#pantryorganization`, `#undersinkstorage`
- `#amazonhomefinds`, `#amazonfinds`, `#smallspacesolutions`
- `#bathroomorganization`, `#closetorganization`

**Account size sweet spot:** 5K–500K followers. Larger = your engagement is invisible. Smaller = no algorithmic ROI.

**Avoid:** giveaway accounts, dropshipping spam pages, accounts <1K followers.

---

## Procedure (per session)

### Step 1 — Discover targets
1. Open `https://www.instagram.com/explore/tags/<hashtag>/` for one of the niche hashtags
2. Scroll once, identify 3–5 reels with: high view count, comments enabled, creator in size sweet spot
3. Open each in a separate action

### Step 2 — Engage (per reel)
1. **Like** (heart button) — always
2. **Comment** if reel meets quality bar (real human content, not AI/dropship). Use a 1–2 sentence comment that:
   - References a specific detail in the video (proves you watched)
   - Adds a useful thought, not "great post!"
   - Never mentions our affiliate or product (looks spammy)
   - Examples in `social/comment_templates.json`
3. **Follow** the creator if (a) they're in size sweet spot AND (b) we haven't followed them before AND (c) we haven't hit 10 follows today

### Step 3 — Log every action
Append to `social/engagement_log.json` with shape:
```json
{
  "date": "YYYY-MM-DD",
  "action": "follow|like|comment",
  "target_handle": "@username",
  "target_reel_url": "https://instagram.com/reel/...",
  "comment_text": "... (if comment)",
  "result": "success|blocked|skipped"
}
```

### Step 4 — Wrap
- Update `social/engagement_log.json` summary at top with running totals
- If any action returned "blocked", write a CRITICAL note for next session
- Commit log to main: `Engagement: <date> — F<n> L<n> C<n>`

---

## Comment quality bar

A good comment on a niche reel does ONE of:
- Names a specific moment ("that swap from drawer to baskets at 0:15 — chef's kiss")
- Adds a related tip ("the Sterilite version of these is half the price btw")
- Asks a real question ("does the front rack catch on the cabinet door?")
- Compliments a non-obvious detail ("the way you labeled the top of the lids — never thought of that")

A BAD comment:
- "Love this!" / "So cute!" / generic emoji
- Anything mentioning Golden Home Project unprompted
- Anything pitching our products
- More than 2 sentences

---

## Anti-patterns

- **Bulk-liking the same creator's last 10 reels** — looks bot-like; max 1 like per creator per session
- **Following without engaging first** — algorithm reads it as spam; always like → comment → follow
- **Commenting "link in bio"** anywhere — guaranteed shadowban
- **Engaging with the SAME hashtags every day** — rotate at least 3 per session

---

## Validation that this works

Track in `social/engagement_log.json`:
- **Followers-back rate** — what % of accounts we follow follow us back within 7 days
- **Profile-visit rate** — proxy: comment replies on our posts from accounts we engaged with
- **Reach lift** — pre/post engagement period view counts on our own posts (after Meta App Review unlocks insights)

Target Month 1: 20% follow-back rate, 100+ new followers from engagement (vs current ~0/week).
