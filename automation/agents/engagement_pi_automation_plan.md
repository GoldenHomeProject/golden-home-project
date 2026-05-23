# Engagement Pi Automation Plan

**Goal:** Move @golden_home_project daily engagement (likes/follows/comments/DM-replies) off Mac Chrome sessions and onto the Pi so it runs on cron without needing a human Chrome to be open.

**Status (2026-05-23):** Engagement is the **one remaining manual gap** per `project_ghp_autonomy_audit_2026-05-22.md`. Everything else (posting, blog, trend scout, content engine, DM keyword funnel, IG insights, watchdog, CEO review) is on cron. Engagement still requires my Chrome MCP session because GitHub Actions runners can't be logged in as @golden_home_project on instagram.com.

---

## Why Pi, not GitHub Actions

- IG bot detection compares device + IP + session continuity. A fresh GH Actions runner is on a rotating cloud IP with no cookies — fails the "is this a real human?" check inside 1–2 sessions.
- The Pi is a persistent device on a residential IP. Logging in once and keeping the profile means IG sees the same fingerprint every day — same pattern as a human user.
- The Pi already runs the watchdog and self-review cron jobs successfully. Adding one more cron is low risk.

## Why NOT a paid scheduler (Phantombuster / IGAutomator / etc.)

- GHP is at $0 lifetime revenue. CEO directive: zero spend until first sale. (`project_ghp_ceo_prompt.md`)
- Most paid IG automation tools are also against IG ToS — same risk surface as DIY, but you also lose the money.

---

## Architecture

```
Pi 5 (raspberrypi5.local)
├── Chromium + persistent profile (~/.config/ghp-chromium)
│   └── logged in once interactively as @golden_home_project
├── Playwright (Python) for browser automation
│   └── attach to existing user-data-dir, not headless
├── scripts/engagement_cron.py
│   ├── reads automation/agents/daily_engagement_chrome.md procedure
│   ├── reads social/engagement_targets/*.json (hashtags + size filters)
│   ├── enforces daily caps (10 follow / 30 like / 5 comment)
│   ├── checks Requests folder + Activity panel BEFORE outbound (Step 0)
│   ├── logs to social/engagement_log.json (same shape as today)
│   └── commits log back to repo via gh
└── systemd timer: ghp-engagement.timer (1×/day, 18:00–21:00 UTC randomized)
```

## Sequencing (do not parallelize)

1. **Manual on Pi:** install Chromium + Playwright, create profile dir, run `chromium --user-data-dir=~/.config/ghp-chromium`, log in to instagram.com as @golden_home_project, close. (One-time, ~10 min.)
2. **Port the playbook to Python:** wrap each step in `daily_engagement_chrome.md` as a Playwright function. Start with **Step 0 (Requests + Activity)** because that has the highest ROI per the torilanaee incident and the lowest action-block risk (no outbound actions).
3. **Smoke-test interactively** on the Pi for 5 consecutive days with me reviewing the log + the IG account state. Watch for shadowban signals (reach drop, comments not appearing).
4. **Only after 5 clean runs:** enable the systemd timer and stop running engagement from my Chrome MCP. Update `project_ghp_autonomy_audit_2026-05-22.md` to remove the "ONE GAP" line.

## Action budgets on Pi

Same as `daily_engagement_chrome.md` — no looser. The Pi running the same caps a human runs is the whole point.

| Action | Daily cap | Pacing |
|---|---|---|
| Follow | 10 | randomized 30–90 sec |
| Like | 30 | randomized 8–20 sec |
| Comment | 5 | randomized 60–180 sec |
| DM reply | unlimited | natural |

Hard rule still applies: any "action blocked" or 429 → halt 24h, write a CRITICAL note, email me.

## Failure modes to plan for

- **IG forces re-login** (suspicious-login flow, 2FA). The Pi script must detect the login wall and email me to re-auth on the Pi via VNC/Pi Connect rather than try to brute through it.
- **Cookie expiry.** Detect by checking for the inbox/Requests URL responding 200 with our handle visible. If logged out, halt and email.
- **DOM changes.** IG ships UI updates often. Wrap every selector in a try/except that logs the failure to `social/engagement_log.json` with `result: "selector_miss"` so I can fix it the next day.
- **Action block.** Per playbook, stop for 24h, do not retry.

## Cost

- Pi 5: already deployed.
- Chromium + Playwright: free, OSS.
- IG account: free.
- Cloudflare / proxy: none — residential Pi IP is the asset.

Net new spend: $0. ✓ aligns with CEO operating prompt.

## Kill criterion for this plan itself

If after 2 weeks on the Pi the engagement isn't producing measurable lift (follow-back rate <10%, no new DM inbounds, no comment replies on our posts), kill it and move budget to a different growth lever. Engagement automation isn't a feature — it's a hypothesis.

---

## Next session start (for me)

Open this file. If "Status" still says "one remaining manual gap", run engagement from my Chrome (Step 0 first, then outbound). If the gap is closed, this file gets archived.
