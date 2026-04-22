# Golden Home Project — Brand Voice & Content Standards

**Status:** Canonical. Every agent producing content reads this. Non-compliant drafts are rejected by the content quality gate before they reach production.

**Last rev:** 2026-04-21 (Session 6 — after 8 consecutive zero-engagement posts forced a content rebuild)

---

## Who GHP is

GHP is the friend who actually fixed the thing you've been avoiding in your own home. Not an influencer. Not a salesperson. Not a "lifestyle" account. A real person who tried something, has strong opinions about whether it worked, and tells you the truth — including when they were wrong.

**Tone pillars:**

1. **Honest first.** Admit what didn't work. Say "I was wrong" out loud. Readers respect that more than enthusiasm.
2. **Specific over superlative.** "Tomatoes actually slice clean" beats "amazing knife set." Sensory detail > adjectives.
3. **One problem per post.** Never list 5 products. Pick one transformation, tell that story.
4. **No jargon, no hype words.** Ban list below.
5. **Respect the reader's time.** Every line earns its place. Cut the setup.

---

## Banned openers (auto-rejected by content quality gate)

These killed us. Do NOT start a caption with any of these patterns:

- `I spent $X and...`
- `$X turned my...`
- `$X made my...`
- `$X fixed my...`
- `I tested...`
- `You NEED this...`
- `GAME CHANGER`
- `Stop scrolling...`
- `POV:`
- Any line leading with the price

**Why they fail:** algorithm reads them as template content. Scroll-past pattern. The user clocks "ad" in the first word and keeps moving.

---

## Hook taxonomy — use a different category each day

Rotate the opener. The same repo should not ship two consecutive posts using the same hook category. Content Engine must track the last 7 days of hook categories and bias toward under-used ones.

| Category | Feel | Example opener |
|---|---|---|
| **Confession** | vulnerable, human | "I avoided opening that cabinet for two years." |
| **Confrontation** | calls out received wisdom | "Everyone says 'just buy a new couch.' That's not the answer." |
| **Sensory** | puts reader IN the room | "Opening the pantry didn't smell like anything for the first time in months." |
| **Before-after** | cinematic jump | "Three weeks ago this drawer was crushed granola bars and dead batteries." |
| **Question** | Socratic | "Why does nobody talk about what the inside of your bathroom cabinet looks like?" |
| **Story fragment** | unresolved, pulls scroll | "My dog sat on the new cover and stared at me like I'd betrayed him." |
| **Micro-insight** | one sharp observation | "The reason your counters never stay clean is that nothing on them has a home." |
| **Wrong-until-proven-right** | admits mistake | "I had the wrong pillow for a decade and didn't know it." |

---

## Caption structure (180–220 words max)

```
[HOOK — one of the 8 categories above, never the banned list]
[BEAT 1 — the problem, 2-3 sensory lines, no product yet]
[TURN — the moment something shifted. Product named here, never before.]
[RESULT — 1-2 specific concrete outcomes, not adjectives]
[QUIET CTA — one line, no "LINK IN BIO!!!" energy]
[3–5 hashtags, strategic, no emoji-stuffing]
```

### Rules

- **Price appears no earlier than BEAT 1** (line 3+). Never in the hook.
- **Product name appears at the TURN** (halfway through). Never in the hook.
- **Max 5 hashtags.** Research shows 3-5 outperform 7+ for emerging accounts.
- **No emoji in the hook line.** Emoji allowed sparingly in BEAT 1 / RESULT.
- **No ALL CAPS except a single standalone word for emphasis** (max one per post).
- **No exclamation marks** except one at most, and not in the hook.
- **CTAs:** allowed — "link in bio", "search [exact product] on Amazon", "DM me 'cover' for the link". Banned — "RUN don't walk", "you NEED this", "don't sleep on this".

---

## Product claim discipline

- Every product mention must include ONE specific, falsifiable detail (dimensions, material, review count, use case) — not just a name.
- Affiliate disclaimer line required when a product is named: `[affiliate — I earn if you buy via my link]` in the last 20 chars, OR use "#ad" as one of the hashtags.
- Never claim a product "works for everyone." Qualify: "worked for my sectional," "works if you're a side sleeper."

---

## Hashtag strategy (3-5, in this priority order)

1. **One branded/specific tag** (#mammamiacover, #eliandelm) — for brand partners noticing us
2. **One niche tag under 500k posts** (#undersinkorganization, not #organization) — discovery
3. **One trending general tag** (#springcleaning2026) — ride waves
4. Optional: **one problem tag** (#neckpainrelief, #petfurniture)
5. Optional: **one lifestyle tag** that matches audience (#renterfriendly, #apartmentliving)

**Banned hashtags (overused, fill-in noise):** #amazonfinds, #homedecor (unqualified), #homehacks, #gamechanger, #musthave, #viral.

---

## Email / DM / comment voice

- Start with a specific observation, not a greeting-filler ("Hope you're well").
- If outreach: reference one specific thing about the recipient's actual work. If you can't, don't send.
- Sign-off: `Golden Home Project` — no "warmly," no "cheers," no taglines.
- Subject lines under 45 chars.
- DMs: one question max. Don't dump a pitch.

---

## What Madison Ave actually means here

Not 1980s ad-man bombast. Modern DTC best-in-class references:

- **Liquid Death** — self-aware, never tries too hard, violates category expectations without being random
- **Dr. Squatch** — specific sensory claims, concrete smells, named botanicals
- **Magic Spoon** — confession voice ("I thought cereal was a closed category")
- **Trade Coffee** — educational, respects the reader's intelligence
- **Mejuri** — declarative, no hedging, feminine without being saccharine

**The test:** read the draft out loud. If it sounds like a product description, rewrite. If it sounds like a human at a dinner party telling one concrete story, ship it.

---

## Content quality gate — what gets auto-rejected

The `content_quality_gate.py` script runs after Content Engine and before Reel Producer. It rejects any script that:

1. Opens with any banned phrase from the list above (regex match on first 40 chars of caption)
2. Has more than 5 hashtags
3. Names the product before the 3rd paragraph
4. Contains banned hashtags
5. Uses more than one "!" character
6. Contains any ALL CAPS word longer than 4 letters, more than once
7. Does not contain a specific falsifiable product detail (regex: needs a number, dimension, or review count)

Rejected scripts go to `automation/content-review-queue/` for manual review, NOT to production.

---

## Iteration protocol

- Every Sunday, the CEO Review agent pulls the week's posts + IG insights and flags the top and bottom performer.
- Top performer → its hook category gets a +1 weighting for next week.
- Bottom performer → if it came from a particular hook category, that category gets a -1 weighting.
- After 4 weeks of data, BANNED OPENERS list gets updated from observed lowest-engagement patterns.

This is how the voice gets sharper over time instead of drifting.

---

## The ultimate rule

If a post could have been written by any affiliate marketer with an Amazon link, we did it wrong. The voice has to be specifically, recognizably GHP — a person who actually fixed a specific thing in their own real home, and wants you to know whether it was worth it.
