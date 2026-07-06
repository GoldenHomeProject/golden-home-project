"""Shared Claude helper — uses the Claude Code CLI (subscription auth), NOT API tokens.

All agents import this. The CLI is installed by each workflow via:
    npm install -g @anthropic-ai/claude-code
and authenticates via CLAUDE_CODE_OAUTH_TOKEN env var (generated locally via
`claude setup-token` and pasted into GitHub Secrets).

Why CLI, not API:
- Uses your Max subscription — no per-token billing
- Same model access, same quality
- Subject to subscription usage windows (5-hour rolling caps)

Usage:
    from _claude_api import call_claude, call_claude_json
    text = call_claude("Write a 5-word slogan.")
    data = call_claude_json(prompt, system=SYSTEM_PROMPT)
"""
import json
import os
import re
import subprocess
import time


DEFAULT_TIMEOUT = 300  # 5 min — long-form blog posts can run long


def _check_auth():
    # GitHub Actions authenticates the CLI via the CLAUDE_CODE_OAUTH_TOKEN secret.
    # On the Pi (and local dev) the CLI is already logged in via stored
    # subscription credentials (~/.claude/.credentials.json) — no env token
    # needed there. Accept either so the same code runs in both places.
    if os.environ.get("CLAUDE_CODE_OAUTH_TOKEN"):
        return
    if os.path.exists(os.path.expanduser("~/.claude/.credentials.json")):
        return
    raise RuntimeError(
        "No Claude auth: set CLAUDE_CODE_OAUTH_TOKEN (CI) or log in the CLI "
        "via `claude setup-token` / `claude login` (local/Pi)."
    )


def call_claude(prompt: str, *, system: str | None = None,
                timeout: int = DEFAULT_TIMEOUT, retries: int = 3,
                max_tokens: int | None = None,
                max_turns: int | None = None) -> str:
    """Shell out to `claude --print`. Prompt via stdin to handle any content.

    Retries on transient subscription-limit errors. Raises on permanent failures.
    `max_tokens` is accepted for backward compat with the old API helper but
    ignored — the CLI decides length based on the model's default.
    `max_turns` caps the agentic-loop iterations. Pass max_turns=1 for pure
    one-shot text/JSON generation (skips tool-use loops, much faster).
    """
    _ = max_tokens  # accepted for backward compat, not applicable to the CLI
    _check_auth()

    cmd = ["claude", "--print"]
    if max_turns is not None:
        cmd += ["--max-turns", str(max_turns)]
    if system:
        cmd += ["--append-system-prompt", system]

    last_err = None
    for attempt in range(retries):
        try:
            result = subprocess.run(
                cmd,
                input=prompt,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
            if result.returncode == 0:
                return result.stdout.strip()

            err = (result.stderr or result.stdout or "").strip()
            last_err = err
            # Retry on transient: rate-limit-ish phrases, network hiccups.
            if any(tok in err.lower() for tok in [
                "rate limit", "usage limit", "timeout", "temporarily",
                "connection", "retry", "max turns",
            ]):
                time.sleep(2 ** attempt * 2)
                continue
            raise RuntimeError(f"claude CLI failed (rc={result.returncode}): {err[:500]}")

        except subprocess.TimeoutExpired:
            last_err = f"timeout after {timeout}s"
            time.sleep(2 ** attempt)
        except FileNotFoundError:
            raise RuntimeError(
                "`claude` CLI not found in PATH. Install via: npm install -g @anthropic-ai/claude-code"
            )

    raise RuntimeError(f"claude CLI failed after {retries} retries: {last_err}")


def call_claude_json(prompt: str, **kwargs) -> dict | list:
    """Extract the first valid JSON block from Claude's response.

    The CLI does not force JSON mode, so we ask in the prompt + parse defensively.
    Handles both ```json fences and bare JSON.
    """
    # Nudge the model toward clean JSON — belt and suspenders
    suffix = "\n\nRespond with ONLY valid JSON. No prose before or after. No markdown fences."
    raw = call_claude(prompt.rstrip() + suffix, **kwargs)

    # Strip fences if present
    fence_match = re.search(r"```(?:json)?\s*\n(.*?)\n```", raw, re.DOTALL)
    candidate = fence_match.group(1) if fence_match else raw

    # Find first JSON-ish opener
    opener_positions = [p for p in (candidate.find("{"), candidate.find("[")) if p >= 0]
    if not opener_positions:
        raise ValueError(f"No JSON found in response: {raw[:200]}")
    start = min(opener_positions)
    candidate = candidate[start:]

    # Try progressively shorter suffixes until one parses
    for end in range(len(candidate), 0, -1):
        try:
            return json.loads(candidate[:end])
        except json.JSONDecodeError:
            continue
    raise ValueError(f"Could not parse JSON from: {raw[:300]}")
