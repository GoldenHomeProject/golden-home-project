# Reel manifest — 2026-04-28 LINK

**Final asset:** `reel_2026-04-28_LINK_v1.mp4`

## Specs
- 1080x1920 9:16 (Reels/Shorts native)
- 24.04 sec
- 30 fps, H.264 high profile
- AAC mono 24kHz audio (voiceover only — no music in V1)
- 10.4 MB

## Source script
`automation/scripts/reel-2026-04-28-002.json`

## DM keyword
`LINK` → Simple Houseware 2-Tier Sliding Basket Organizer (B01M0TS64K)
Affiliate URL: `https://www.amazon.com/dp/B01M0TS64K?tag=goldenhomep06-20`

## Pipeline (manual, free-only)

| Layer | Tool | Source |
|---|---|---|
| Voiceover | `edge-tts` (Microsoft neural, free, no auth) | `en-US-AvaMultilingualNeural` voice, +5% rate |
| B-roll | Pexels direct download (no API key) | pex_5285483, pex_8580892, pex_8103059 |
| Product images | Amazon hi-res CDN via Chrome DOM scrape | amz_81pQGLlsbIL, amz_51yVKp09O4L |
| Text overlays | PIL/Pillow → 1080x1920 RGBA PNG | Impact font, drop-shadow, 130pt |
| Composite/render | ffmpeg overlay + zoompan + concat | local CLI |

## Scene-by-scene

| # | Dur | Source clip | On-screen | VO |
|---|---|---|---|---|
| 1 | 3s | pex_5285483 (messy sink) | FOUR YEARS OF THIS | "I had four years of bottles falling on my feet." |
| 2 | 4s | pex_8580892 (jar grab) | EVERYTHING JUST FELL | "Reach for paper towels, knock over six things." |
| 3 | 4s | pex_8103059 (cabinet reach) | I GAVE UP TRYING | "I'd given up. Just kept the door shut." |
| 4 | 5s | amz_81pQGLlsbIL hero (Ken Burns) | $32 SLIDING ORGANIZER | "Then I got a 2-tier sliding basket. Chrome, 18 pound shelves." |
| 5 | 4s | amz_51yVKp09O4L lifestyle (Ken Burns) | FRONT SLIDES OUT | "The front pulls out without disturbing the back row." |
| 6 | 4s | pex_8580892 (organized cabinet) | COMMENT LINK | "Haven't dropped a bottle in three weeks." |

## Caption (use when posting)

```
I had four years of bottles falling on my feet every morning.

The cabinet under the kitchen sink was the place things went to die. Sponges, dish soap, an entire bottle of expensive olive oil I forgot I owned. Every morning I reached for paper towels and knocked over six things.

I got a Simple Houseware 2-tier sliding basket — chrome wire, holds 18 lbs per shelf, and the front rack slides out independently of the back.

Now I see everything. Sliding the front out doesn't disturb the back row. Haven't dropped a bottle in three weeks.

Comment LINK and I'll DM you the link.
Amazon affiliate — I earn a small commission at no extra cost to you.

#amazonhomefinds #kitchenorganization #smallspacesolutions #undersinkstorage
```

## Known V1 limitations (improve in V2)
- No background music — voiceover-only
- No transitions between scenes (hard cuts)
- Single voice for whole reel
- Static text overlays (no slide-in animation)
- Pexels b-roll may need crop tuning per scene

## Cost
$0 — used Claude subscription + free third-party tools only.
