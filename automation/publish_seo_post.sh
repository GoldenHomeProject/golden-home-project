#!/bin/bash
# publish_seo_post.sh — generate the day's search-demand post AND publish it.
#
# The 07:15 cron used to call blog_writer.py directly, which only WRITES files. The
# GitHub Actions workflow it replaced had a commit step; the cron did not. Result:
# five keyword-targeted posts (08-01..08-06) sat untracked on the Pi, returned 404 on
# the live site, and the sitemap advertised those 404s to Google — which is a terrible
# signal for a site already showing "Discovered - currently not indexed".
#
# Generation without publication is worthless, so the two live in one script.
set -euo pipefail
cd "$HOME/golden-home-project"

set -a; . "$HOME/.ghp-secrets/claude.env"; set +a
/usr/bin/python3 automation/blog_writer.py

# .md files feed the repurpose agent; index.html gets the new card.
git add blog/posts/*.html blog/posts/*.md blog/index.html social/keyword_queue.json 2>/dev/null || true
if git diff --staged --quiet; then
  echo "[seo] nothing new to publish"
  exit 0
fi

git -c user.name="GHP SEO Bot" -c user.email="goldenhomeprojectllc@gmail.com" \
    commit -q -m "seo: search-demand post $(date -u +%Y-%m-%d)"
for i in 1 2 3 4 5; do
  if git -c rebase.autoStash=true pull --rebase --quiet origin main \
     && git push --quiet origin main; then
    echo "[seo] published"
    exit 0
  fi
  sleep 5
done
echo "[seo] PUSH FAILED — post committed locally only"
exit 1
