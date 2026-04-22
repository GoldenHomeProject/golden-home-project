# Meta App Review — Submission Pack

**App:** Golden Home Project (Meta / Facebook developer app backing the IG Graph API integration)
**Permission requested:** `instagram_manage_insights`
**Why blocked:** Until this permission is granted, `/{media-id}/insights` returns an error in dev mode. We can see `like_count` and `comments_count` but not reach / impressions / profile visits / saves. CEO Review agent needs insights to know which hooks win.

---

## 1. Use-case description (paste in App Review form)

Golden Home Project is a one-person Instagram publisher that posts home-improvement product Reels (affiliate). We use the Instagram Graph API to:

1. Publish Reels and image posts to our business IG account `@golden_home_project` (already approved scopes: `instagram_content_publish`, `pages_show_list`, `pages_read_engagement`).
2. Read post-level insights (reach, impressions, profile visits, saves) so our weekly "CEO Review" script can identify which hook styles are actually driving reach and which are getting suppressed. Without `instagram_manage_insights` we are flying blind — Meta's dev-mode responses only expose `like_count` / `comments_count`, which is insufficient to diagnose reach-vs-engagement failures.

**We do NOT use this permission to:** read another user's data, operate a surveillance product, display insights to third parties, or resell data.

**Who sees the data:** only the single operator of the app (the business owner). Insights are written to `social/ig_insights.json` inside a private GitHub repository and consumed by internal scripts.

## 2. Test instructions (for Meta reviewer)

1. Log into `@golden_home_project` on instagram.com (credentials provided via the secure reviewer form).
2. Confirm recent posts exist (>10 REELS, most recent within last 48h).
3. From a terminal with `curl`, run:
   ```
   curl -s "https://graph.facebook.com/v21.0/{media-id}/insights?metric=reach,impressions,saved,profile_visits&access_token={reviewer-token}"
   ```
4. Expected response: JSON with four metric objects. This is the exact call our `automation/ig_insights.py` script makes; no UI surface.

## 3. Screencast script (record ~90 seconds, upload as .mp4)

Frame 1 — open `social/ig_insights.py` in an editor, highlight the line:
```python
url = f"https://graph.facebook.com/v21.0/{media_id}/insights?metric=reach,impressions,saved,profile_visits&access_token={TOKEN}"
```

Frame 2 — run the script against a real media ID. Show terminal output: "401 / permission denied" before approval.

Frame 3 — narrate: "Once instagram_manage_insights is approved, this same call will return the four metrics below which feed our weekly CEO Review."

Frame 4 — open `automation/ceo_review.py`, highlight where insights JSON is read. Narrate: "Reach and saves drive our hook-category weighting. No UI — purely internal analytics."

Frame 5 — open `@golden_home_project` Instagram profile (business account), show posts are public product Reels, not sensitive content.

## 4. Privacy policy URL

https://goldenhomeproject.com/privacy (confirm this page exists and mentions IG data handling — write if missing).

## 5. Data deletion instructions URL

https://goldenhomeproject.com/data-deletion (confirm or create — required by Meta).

## 6. Business verification

Meta requires business verification for `instagram_manage_insights`. If Golden Home Project LLC is not verified:
- Upload LLC formation doc (Delaware/state of formation)
- Upload EIN letter from IRS
- Expect 3–5 business days for verification decision before the permission review even opens

## 7. Fallback if review is denied

If denied, the CEO Review agent can still run on `like_count + comments_count + follower delta`. Scoring loses reach-based signal but the banned-opener / hook-rotation loop still improves voice from engagement alone.

---

**Status:** draft prepared 2026-04-21. Submit once the correct Meta account is logged in on this machine.
