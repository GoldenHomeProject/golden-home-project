"""GHP Blog Writer — Agent 4 of the flywheel.

Writes one SEO long-form post per day (5/week via cron, 260/year).

Combines:
- E-E-A-T (Experience, Expertise, Authoritativeness, Trustworthiness) — Google 2026 ranking
- AIDA copy — Attention/Interest/Desire/Action
- Grand Slam Offer value equation — embedded in product sections
- Schema.org Article + FAQPage JSON-LD for SERP features

Output per run:
- blog/posts/<date>-<slug>.html — rendered page
- blog/posts/<date>-<slug>.md — source markdown (for repurpose agent)
- blog/index.html — regenerated index
"""
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _claude_api import call_claude, call_claude_json
from affiliate_links import build_affiliate_url

ROOT = Path(__file__).resolve().parent.parent
BLOG_DIR = ROOT / "blog"
POSTS_DIR = BLOG_DIR / "posts"
POSTS_DIR.mkdir(parents=True, exist_ok=True)
TREND_FEED = ROOT / "social" / "trend_feed.json"

AMAZON_TAG = "goldenhomep06-20"
SITE_URL = "https://goldenhomeproject.com"

SYSTEM_PROMPT = """You are the SEO Blog Writer for Golden Home Project LLC.

Every post MUST hit ALL these bars:

Google E-E-A-T (2026 rankings):
- Experience: first-person, "I tested this" / "I bought this"
- Expertise: specific numbers, measurements, comparisons, technical detail
- Authoritativeness: cite specific products/brands by name
- Trustworthiness: disclose affiliate relationships up front, admit tradeoffs

AIDA copy structure:
- Attention: H1 with specific $ + outcome + timeframe
- Interest: opening 2 paragraphs describe the pain point
- Desire: product sections stack the value equation
- Action: single clear CTA per product ("Check current price on Amazon →")

Hormozi Grand Slam Offer value equation (per product):
value = (Dream × Likelihood) / (Time × Effort)
- State the dream outcome this product delivers
- Show why it's believable (specific $ + reviews)
- Show speed of result
- Show minimal effort required

Voice:
- First-person singular ("I") — NEVER "we" or "our team"
- Conversational, skeptic-to-convert tone
- NEVER "amazing", "game-changer", "you won't believe"
- Always specific $ amounts, never "affordable" or "cheap"
- 1,800-2,400 words (Google's sweet spot for commercial-intent content)

Output format: STRICT JSON — no prose, no fences."""


_STOPWORDS = {
    "the", "a", "an", "and", "or", "for", "to", "of", "in", "on", "with",
    "review", "best", "i", "my", "how", "dollar", "spent", "fix", "this",
    "that", "your", "you", "it", "is", "are", "2026", "2025",
}


def _topic_tokens(text: str) -> set[str]:
    return {t for t in re.findall(r"[a-z0-9]+", text.lower())
            if t not in _STOPWORDS and len(t) > 2}


def _published_topic_token_sets() -> list[set[str]]:
    """Token-set per already-published post slug, stopwords stripped, so a new
    opportunity can be checked for near-duplication before we spend a Claude
    generation on it."""
    sets = []
    for p in POSTS_DIR.glob("*.html"):
        m = re.match(r"\d{4}-\d{2}-\d{2}-(.+)", p.stem)
        if m:
            sets.append(_topic_tokens(m.group(1).replace("-", " ")))
    return sets


def _is_near_duplicate(opp: dict) -> bool:
    """True if this opportunity's keyword cluster substantially overlaps an
    already-published post. Guards against the 8-near-identical-sofa-cover
    failure (2026-04→05) recurring on ANY topic, not just the COVER cluster."""
    cand = _topic_tokens(" ".join(
        str(opp.get(k, "")) for k in
        ("specific_product", "product_category", "keyword", "title", "topic")
    ))
    if len(cand) < 2:
        return False
    for existing in _published_topic_token_sets():
        if not existing:
            continue
        overlap = len(cand & existing)
        # Jaccard over the smaller set: >=0.6 shared meaningful tokens = dupe.
        if overlap >= 2 and overlap / min(len(cand), len(existing)) >= 0.6:
            return True
    return False


