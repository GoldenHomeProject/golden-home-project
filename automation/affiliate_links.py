#!/usr/bin/env python3
"""Single source of truth for building monetizable Amazon affiliate URLs.

Two hard rules, both learned the expensive way:

1. ONLY direct ``/dp/<ASIN>?tag=goldenhomep06-20`` links pay this account.
   Amazon SEARCH URLs (``/s?k=...&tag=``) earn $0 — they were the April 2026
   dead-ASIN "fix" and produced zero commission. Never emit a search URL.

2. We had one tracking tag everywhere, so we could never tell WHICH channel
   drove the few clicks we got. Amazon Associates allows up to 100 free
   tracking sub-IDs via the ``ascsubtag`` query param, which surfaces in the
   Associates "Tracking ID" / link-type reports. Stamping every link with
   its channel finally makes attribution possible.

Use ``build_affiliate_url(asin, channel)`` everywhere instead of f-stringing
the URL by hand.
"""
from __future__ import annotations

ASSOCIATES_TAG = "goldenhomep06-20"

# Known channels — keep this list tight so the Associates report stays
# readable. Add a channel here before using it.
CHANNELS = {
    "pinterest",   # pins
    "instagram",   # IG posts / DM funnel
    "blog",        # on-site blog CTAs
    "youtube",     # YT descriptions
    "direct",      # links.html / linktree-style hub
}


def build_affiliate_url(asin: str, channel: str, *, subtag: str | None = None) -> str:
    """Return a monetizable /dp/ affiliate URL with channel attribution.

    asin:    10-char Amazon ASIN (validated loosely).
    channel: one of CHANNELS — becomes the ascsubtag prefix.
    subtag:  optional finer-grained suffix (e.g. a campaign/date), appended
             as ``<channel>_<subtag>`` so reports can roll up by channel.
    """
    asin = (asin or "").strip().upper()
    if len(asin) != 10 or not asin.isalnum():
        raise ValueError(f"implausible ASIN: {asin!r}")
    if channel not in CHANNELS:
        raise ValueError(f"unknown channel {channel!r}; add it to CHANNELS first")
    ascsubtag = channel if not subtag else f"{channel}_{subtag}"
    return (
        f"https://www.amazon.com/dp/{asin}"
        f"?tag={ASSOCIATES_TAG}&ascsubtag={ascsubtag}"
    )


if __name__ == "__main__":
    # tiny self-check
    print(build_affiliate_url("B0D176VGXZ", "pinterest"))
    print(build_affiliate_url("B0D176VGXZ", "pinterest", subtag="2026-05-30"))
