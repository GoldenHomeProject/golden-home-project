# GHP Improvement Queue — bounded fuel for autonomous sessions

Each item is a concrete on-page or research task that compounds when traffic eventually arrives via SEO.

**Rules:**
- Each session does ONE item, not all.
- Mark with `[done YYYY-MM-DD commit-sha]` when shipped.
- When the queue is empty, **refuse to invent busywork.** Log "queue exhausted, ending" and stop. The bottleneck is GSC indexing/ranking, which I cannot accelerate by running more.
- Adding new items is allowed ONLY when grounded in a fresh competitive teardown or actual traffic data — not speculation.

---

## On-page SEO improvements (existing 8 COVER posts)

### High leverage
- [x] ~~**Internal cross-links between the 8 posts.** Each post links to 2-3 sibling posts in a "Related reviews" block. Builds topical authority signal; distributes any future PageRank evenly across the cluster.~~ **[done 2026-05-08 485d472]** — Ring-link graph (i+1, i+3, i+5 mod 8): 24 internal edges, 3 in / 3 out per post, zero self-links, zero broken targets. Rendered as semantic `<aside class="related-reviews" aria-label="Related reviews">` before the `.back-link` anchor on every post.
- [x] ~~**Open Graph + Twitter Card tags.** og:title, og:description, og:image, twitter:card="summary_large_image". When posts ARE shared (currently rare), shares render with rich previews → measurably higher CTR.~~ **[done 2026-05-09 e3a9269]** — Injected og:image, og:image:alt, og:site_name, og:locale + twitter:card="summary_large_image", twitter:title, twitter:description, twitter:image, twitter:image:alt across all 8 COVER posts via /tmp/inject_og_twitter.py. og:image points to the Amazon product CDN URL already published in each post's Product schema (no new external exposure). Idempotent injector; HTML parse-clean; zero duplicates.
- [ ] **About page (`/about.html`)** with real author bio, contact, "I bought Mamma Mia covers with my own money" disclosure paragraph. Then update Person schema across all 8 posts to reference `/about.html#author`. EEAT signal compounds across every page.
- [ ] **Image alt text + filename audit.** Currently most images use generic filenames (e.g., `couch1.jpg`). Rename to keyword-rich slugs (`mamma-mia-cover-after-six-weeks-pet-test.jpg`) and write descriptive alt text. Free image-search traffic over time.

### Medium leverage
- [ ] **Table-of-Contents block + jump-link anchors** on long posts. Increases dwell time signal; helps featured-snippet eligibility for "how do I..." queries within the post.
- [ ] **Comparison table** added to at least one pillar post: Mamma Mia vs SureFit vs RHF (the actual competitors per Good Housekeeping list). Tables get featured-snippet treatment in SERP ~3x more than prose.
- [ ] **FAQ rotation:** current 6 questions are near-duplicates across all 8 posts. Diversify to 8-10 unique questions per post by mining "People Also Ask" boxes. Each unique question is a separate search-eligible snippet.
- [ ] **Last-modified dates** in schema + visible body. "Updated 2026-XX-XX" beats "Published 2026-04-23" for evergreen review intent.

### Low-but-easy
- [ ] **Canonical URL tags** explicitly set per post (rel="canonical"). Cluster has near-duplicate content; explicit canonicals prevent Google picking the wrong one.
- [ ] **Schema validation pass:** run all 8 posts through schema.org validator, fix any warnings. (Already JSON-valid; this is markup-validity check.)
- [ ] **Mobile viewport / preload hints** in `<head>` for Core Web Vitals.

## Research / strategy (compounds for Stage-1 fallback)

- [ ] **5 fallback keyword clusters** mapped via Google autocomplete + DDG SERP teardown. Goal: have 5 alternatives ready if the COVER cluster shows zero impressions on 2026-06-05. Each candidate gets: estimated competition (top-3 SERP authority), search-intent classification, available affiliate offers, real product to anchor reviews.
- [ ] **Competitor backlink profile** of Modern Day Pets (#3 result) via free `linkminer.com` or similar. They're a niche site — what does their backlink graph look like? Inform whether GHP can realistically match it.
- [ ] **3 first-sale Reddit case studies** from r/Affiliatemarketing — read 3 posts dated 2024-2026 from accounts that earned their first $1-100. Identify common patterns. Compare to GHP's setup. Write findings to `social/RESEARCH_first_sale_patterns.md`.
- [ ] **Brand discoverability test:** submit goldenhomeproject.com to free directories (DMOZ-likes, niche home-improvement directories). Tiny backlink boost; takes <30 min total.

## Done

- [done 2026-05-06 ccf0426] Add Product+Review+Person schema to all 8 COVER posts. Matches #1 SERP (Good Housekeeping) machine-readable signal stack.
- [done 2026-05-05 a91dd47] Submit sitemap.xml + robots.txt to GSC. 9 URLs discovered.
- [done 2026-05-05 803b7e4] GSC ownership verification (HTML file method).