def _has_payable_product(opp: dict) -> bool:
    """True when some field of the opportunity maps to a live registry ASIN —
    i.e. the post would ship with a real affiliate CTA instead of cta-disabled."""
    for k in ("specific_product", "keyword", "product_category", "title", "topic"):
        q = str(opp.get(k, "")).strip()
        if q and lookup_registry_product(q):
            return True
    return False


def pick_topic() -> dict | None:
    """Pull the highest-composite opportunity from today's trend feed.

    Guards, in order:
    1. COVER-cluster hardblock (2026-05-11, CEO directive + GSC sandbox
       protection): skip any topic matching the sofa/couch/slipcover cluster.
       The 8 COVER posts published 2026-04-22→05-06 are the only primary signal
       for the 2026-06-05 Stage-1 GSC evaluation; another COVER post pollutes it.
    2. General near-duplicate guard: skip any topic that substantially overlaps
       an already-published post (any cluster). Stops the duplicate-content
       self-sabotage that split ranking signal across the sofa posts.
    3. Monetization preference (2026-06-11, after the 6/03 + 6/10 posts shipped
       with ZERO affiliate links): first pass only accepts topics that map to a
       live registry ASIN; an unmonetized topic is used only when nothing
       payable is available, so the weekly cadence never silently goes dark.
    """
    if not TREND_FEED.exists():
        print("[blog-writer] No trend feed available.")
        return None
    feed = json.loads(TREND_FEED.read_text())
    opps = feed.get("opportunities", [])

    cover_terms = ("cover", "slipcover", "couch", "sofa", "loveseat", "sectional")

    def _eligible(opp):
        haystack = " ".join(
            str(opp.get(k, "")).lower()
            for k in ("product_category", "specific_product", "keyword", "title", "topic")
        )
        if any(term in haystack for term in cover_terms):
            print(f"[blog-writer] SKIPPING COVER-cluster topic until 2026-06-05: {haystack[:80]}")
            return False
        if _is_near_duplicate(opp):
            print(f"[blog-writer] SKIPPING near-duplicate of existing post: {haystack[:80]}")
            return False
        return True

    eligible = [o for o in opps if _eligible(o)]
    for opp in eligible:
        if _has_payable_product(opp):
            return opp
        print("[blog-writer] deferring topic with no live registry ASIN "
              f"(would ship unmonetized): {str(opp.get('keyword') or opp.get('topic') or '')[:60]}")
    if eligible:
        print("[blog-writer] WARNING: no payable topic available — shipping "
              "best unmonetized topic to keep weekly cadence. Grow the vetted pool!")
        return eligible[0]
    print("[blog-writer] No fresh non-COVER opportunities available today.")
    return None


def slugify(s: str) -> str:
    s = s.lower().strip()
    s = re.sub(r"[^a-z0-9]+", "-", s)
    return s.strip("-")[:70]


def generate_post(opportunity: dict) -> dict:
    """Returns structured post object ready to render."""
    prompt = f"""Write a full long-form SEO blog post based on this product opportunity:

{json.dumps(opportunity, indent=2)}

Return STRICT JSON matching this exact schema:
{{
  "title": "H1 — specific $ + outcome, <=65 chars for SERP",
  "slug": "url-safe-slug",
  "meta_description": "<=155 chars, specific $, CTR-optimized",
  "keywords": ["5-8 target keywords"],
  "intro": "2 paragraphs. AIDA: Attention+Interest. First person. Pain point + teaser of transformation.",
  "sections": [
    {{
      "h2": "Section heading",
      "body_markdown": "200-400 words in markdown. Specific details. First-person.",
      "featured_product": {{
        "name": "product name",
        "price_estimate": "$XX",
        "dream_outcome": "sentence",
        "why_believable": "sentence",
        "how_fast": "sentence",
        "how_little_effort": "sentence",
        "amazon_search": "search keywords for Amazon"
      }}
    }}
    // 4-6 sections total
  ],
  "faq": [
    {{"q": "specific question buyers ask", "a": "direct answer with numbers"}}
    // 4-6 FAQs for FAQPage schema
  ],
  "conclusion": "150-200 words, restate transformation + soft CTA to email list",
  "internal_links": [
    {{"anchor": "related post title", "href": "/products/post-XXX.html"}}
  ]
}}"""
    return call_claude_json(prompt, system=SYSTEM_PROMPT, max_tokens=8000)


