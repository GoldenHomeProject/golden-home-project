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

# Real Amazon TRACKING IDs, one per channel, created 2026-09-02.
#
# ascsubtag alone was not enough. Amazon suppresses Linked Product / Category /
# Top Sellers reporting at our volume ("values may be hidden due to low volumes"),
# and no downloadable report exposes ascsubtag — so after 14 sales we still could
# not say which channel produced them. Amazon DOES group natively by Tracking ID,
# and that view is never suppressed.
#
# All of these belong to the same Associates account, so commission is unaffected;
# this only changes which bucket a click is reported under. ascsubtag is still
# stamped on top for finer-grained (per-date) detail.
CHANNEL_TAGS = {
    "pinterest": "ghppinterest0e-20",
    "instagram": "ghpinstagram0e-20",
    "youtube":   "ghpyoutube0e-20",
    "blog":      "ghpwebsite0e-20",
    "direct":    "ghpwebsite0e-20",
}


def tag_for(channel: str) -> str:
    """Tracking ID for a channel, falling back to the original account tag."""
    return CHANNEL_TAGS.get((channel or "").lower(), ASSOCIATES_TAG)

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
        f"?tag={tag_for(channel)}&ascsubtag={ascsubtag}"
    )


if __name__ == "__main__":
    # tiny self-check
    print(build_affiliate_url("B0D176VGXZ", "pinterest"))
    print(build_affiliate_url("B0D176VGXZ", "pinterest", subtag="2026-05-30"))
