"""Shared Anthropic API helper for all GHP agents.

Keeps every agent DRY: same retry logic, same model, same JSON extraction.
Runs headless in GitHub Actions — no Claude CLI dependency.

Usage:
    from _claude_api import call_claude, call_claude_json
    text = call_claude("Write a 5-word slogan.")
    data = call_claude_json(prompt, schema_hint="...", max_tokens=4096)
"""
import json
import os
import re
import time
import urllib.error
import urllib.request

API_URL = "https://api.anthropic.com/v1/messages"
DEFAULT_MODEL = "claude-sonnet-4-6"  # fast + cheap + smart enough for content
DEFAULT_MAX_TOKENS = 4096


def _get_key() -> str:
    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        raise RuntimeError("ANTHROPIC_API_KEY not set")
    return key


def call_claude(prompt: str, *, model: str = DEFAULT_MODEL,
                max_tokens: int = DEFAULT_MAX_TOKENS,
                system: str | None = None,
                retries: int = 3) -> str:
    """Single-turn message → raw text response."""
    headers = {
        "x-api-key": _get_key(),
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
    }
    body: dict = {
        "model": model,
        "max_tokens": max_tokens,
        "messages": [{"role": "user", "content": prompt}],
    }
    if system:
        body["system"] = system

    last_err = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(
                API_URL,
                data=json.dumps(body).encode("utf-8"),
                headers=headers,
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=120) as resp:
                data = json.loads(resp.read())
            return data["content"][0]["text"]
        except urllib.error.HTTPError as e:
            last_err = f"HTTP {e.code}: {e.read().decode('utf-8', errors='replace')[:500]}"
            # 429 / 529 → back off. Everything else → fail fast.
            if e.code in (429, 529, 500, 502, 503):
                time.sleep(2 ** attempt * 2)
                continue
            raise RuntimeError(last_err) from e
        except Exception as e:
            last_err = str(e)
            time.sleep(2 ** attempt)
    raise RuntimeError(f"Claude API failed after {retries} retries: {last_err}")


def call_claude_json(prompt: str, **kwargs) -> dict | list:
    """Wraps call_claude and extracts the first valid JSON block from the response.

    Claude sometimes wraps JSON in ```json fences or adds preamble — handle both.
    """
    raw = call_claude(prompt, **kwargs)

    # Try fenced first
    fence_match = re.search(r"```(?:json)?\s*\n(.*?)\n```", raw, re.DOTALL)
    if fence_match:
        candidate = fence_match.group(1)
    else:
        # Find first { or [ and last matching close
        start = min(
            (i for i in [raw.find("{"), raw.find("[")] if i >= 0),
            default=-1,
        )
        if start < 0:
            raise ValueError(f"No JSON found in response: {raw[:200]}")
        # Greedy — rely on json.loads to reject bad endings
        candidate = raw[start:]

    # Try progressively shorter suffixes until one parses
    for end in range(len(candidate), 0, -1):
        try:
            return json.loads(candidate[:end])
        except json.JSONDecodeError:
            continue
    raise ValueError(f"Could not parse JSON from: {raw[:300]}")
