"""
Thin accessor wrappers over the raw context dicts defined in challenge-brief.md §4.

Inputs to compose() arrive as plain dicts (loaded from dataset JSON, or pushed via
POST /v1/context). We don't deserialize into strict schemas because the judge's
post-submission context injection (challenge-testing-brief.md §Phase 3) can add
fields we've never seen. Wrapping with .get()-based accessors keeps us tolerant of
that without ever inventing data that isn't present (AGENTS: "don't fabricate").
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional


class _DictView:
    """Read-only convenience wrapper: attribute-ish access over a raw dict, safe on missing keys."""

    def __init__(self, raw: dict[str, Any] | None):
        self.raw = raw or {}

    def get(self, path: str, default: Any = None) -> Any:
        node: Any = self.raw
        for part in path.split("."):
            if not isinstance(node, dict) or part not in node:
                return default
            node = node[part]
        return node if node is not None else default

    def __bool__(self) -> bool:
        return bool(self.raw)


class Category(_DictView):
    @property
    def slug(self) -> str:
        return self.get("slug", "")

    @property
    def voice(self) -> dict:
        return self.get("voice", {}) or {}

    @property
    def offer_catalog(self) -> list[dict]:
        return self.get("offer_catalog", []) or []

    @property
    def peer_stats(self) -> dict:
        return self.get("peer_stats", {}) or {}

    @property
    def digest(self) -> list[dict]:
        return self.get("digest", []) or []

    def digest_item(self, item_id: str) -> Optional[dict]:
        for item in self.digest:
            if item.get("id") == item_id:
                return item
        return None

    @property
    def seasonal_beats(self) -> list[dict]:
        return self.get("seasonal_beats", []) or []

    @property
    def trend_signals(self) -> list[dict]:
        return self.get("trend_signals", []) or []

    @property
    def patient_content_library(self) -> list[dict]:
        return self.get("patient_content_library", []) or []


class Merchant(_DictView):
    @property
    def merchant_id(self) -> str:
        return self.get("merchant_id", "")

    @property
    def category_slug(self) -> str:
        return self.get("category_slug", "")

    @property
    def name(self) -> str:
        return self.get("identity.name", "there")

    @property
    def first_name(self) -> str:
        return self.get("identity.owner_first_name") or self.name.split()[0]

    @property
    def languages(self) -> list[str]:
        return self.get("identity.languages", ["en"]) or ["en"]

    @property
    def wants_hindi_mix(self) -> bool:
        return "hi" in self.languages

    @property
    def signals(self) -> list[str]:
        return self.get("signals", []) or []

    @property
    def performance(self) -> dict:
        return self.get("performance", {}) or {}

    @property
    def conversation_history(self) -> list[dict]:
        return self.get("conversation_history", []) or []

    @property
    def offers(self) -> list[dict]:
        return self.get("offers", []) or []

    def active_offers(self) -> list[dict]:
        return [o for o in self.offers if o.get("status") == "active"]

    @property
    def customer_aggregate(self) -> dict:
        return self.get("customer_aggregate", {}) or {}

    @property
    def review_themes(self) -> list[dict]:
        return self.get("review_themes", []) or []


class Trigger(_DictView):
    @property
    def id(self) -> str:
        return self.get("id", "")

    @property
    def kind(self) -> str:
        return self.get("kind", "")

    @property
    def scope(self) -> str:
        return self.get("scope", "merchant")

    @property
    def source(self) -> str:
        return self.get("source", "internal")

    @property
    def payload(self) -> dict:
        return self.get("payload", {}) or {}

    @property
    def urgency(self) -> int:
        return int(self.get("urgency", 1) or 1)

    @property
    def suppression_key(self) -> str:
        return self.get("suppression_key", self.id)


class Customer(_DictView):
    @property
    def customer_id(self) -> str:
        return self.get("customer_id", "")

    @property
    def name(self) -> str:
        return self.get("identity.name", "there")

    @property
    def language_pref(self) -> str:
        return self.get("identity.language_pref", "en")

    @property
    def wants_hindi_mix(self) -> bool:
        return "hi" in self.language_pref.lower()

    @property
    def state(self) -> str:
        return self.get("state", "active")

    @property
    def relationship(self) -> dict:
        return self.get("relationship", {}) or {}

    @property
    def preferences(self) -> dict:
        return self.get("preferences", {}) or {}


@dataclass
class Fact:
    """A single verifiable anchor pulled from context — the atomic unit of specificity."""
    text: str
    source: str = ""


@dataclass
class FactBundle:
    """Output of Stage 6 (opportunity detection) for one (merchant, trigger) pair."""
    opportunity_type: str          # e.g. "research_hook", "loss_aversion", "milestone_celebration"
    primary_fact: Fact
    secondary_facts: list[Fact] = field(default_factory=list)
    suggested_cta_kind: str = "open_ended"   # "binary" | "open_ended" | "none"
    reasoning: list[str] = field(default_factory=list)  # internal-only, never shown to merchant


@dataclass
class Candidate:
    body: str
    cta: str
    rationale: str
    send_as: str = "vera"


@dataclass
class ScoreCard:
    specificity: float
    category_fit: float
    merchant_fit: float
    trigger_relevance: float
    engagement: float

    @property
    def total(self) -> float:
        return (
            self.specificity
            + self.category_fit
            + self.merchant_fit
            + self.trigger_relevance
            + self.engagement
        )
