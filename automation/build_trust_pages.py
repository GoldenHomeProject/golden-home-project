#!/usr/bin/env python3
"""build_trust_pages.py — About / Contact / Privacy, the pages affiliate networks check.

Why (2026-08-17): Amazon pays 3%. Walmart pays up to 14% on home, kitchen, storage and
furniture — our exact category — and Wayfair 7%. Same products, same traffic, ~4.7x the
revenue per sale. Those networks (Impact, ShareASale) are free to join but require a
"legitimate, content-rich platform", and in practice reviewers look for About, Contact
and Privacy pages. We had 39 indexed pages and proper affiliate disclosures but none of
those three, which is a cheap reason to get rejected.

Written honestly. Golden Home Project is an LLC running an automated product-research
site: no invented founder, no claim that anyone hand-tested these products, because that
would be a lie and it is exactly what we removed from the blog and social copy.
"""
from __future__ import annotations

from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TODAY = date.today().strftime("%B %-d, %Y")
SITE = "https://goldenhomeproject.com"

HEAD = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{title} | Golden Home Project</title>
<meta name="description" content="{desc}">
<link rel="canonical" href="{site}/{slug}.html">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700&family=Playfair+Display:wght@600;700&display=swap" rel="stylesheet">
<style>
*,*::before,*::after{{margin:0;padding:0;box-sizing:border-box}}
body{{font-family:'Inter',sans-serif;background:#0a0a0a;color:#f0ece4;line-height:1.7;-webkit-font-smoothing:antialiased}}
.wrap{{max-width:760px;margin:0 auto;padding:40px 20px 80px}}
.breadcrumbs{{font-size:13px;color:#a8a4a0;margin-bottom:24px}}
.breadcrumbs a{{color:#d4a745;text-decoration:none}}
h1{{font-family:'Playfair Display',serif;font-size:38px;line-height:1.2;margin-bottom:16px;color:#fff}}
h2{{font-family:'Playfair Display',serif;font-size:24px;margin:32px 0 12px;color:#fff}}
p{{margin-bottom:16px}}
ul{{margin:0 0 16px 22px}}
li{{margin-bottom:8px}}
a{{color:#d4a745}}
.meta{{color:#a8a4a0;font-size:14px;margin-bottom:32px;padding-bottom:24px;border-bottom:1px solid rgba(212,167,69,.15)}}
</style>
</head>
<body>
<div class="wrap">
  <div class="breadcrumbs"><a href="/">Home</a> &rsaquo; {title}</div>
  <h1>{title}</h1>
  <div class="meta">Golden Home Project LLC &middot; Updated {today}</div>
"""

FOOT = """  <p style="margin-top:40px"><a href="/">&larr; Back to Golden Home Project</a></p>
</div>
</body>
</html>
"""

PAGES = {
    "about": {
        "title": "About Golden Home Project",
        "desc": "Who runs Golden Home Project, how we choose products, and how the site makes money.",
        "body": """
  <p>Golden Home Project is a home-organization product research site operated by
  Golden Home Project LLC in Louisville, Kentucky. We publish buying guides for storage,
  organization and everyday home products, focused on things that are inexpensive,
  widely reviewed and actually available.</p>

  <h2>How we choose products</h2>
  <p>Our picks come from Amazon's live best-seller charts, which we read every morning and
  record. A product only appears on this site if it clears the same bar every time:</p>
  <ul>
    <li>priced roughly $5&ndash;$35, where most readers are comparison shopping</li>
    <li>rated 4.5 stars or higher</li>
    <li>backed by a substantial number of customer reviews, not a handful</li>
    <li>verified as a live, buyable listing at the time we publish</li>
    <li>not a disposable commodity (paper goods, batteries) or off-category item</li>
  </ul>
  <p>Because we save those daily readings, we can also tell you when something's price has
  actually changed &mdash; and we cite the dates we observed it.</p>

  <h2>What we do not do</h2>
  <p>We do not claim to have personally bought, tested or lived with these products. Our
  guides are built from verifiable information: listed prices, star ratings, review
  counts, stated dimensions and materials, and what reviewers repeatedly report. If you
  read a first-person story about someone's kitchen on an affiliate site, it is very often
  invented. We would rather be useful than pretend.</p>

  <h2>How this site makes money</h2>
  <p>Golden Home Project is supported by affiliate commissions. When you buy through a link
  here, we may earn a small commission at no additional cost to you. As an Amazon
  Associate, Golden Home Project earns from qualifying purchases. Commissions never
  determine our rankings &mdash; the selection rules above are applied before we know what
  anything pays.</p>

  <h2>Contact</h2>
  <p>Questions, corrections or partnership enquiries: see our
  <a href="/contact.html">contact page</a>. If we get something wrong, tell us and we will
  fix it.</p>
""",
    },
    "contact": {
        "title": "Contact",
        "desc": "How to reach Golden Home Project LLC about corrections, questions or partnerships.",
        "body": """
  <p>We read everything sent to us.</p>
  <h2>Email</h2>
  <p><a href="mailto:goldenhomeprojectllc@gmail.com">goldenhomeprojectllc@gmail.com</a></p>
  <h2>What to write about</h2>
  <ul>
    <li><strong>Corrections.</strong> A price that has moved, a listing that has gone away,
    anything that reads as inaccurate. Product pages change constantly and we would rather
    hear it from you than leave it wrong.</li>
    <li><strong>Product suggestions.</strong> Something you think belongs in one of our
    guides.</li>
    <li><strong>Brands and partnerships.</strong> Tell us what you sell and why it fits a
    home-organization audience.</li>
  </ul>
  <p>Golden Home Project LLC &middot; Louisville, Kentucky, USA</p>
""",
    },
    "privacy": {
        "title": "Privacy Policy",
        "desc": "What Golden Home Project collects, what it does not, and how affiliate links work.",
        "body": """
  <p>This policy explains what happens to information when you visit
  goldenhomeproject.com.</p>

  <h2>What we collect</h2>
  <p>We do not ask you to create an account, and we do not collect names, addresses or
  payment details. This site is a set of static pages; there is no login and no customer
  database.</p>

  <h2>Affiliate links and cookies</h2>
  <p>Links to retailers on this site are affiliate links. When you follow one, the retailer
  may set a cookie that tells them we referred you, so that a commission can be credited if
  you buy something. That cookie is set and controlled by the retailer &mdash; for example
  Amazon &mdash; under their own privacy policy, not ours. We never see your order details,
  payment information or what else is in your cart; we only see aggregate reports of how
  many clicks and orders occurred.</p>
  <p>As an Amazon Associate, Golden Home Project earns from qualifying purchases.</p>

  <h2>Analytics and hosting</h2>
  <p>The site is hosted on GitHub Pages, which may log standard request information such as
  IP address and browser type for security and operational purposes, as nearly all web
  hosts do.</p>

  <h2>Children</h2>
  <p>This site is intended for a general adult audience and is not directed at children
  under 13.</p>

  <h2>Your choices</h2>
  <p>You can block or clear cookies in your browser at any time; the site will still work.
  If you have a question about this policy, email
  <a href="mailto:goldenhomeprojectllc@gmail.com">goldenhomeprojectllc@gmail.com</a>.</p>
""",
    },
}


def main() -> int:
    for slug, page in PAGES.items():
        html = HEAD.format(title=page["title"], desc=page["desc"], slug=slug,
                           site=SITE, today=TODAY) + page["body"] + FOOT
        (ROOT / f"{slug}.html").write_text(html)
        print(f"  wrote {slug}.html")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