DM_REGISTRY_PATH = ROOT / "social" / "dm_keyword_registry.json"


def _load_live_registry() -> list[dict]:
    """Return entries[] with status='live' PLUS the vetted[] pool — both are
    payable affiliate destinations for blog use.

    Why both:
    - entries[status='live'] = ASIN + Meta DM automation wired. These have the
      highest conversion path (DM funnel) AND blog use.
    - vetted[] = ASIN verified live in Chrome but no Meta automation yet. These
      are safe for blog/SEO/IG-caption use right now (no DM funnel dependency),
      and become entries[] later once the user wires the Meta automation.

    Live entries rank first so lookup_registry_product() prefers them on ties —
    higher-conversion path wins when both could serve the query.
    """
    try:
        reg = json.loads(DM_REGISTRY_PATH.read_text())
    except Exception:
        return []
    live = [e for e in reg.get("entries", []) if e.get("status") == "live"]
    vetted = list(reg.get("vetted", []))
    return live + vetted


def _registry_url(entry: dict) -> str:
    """Return the affiliate URL we are actually paid on for this registry entry.

    Priority: Impact Radius / network short link (`affiliate_url`) > Amazon
    /dp/ASIN with our tag + blog-channel ascsubtag. Never returns a search URL —
    those do not pay this account (per feedback_ghp_no_search_urls.md 2026-05-26).

    The /dp/ path routes through build_affiliate_url so every Amazon blog click
    is stamped ascsubtag=blog — the only way the Associates report can tell blog
    traffic apart from pinterest/instagram. Network short links (sjv.io) can't
    carry ascsubtag (Amazon-specific), so they pass through unchanged.
    """
    aff = entry.get("affiliate_url")
    if aff and "/s?k=" not in aff:
        return aff
    asin = entry.get("asin")
    if asin:
        return build_affiliate_url(asin, "blog")
    raise ValueError(f"registry entry has no payable URL: keyword={entry.get('keyword')}")


def lookup_registry_product(query: str) -> dict | None:
    """Best-effort match a free-text product query against the live registry.

    Match order: exact keyword (case-insensitive) > category contains > token
    overlap in primary_product field. Returns None if nothing matches — caller
    MUST refuse to ship an affiliate CTA when this happens. Do not fall back
    to a generic search URL: those do not pay this account.
    """
    live = _load_live_registry()
    if not live:
        return None
    q = (query or "").lower().strip()
    if not q:
        return None
    # Exact keyword
    for e in live:
        if e.get("keyword", "").lower() == q:
            return e
    # Category
    for e in live:
        cats = [c.lower() for c in e.get("categories", [])]
        if any(c in q or q in c for c in cats):
            return e
    # Token overlap on product_name (entries[] use `product_name`, not
    # `primary_product` — prior code used the wrong field which silently
    # broke this fallback for the entire project lifetime).
    q_tokens = set(re.findall(r"[a-z0-9]+", q))
    best, best_score = None, 0
    for e in live:
        p = (e.get("product_name", "") or "").lower()
        p_tokens = set(re.findall(r"[a-z0-9]+", p))
        score = len(q_tokens & p_tokens)
        if score > best_score:
            best, best_score = e, score
    return best if best_score >= 2 else None


def amazon_url(query: str) -> str:
    """Deprecated shim — kept only so callers don't crash. Resolves via the
    live registry. Raises if no match (do NOT silently fall back to search)."""
    entry = lookup_registry_product(query)
    if not entry:
        raise ValueError(
            f"No live registry entry matches {query!r}. Add ASIN + Meta automation "
            "before shipping a CTA for this topic. Search URLs are NOT a fallback."
        )
    return _registry_url(entry)


