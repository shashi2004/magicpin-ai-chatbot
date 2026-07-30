"""
Stage 1 (Understand Merchant) + Stage 4 (Understand Conversation History) + Stage 5 (Find Merchant Goal).

Builds a compact "mental model" the rest of the pipeline reasons over, instead of
re-deriving engagement state ad hoc in every template. Kept deliberately small:
only the facts that change downstream decisions (voice, CTA shape, whether to
re-introduce ourselves, whether the merchant already signaled intent/rejection).
"""
from __future__ import annotations

from dataclasses import dataclass, field

from engine.conversation.detection import detect_intent, is_auto_reply
from engine.models import Merchant


@dataclass
class MerchantMentalModel:
    merchant_id: str
    prefers_hindi_mix: bool
    is_new_conversation: bool          # no history yet -> must use template/first-touch framing
    last_engagement: str               # "merchant_replied" | "no_reply" | "intent_action" | "none"
    recent_intent: str                 # "join"/"accept"/"reject"/"question"/"none" from most recent merchant turn
    auto_reply_suspected: bool
    ranked_signals: list[str] = field(default_factory=list)
    top_priority_signal: str = ""


_SIGNAL_PRIORITY = {
    "engaged_in_last_48h": 5,
    "high_risk_adult_cohort": 4,
    "ctr_below_peer_median": 4,
    "stale_posts": 3,
    "dormant": 2,
}


def _rank_signals(signals: list[str]) -> list[str]:
    def score(sig: str) -> int:
        base = sig.split(":")[0]
        return _SIGNAL_PRIORITY.get(base, 1)
    return sorted(signals, key=score, reverse=True)


def build(merchant: Merchant) -> MerchantMentalModel:
    history = merchant.conversation_history
    last_merchant_turn = next((t for t in reversed(history) if t.get("from") == "merchant"), None)
    last_turn = history[-1] if history else None

    auto_reply = False
    recent_intent = "none"
    if last_merchant_turn:
        prior_bodies = [t.get("body", "") for t in history if t.get("from") == "merchant"]
        auto_reply = is_auto_reply(last_merchant_turn.get("body", ""), prior_bodies[:-1])
        recent_intent = detect_intent(last_merchant_turn.get("body", ""))

    last_engagement = (last_turn or {}).get("engagement", "none")

    ranked = _rank_signals(merchant.signals)
    return MerchantMentalModel(
        merchant_id=merchant.merchant_id,
        prefers_hindi_mix=merchant.wants_hindi_mix,
        is_new_conversation=len(history) == 0,
        last_engagement=last_engagement,
        recent_intent=recent_intent,
        auto_reply_suspected=auto_reply,
        ranked_signals=ranked,
        top_priority_signal=ranked[0] if ranked else "",
    )
