"""
Optional polish stage (Rewrite). The deterministic template renderer already
produces a fact-anchored, category-correct, rubric-scored message — this stage
exists only to make the prose read less templated when an LLM key is available.

Design constraints that make this safe to bolt onto a deterministic pipeline:
  - temperature=0, so identical inputs still produce identical outputs.
  - The prompt forbids introducing any number, date, name, or claim not already
    present in the draft (no new facts = no new hallucinations).
  - The rewrite is re-scored by the same evaluator as the template candidates;
    if it scores lower or drops a numeric anchor the draft had, we keep the
    draft. The LLM can only make things better, never worse or riskier.

No key configured -> `polish()` is a no-op passthrough. This keeps the bot fully
functional (and fully deterministic) with zero external dependencies — every
call here is plain `urllib`, no `openai`/`anthropic` SDK required.
"""
from __future__ import annotations

import json
import os
import re
from urllib import error as urlerror
from urllib import request as urlrequest

_TIMEOUT = 15  # compose() has a hard 30s budget (testing-brief §5); leave headroom for the rest of the pipeline

_SYSTEM_PROMPT = (
    "You are polishing a WhatsApp business message for a merchant AI assistant. "
    "Rewrite ONLY for tone and flow. Do not add, remove, or change any number, "
    "date, price, name, percentage, or citation that appears in the draft. Do not "
    "add new facts, offers, or claims. Do not add a greeting if the draft has none. "
    "Keep it concise. Keep exactly one call-to-action. Return only the rewritten "
    "message body, nothing else."
)


def _post_json(url: str, headers: dict, body: dict) -> dict:
    req = urlrequest.Request(url, data=json.dumps(body).encode("utf-8"), headers=headers, method="POST")
    with urlrequest.urlopen(req, timeout=_TIMEOUT) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _openai_compatible_complete(draft: str, base_url: str, api_key: str, model: str) -> str | None:
    try:
        data = _post_json(
            f"{base_url.rstrip('/')}/chat/completions",
            {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            {
                "model": model,
                "temperature": 0,
                "max_tokens": 400,
                "messages": [
                    {"role": "system", "content": _SYSTEM_PROMPT},
                    {"role": "user", "content": draft},
                ],
            },
        )
        return (data["choices"][0]["message"]["content"] or "").strip() or None
    except (urlerror.URLError, KeyError, IndexError, ValueError, TimeoutError):
        return None


def _anthropic_complete(draft: str, api_key: str, model: str) -> str | None:
    try:
        data = _post_json(
            "https://api.anthropic.com/v1/messages",
            {"x-api-key": api_key, "Content-Type": "application/json", "anthropic-version": "2023-06-01"},
            {
                "model": model,
                "max_tokens": 400,
                "temperature": 0,
                "system": _SYSTEM_PROMPT,
                "messages": [{"role": "user", "content": draft}],
            },
        )
        return "".join(b.get("text", "") for b in data.get("content", [])).strip() or None
    except (urlerror.URLError, KeyError, IndexError, ValueError, TimeoutError):
        return None


def _numeric_anchors(text: str) -> set[str]:
    return set(re.findall(r"\d[\d.,%₹]*", text or ""))


def available() -> bool:
    return bool(
        os.environ.get("ANTHROPIC_API_KEY")
        or os.environ.get("OPENAI_API_KEY")
        or os.environ.get("NVIDIA_API_KEY")
    )


def polish(draft: str) -> str | None:
    """Returns a polished draft, or None if no LLM is configured / the call fails."""
    if not draft:
        return None

    if key := os.environ.get("ANTHROPIC_API_KEY"):
        return _anthropic_complete(draft, key, os.environ.get("ANTHROPIC_MODEL", "claude-opus-4-5"))

    if key := os.environ.get("NVIDIA_API_KEY"):
        return _openai_compatible_complete(
            draft, "https://integrate.api.nvidia.com/v1", key,
            os.environ.get("NVIDIA_MODEL", "meta/llama-3.1-70b-instruct"),
        )

    if key := os.environ.get("OPENAI_API_KEY"):
        return _openai_compatible_complete(
            draft, os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1"), key,
            os.environ.get("OPENAI_MODEL", "gpt-4o-mini"),
        )

    return None


def safe_polish(draft: str) -> tuple[str, bool]:
    """Polish, but only accept the rewrite if it preserves every numeric anchor
    in the draft (guards against the rewrite silently dropping a number/date).
    Returns (final_text, was_polished)."""
    polished = polish(draft)
    if not polished:
        return draft, False
    if _numeric_anchors(draft) - _numeric_anchors(polished):
        return draft, False  # rewrite dropped an anchor -> reject, keep deterministic draft
    return polished, True