def render_html(post: dict, date_str: str, slug: str) -> str:
    """Render markdown sections → GHP-branded HTML matching site style."""
    sections_html = []
    for sec in post.get("sections", []):
        body = sec["body_markdown"]
        # Minimal markdown → HTML (paragraphs only, the model is fine with that)
        body_html = "".join(f"<p>{p.strip()}</p>\n" for p in body.split("\n\n") if p.strip())
        prod = sec.get("featured_product") or {}
        # Affiliate CTA only when the topic maps to a live registry entry.
        # Search URLs do NOT pay this account — never fall back to one.
        registry_entry = lookup_registry_product(
            prod.get("amazon_search") or prod.get("name") or sec.get("h2", "")
        )
        if registry_entry:
            cta_url = _registry_url(registry_entry)
            cta_html = (
                f'<a class="cta" href="{cta_url}" rel="sponsored nofollow noopener" target="_blank">\n'
                f'      Check current price &rarr;\n'
                f'    </a>'
            )
        else:
            # No payable link — emit a clear in-page note instead of a fake CTA.
            print(
                f"[blog_writer] no registry match for section {sec.get('h2','?')!r} "
                f"product={prod.get('name','?')!r} — shipping without affiliate CTA",
                file=sys.stderr,
            )
            cta_html = (
                '<p class="cta-disabled"><em>We&rsquo;re still vetting a product '
                'we trust enough to link here. <a href="/blog/">Browse other Golden '
                'Home Project picks</a>.</em></p>'
            )
        sections_html.append(f"""
<section class="post-section">
  <h2>{sec['h2']}</h2>
  {body_html}
  <div class="product-card">
    <div class="product-name">{prod.get('name', '')}</div>
    <div class="product-price">{prod.get('price_estimate', '')}</div>
    <ul class="value-stack">
      <li><strong>Outcome:</strong> {prod.get('dream_outcome', '')}</li>
      <li><strong>Why it works:</strong> {prod.get('why_believable', '')}</li>
      <li><strong>Speed:</strong> {prod.get('how_fast', '')}</li>
      <li><strong>Effort:</strong> {prod.get('how_little_effort', '')}</li>
    </ul>
    {cta_html}
  </div>
</section>""")

    faq_html = "\n".join(
        f'<details><summary>{f["q"]}</summary><p>{f["a"]}</p></details>'
        for f in post.get("faq", [])
    )

    # Schema.org JSON-LD
    canonical = f"{SITE_URL}/blog/posts/{date_str}-{slug}.html"
    article_schema = {
        "@context": "https://schema.org",
        "@type": "Article",
        "headline": post["title"],
        "datePublished": date_str,
        "dateModified": date_str,
        "author": {"@type": "Organization", "name": "Golden Home Project"},
        "publisher": {"@type": "Organization", "name": "Golden Home Project LLC"},
        "mainEntityOfPage": canonical,
        "description": post["meta_description"],
    }
    faq_schema = {
        "@context": "https://schema.org",
        "@type": "FAQPage",
        "mainEntity": [
            {
                "@type": "Question",
                "name": f["q"],
                "acceptedAnswer": {"@type": "Answer", "text": f["a"]},
            }
            for f in post.get("faq", [])
        ],
    }

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{post['title']} | Golden Home Project</title>
<meta name="description" content="{post['meta_description']}">
<link rel="canonical" href="{canonical}">
<meta property="og:title" content="{post['title']}">
<meta property="og:description" content="{post['meta_description']}">
<meta property="og:type" content="article">
<meta property="og:url" content="{canonical}">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700&family=Playfair+Display:wght@600;700&display=swap" rel="stylesheet">
<script type="application/ld+json">{json.dumps(article_schema)}</script>
<script type="application/ld+json">{json.dumps(faq_schema)}</script>
<style>
*,*::before,*::after{{margin:0;padding:0;box-sizing:border-box}}
body{{font-family:'Inter',sans-serif;background:#0a0a0a;color:#f0ece4;line-height:1.7;-webkit-font-smoothing:antialiased}}
.wrap{{max-width:760px;margin:0 auto;padding:40px 20px 80px}}
.breadcrumbs{{font-size:13px;color:#a8a4a0;margin-bottom:24px}}
.breadcrumbs a{{color:#d4a745;text-decoration:none}}
h1{{font-family:'Playfair Display',serif;font-size:38px;line-height:1.2;margin-bottom:16px;color:#fff}}
.meta{{color:#a8a4a0;font-size:14px;margin-bottom:32px;padding-bottom:24px;border-bottom:1px solid rgba(212,167,69,.15)}}
.affiliate-disclosure{{font-size:12px;color:#a8a4a0;background:rgba(212,167,69,.06);padding:12px 16px;border-left:3px solid #d4a745;margin-bottom:32px;border-radius:4px}}
.intro{{font-size:18px;color:#e8e4dc;margin-bottom:32px}}
.intro p{{margin-bottom:16px}}
h2{{font-family:'Playfair Display',serif;font-size:26px;margin:40px 0 16px;color:#fff}}
.post-section p{{margin-bottom:14px}}
.product-card{{background:#141428;border:1px solid rgba(212,167,69,.2);border-radius:12px;padding:24px;margin:24px 0}}
.product-name{{font-weight:700;font-size:18px;color:#fff}}
.product-price{{color:#d4a745;font-size:22px;font-weight:700;margin:6px 0 14px}}
.value-stack{{list-style:none;margin-bottom:18px}}
.value-stack li{{padding:6px 0;font-size:15px;color:#d8d4cc}}
.value-stack strong{{color:#d4a745}}
.cta{{display:inline-block;background:linear-gradient(135deg,#d4a745,#b8912e);color:#0a0a0a;font-weight:700;padding:14px 24px;border-radius:8px;text-decoration:none;transition:transform .2s}}
.cta:hover{{transform:translateY(-2px)}}
details{{background:#141428;border:1px solid rgba(212,167,69,.15);border-radius:8px;padding:14px 18px;margin-bottom:10px}}
summary{{cursor:pointer;font-weight:600;color:#fff}}
details[open] summary{{margin-bottom:10px;color:#d4a745}}
.faq-section{{margin-top:40px}}
.conclusion{{margin-top:40px;padding:24px;background:rgba(212,167,69,.06);border-radius:12px;font-size:17px}}
.back-link{{display:inline-block;margin-top:40px;color:#d4a745;text-decoration:none;font-weight:600}}
</style>
</head>
<body>
<div class="wrap">
  <div class="breadcrumbs"><a href="/">Home</a> / <a href="/blog/">Blog</a> / {post['title']}</div>
  <h1>{post['title']}</h1>
  <div class="meta">Published {date_str} · Golden Home Project · {sum(len(s.get('body_markdown','').split()) for s in post.get('sections',[]))}+ word read</div>
  <div class="affiliate-disclosure">
    <strong>Affiliate disclosure:</strong> This post contains Amazon Associate links. If you buy through them I earn a small commission at no cost to you. I only recommend products I've actually used or would use myself.
  </div>
  <div class="intro">{''.join(f'<p>{p}</p>' for p in post['intro'].split(chr(10)+chr(10)) if p.strip())}</div>
  {''.join(sections_html)}
  <div class="faq-section">
    <h2>Frequently asked</h2>
    {faq_html}
  </div>
  <div class="conclusion">{post['conclusion']}</div>
  <a class="back-link" href="/blog/">&larr; More posts</a>
</div>
</body>
</html>"""


def regenerate_index():
    """Rebuild blog/index.html listing all posts by date desc."""
    posts = sorted(POSTS_DIR.glob("*.html"), reverse=True)
    cards = []
    for p in posts:
        name = p.stem  # 2026-04-17-some-slug
        m = re.match(r"(\d{4}-\d{2}-\d{2})-(.+)", name)
        if not m:
            continue
        date, slug = m.groups()
        # Extract title from <h1>
        html = p.read_text()
        title_m = re.search(r"<h1>(.*?)</h1>", html)
        title = title_m.group(1) if title_m else slug.replace("-", " ").title()
        desc_m = re.search(r'<meta name="description" content="(.*?)">', html)
        desc = desc_m.group(1) if desc_m else ""
        cards.append(f"""
<a class="post-card" href="/blog/posts/{p.name}">
  <div class="post-date">{date}</div>
  <h3>{title}</h3>
  <p>{desc}</p>
</a>""")

    index_html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Blog | Golden Home Project</title>
<meta name="description" content="In-depth home transformation guides. Honest product reviews. Specific prices, specific outcomes.">
<link rel="canonical" href="{SITE_URL}/blog/">
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700&family=Playfair+Display:wght@600;700&display=swap" rel="stylesheet">
<style>
*,*::before,*::after{{margin:0;padding:0;box-sizing:border-box}}
body{{font-family:'Inter',sans-serif;background:#0a0a0a;color:#f0ece4;line-height:1.6}}
.wrap{{max-width:880px;margin:0 auto;padding:60px 20px}}
h1{{font-family:'Playfair Display',serif;font-size:44px;color:#fff;margin-bottom:8px}}
.tagline{{color:#a8a4a0;margin-bottom:48px;font-size:17px}}
.post-card{{display:block;padding:24px;background:#141428;border:1px solid rgba(212,167,69,.15);border-radius:12px;margin-bottom:16px;text-decoration:none;color:#f0ece4;transition:all .3s}}
.post-card:hover{{border-color:#d4a745;transform:translateY(-2px)}}
.post-date{{color:#d4a745;font-size:13px;font-weight:600;margin-bottom:8px}}
.post-card h3{{font-family:'Playfair Display',serif;font-size:22px;color:#fff;margin-bottom:8px}}
.post-card p{{color:#a8a4a0;font-size:14px}}
.back{{color:#d4a745;text-decoration:none;margin-bottom:32px;display:inline-block}}
</style>
</head>
<body>
<div class="wrap">
  <a class="back" href="/">&larr; Golden Home Project</a>
  <h1>The Blog</h1>
  <p class="tagline">In-depth transformation guides. Honest product reviews. Specific prices.</p>
  {''.join(cards) if cards else '<p>Posts coming soon.</p>'}
</div>
</body>
</html>"""
    (BLOG_DIR / "index.html").write_text(index_html)


def main():
    date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    print(f"[blog-writer] Starting {date_str}")

    topic = pick_topic()
    if not topic:
        print("[blog-writer] No topic — exiting cleanly.")
        return

    print(f"[blog-writer] Topic: {topic.get('specific_product', topic.get('product_category'))}")
    try:
        post = generate_post(topic)
    except Exception as e:
        print(f"[blog-writer] Claude generation failed: {e}")
        return

    slug = post.get("slug") or slugify(post["title"])
    stem = f"{date_str}-{slug}"

    # Write both HTML + source markdown (markdown fuels repurpose agent)
    html_path = POSTS_DIR / f"{stem}.html"
    md_path = POSTS_DIR / f"{stem}.md"

    html_path.write_text(render_html(post, date_str, slug))
    md_path.write_text(
        f"# {post['title']}\n\n"
        f"> {post['meta_description']}\n\n"
        f"{post['intro']}\n\n"
        + "\n\n".join(
            f"## {s['h2']}\n\n{s['body_markdown']}"
            for s in post.get("sections", [])
        )
        + "\n\n## FAQ\n\n"
        + "\n\n".join(f"**{f['q']}**\n\n{f['a']}" for f in post.get("faq", []))
        + f"\n\n{post['conclusion']}\n"
    )
    regenerate_index()

    print(f"[blog-writer] ✓ {html_path.name} + markdown + index regenerated")


if __name__ == "__main__":
    main()
