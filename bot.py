"""
Static submission entrypoint (challenge-brief.md §7.1). Thin re-export: all the
actual reasoning lives in engine/reasoning/composer.py so the same code path backs
both this static function and the live HTTP harness (engine/api/server.py).
"""
from __future__ import annotations

from typing import Optional

from engine.reasoning.composer import compose as _compose


def compose(category: dict, merchant: dict, trigger: dict, customer: Optional[dict] = None) -> dict:
    """Deterministic (temperature=0 if an LLM is configured; pure rule-based otherwise).
    Completes well under 30s per call — no network I/O unless ANTHROPIC_API_KEY or
    OPENAI_API_KEY is set for the optional polish stage."""
    return _compose(category, merchant, trigger, customer)
