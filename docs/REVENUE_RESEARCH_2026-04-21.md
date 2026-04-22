# Revenue Research — 2026-04-21

**Question:** Why do accounts in our niche generate revenue while GHP (131 posts, 2 followers, $0) does not? What are they doing that we aren't?

**Method:** Studied 2 winning accounts in adjacent niches with visible engagement proof.

---

## Account A — @sandrauus (Decoration)

- **299K followers, 1,284 posts**
- **12.4K likes** on under-sink organization Reel
- Bio → `uniqueutopia.shop` (Shopify dropshipping store, NOT Amazon affiliate)
- CTA mechanic: comment "Link" → DM reply with store URL
- Comment section is dominated by one-word "Link" replies. Mechanic works.

**Model:** own products + DM funnel. Not our path (we don't have inventory).

---

## Account B — @amandabhome (Amazon Affiliate — DIRECT PEER)

- **811K followers, 915 posts, VERIFIED**
- **25.3K likes** on "Genius Amazon home finds" Reel
- Bio: "Affordable Home Decor + Home Inspo + Amazon Finds / Shop Below ⬇️" → linktree-style hub
- CTA in every post: "Like + comment SEND for links 🔗"
- **14 Story Highlights acting as permanent product catalogs**: Amazon Finds, Home Decor Favs, Gift Guides, BF Deals, Christmas 2025, Prime Day, Target Finds, Walmart Finds, Area Rugs, Fall Decor, Bedroom Decor, Outdoor Faves, Dining Room, Decor Faves
- Hashtags used: `#amazongadgets #amazonhomefinds #amazonhomehacks #amazonmusthaves #amazonorganization` — **every single one is on GHP's current banned list**

---

## Gap analysis — GHP vs @amandabhome

| Lever | GHP | @amandabhome | Revenue impact |
|---|---|---|---|
| Followers | 2 | 811K | Proxy for reach |
| CTA mechanic | "link in bio" | "comment SEND → DM" | **HIGH — comment-to-DM drives comments (algo boost) AND clicks (direct send)** |
| Story Highlights | 0 | 14 category catalogs | **HIGH — every profile visitor has a shoppable catalog** |
| Bio link target | `goldenhomeproject.com` homepage | curated product hub | MEDIUM — we lose clicks even when they arrive |
| "Amazon finds" keywords | BANNED by our voice doc | used aggressively in hashtags | **We are suppressing discoverability** |
| Product catalog | 131 posts, unorganized | 915 posts + 14 segmented collections | MEDIUM |
| Verified | No | Yes | Low-medium |

---

## Hypothesis: our BRAND_VOICE.md was half-wrong

Session 6 (this morning) said formulaic Amazon-finds voice gets algo-suppressed and killed our engagement. Evidence at 811K-follower scale says the opposite: formulaic CTAs + Amazon hashtags are exactly what performs in this niche.

**Reconciled model:** voice theory holds for organic reach from zero — we need distinctive hooks to escape the 2-follower starting gravity. But the **CTA mechanic and discoverability hashtags** should copy the proven winners. These are orthogonal.

**Revised doctrine:**
- KEEP: hook taxonomy, banned openers ("I spent $X…"), falsifiable product details, 180–220 word caption structure.
- CHANGE: CTA section — mandate "comment KEYWORD for the link" as primary CTA instead of "link in bio".
- CHANGE: hashtag strategy — allow `#amazonhomefinds`-family as discovery tags once per post. Un-ban.
- ADD: Story Highlights are a P0 asset. Every post should target a named category (Kitchen, Bathroom, Sleep, Pets, Organization, Tech, Under $50) that becomes a Highlight.

---

## Revenue levers ranked

| # | Lever | Effort | Expected impact this week |
|---|---|---|---|
| 1 | **Rewrite 2 queued captions with "comment LINK → DM" CTA** before they ship tomorrow 14:00 UTC | 15 min | Converts any commenter into a DM click; comments boost algo |
| 2 | **Set up Instagram native DM auto-reply for keyword "LINK"** (Meta Business Suite → Automated responses) | 30 min | Automates the DM response at scale — required or the CTA becomes manual work |
| 3 | **Un-ban Amazon discovery hashtags** in `content_quality_gate.py` | 10 min | Regains hashtag discoverability we were voluntarily surrendering |
| 4 | **Build Story Highlights skeleton** (Kitchen / Bathroom / Sleep / Pets / Under $50) — can reuse existing 131 posts | 2 hrs | Every profile visitor gets a shoppable catalog |
| 5 | **Upgrade bio link from goldenhomeproject.com to curated product hub** (Stan Store or similar free option) | 1 hr | Recovers click-through when users still go to bio |
| 6 | **Amazon Storefront + Associates storefront builder** — check if already configured | 30 min | Native shoppable storefront = higher commissions on some categories |

---

## Next actions (this session)

1. Update `docs/BRAND_VOICE.md` — CTA section + hashtag section reconciled with evidence
2. Update `automation/content_quality_gate.py` — un-ban Amazon discovery tags, require DM-CTA pattern
3. Rewrite the 2 queued captions in `social/post_queue.json` with DM CTAs
4. Set up Instagram keyword auto-reply (Meta Business Suite)
5. Start Story Highlights skeleton

Ship these and the 14:00 UTC post tomorrow is the first GHP post that actually has a complete revenue funnel.
