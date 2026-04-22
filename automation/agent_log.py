"""Shared helper for appending to AGENT_LOG.md and committing.

Every GHP agent (cloud workflow OR web routine) calls this at end of run
to record what it did in the shared action journal.

Usage as library (from Python):

    from agent_log import append_log_entry
    append_log_entry(
        agent="Content Engine",
        ran="Generated 3 Reel scripts, all passed quality gate",
        changed="automation/scripts/reel-2026-04-21-*.json, social/post_queue.json",
        external="none",
        hint="Reel Producer should render 3 new MP4s at 07:00 UTC",
    )

Usage as CLI (from a workflow yaml or bash):

    python automation/agent_log.py \\
      --agent "Trend Scout" \\
      --ran "Scanned Reddit r/homegoods + r/organization, found 12 opportunities" \\
      --changed "automation/trends/2026-04-21.json" \\
      --external "none" \\
      --hint "Content Engine can pick top 3 for today's Reels"

The helper is idempotent: if AGENT_LOG.md already has today's entry for
this agent, it appends another one (multiple runs per day are allowed and
sometimes necessary).

Commit + push is performed here too, so callers don't have to. In cloud
(GitHub Actions) this uses git + GITHUB_TOKEN. In Claude Code web sandbox
this will fail `git push`, which is expected — the caller is then supposed
to use the GitHub MCP `push_files` tool to commit instead.
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LOG_PATH = ROOT / "AGENT_LOG.md"


def _now_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def append_log_entry(
    agent: str,
    ran: str,
    changed: str = "none",
    external: str = "none",
    hint: str = "",
    commit: bool = True,
) -> None:
    """Append one protocol entry to AGENT_LOG.md. Optionally commit + push.

    Follows the exact format specified in BUSINESS_BRAIN.md's
    AGENT COORDINATION PROTOCOL section.
    """
    ts = _now_utc()
    entry = (
        f"\n## {ts} — {agent}\n"
        f"**Ran:** {ran.strip()}\n"
        f"**Changed:** {changed.strip()}\n"
        f"**External actions:** {external.strip()}\n"
        f"**Next agent hint:** {hint.strip() or '(no hint)'}\n"
    )

    if not LOG_PATH.exists():
        # Initialize if missing (shouldn't happen in practice)
        LOG_PATH.write_text(
            "# Golden Home Project — Shared Agent Log\n\n"
            "Append-only journal. Every agent reads last ~50 entries at start,\n"
            "appends one entry at end. See BUSINESS_BRAIN.md for the protocol.\n\n"
            "---\n"
        )

    with LOG_PATH.open("a") as f:
        f.write(entry)

    if not commit:
        return

    # Cloud commit path — only if we're in a git repo with push creds.
    try:
        subprocess.run(
            ["git", "-C", str(ROOT), "add", str(LOG_PATH)],
            check=True, capture_output=True,
        )
        date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        subprocess.run(
            ["git", "-C", str(ROOT), "commit", "-m", f"Agent log: {agent} {date_str}"],
            check=True, capture_output=True,
        )
        subprocess.run(
            ["git", "-C", str(ROOT), "push", "origin", "main"],
            check=True, capture_output=True, timeout=30,
        )
        print(f"[agent-log] Pushed entry for {agent}", file=sys.stderr)
    except subprocess.CalledProcessError as e:
        # Not fatal — the log file was still appended locally.
        stderr = (e.stderr or b"").decode("utf-8", errors="replace")[:300]
        print(f"[agent-log] Git step failed (entry still appended locally): {stderr}",
              file=sys.stderr)
    except subprocess.TimeoutExpired:
        print("[agent-log] git push timed out (entry still appended locally)",
              file=sys.stderr)
    except FileNotFoundError:
        print("[agent-log] git not available (skipping commit)", file=sys.stderr)


def _cli() -> None:
    ap = argparse.ArgumentParser(description="Append an AGENT_LOG.md entry")
    ap.add_argument("--agent", required=True)
    ap.add_argument("--ran", required=True)
    ap.add_argument("--changed", default="none")
    ap.add_argument("--external", default="none")
    ap.add_argument("--hint", default="")
    ap.add_argument("--no-commit", action="store_true",
                    help="Skip git commit + push (useful for local testing)")
    args = ap.parse_args()

    append_log_entry(
        agent=args.agent,
        ran=args.ran,
        changed=args.changed,
        external=args.external,
        hint=args.hint,
        commit=not args.no_commit,
    )


if __name__ == "__main__":
    _cli()
