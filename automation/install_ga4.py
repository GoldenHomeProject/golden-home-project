"""Install the GA4 tag on every page.

Until now the site had no analytics of any kind. We could see Amazon clicks (only the
ones that left for Amazon) and Search Console impressions, but nothing about the site
itself — not how many people arrived, not which page they landed on, not whether they
clicked through. That blindness is why the Aug 13 spike is still ambiguous: 188 Amazon
clicks, and no way to tell whether that was 188 people or 30 people clicking six
products each.

GA4's enhanced measurement includes outbound-click tracking, which is the specific
thing we need: it records clicks leaving for amazon.com, per landing page. Combined
with the ascsubtag already on every affiliate link, that finally closes the loop
between "a pin was seen" and "someone clicked buy".

Idempotent: re-running will not double-tag a page, and Google warns explicitly against
more than one tag per page.
"""
from pathlib import Path

ROOT = Path("/home/ianmcwherter/golden-home-project")
GA_ID = "G-6X9B8NJYM7"

SNIPPET = f"""<!-- Google tag (gtag.js) -->
<script async src="https://www.googletagmanager.com/gtag/js?id={GA_ID}"></script>
<script>
  window.dataLayer = window.dataLayer || [];
  function gtag(){{dataLayer.push(arguments);}}
  gtag('js', new Date());
  gtag('config', '{GA_ID}');
</script>
"""

SKIP_DIRS = {".git", "node_modules", "_superseded", "__pycache__"}


def main() -> int:
    tagged = skipped_already = no_head = 0
    for html in sorted(ROOT.rglob("*.html")):
        if any(part in SKIP_DIRS for part in html.parts):
            continue
        text = html.read_text(errors="ignore")
        if GA_ID in text:
            skipped_already += 1
            continue
        low = text.lower()
        i = low.find("<head>")
        if i == -1:
            # Some generated pages use <head attr> or omit it entirely.
            i = low.find("<head")
            if i == -1:
                no_head += 1
                print(f"  NO <head>, skipped: {html.relative_to(ROOT)}")
                continue
            i = low.find(">", i)
            if i == -1:
                no_head += 1
                continue
            insert_at = i + 1
        else:
            insert_at = i + len("<head>")
        html.write_text(text[:insert_at] + "\n" + SNIPPET + text[insert_at:])
        tagged += 1

    print(f"[ga4] tagged {tagged} page(s); {skipped_already} already had it; "
          f"{no_head} had no <head>")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
