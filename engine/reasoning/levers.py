"""
Stage 7 (Predict Best Next Action): map an opportunity_type to the compulsion
levers (challenge-brief.md §10) most likely to drive a reply. Production Vera's
biggest miss is social proof (#3) and asking-the-merchant (#7) — we bias toward
those wherever the fact bundle supports them.
"""
from __future__ import annotations

# opportunity_type -> ordered lever names (first is primary)
LEVER_MAP: dict[str, list[str]] = {
    "research_hook": ["specificity", "curiosity", "effort_externalization"],
    "compliance_alert": ["loss_aversion", "specificity", "single_binary"],
    "cde_invite": ["specificity", "curiosity"],
    "seasonal_prep": ["effort_externalization", "specificity", "single_binary"],
    "occasion_spike": ["specificity", "single_binary"],
    "performance_win": ["social_proof", "reciprocity"],
    "loss_aversion": ["loss_aversion", "specificity", "single_binary"],
    "milestone_celebration": ["social_proof", "curiosity"],
    "milestone_push": ["loss_aversion", "single_binary"],
    "social_listening": ["reciprocity", "asking_the_merchant"],
    "competitive_pressure": ["loss_aversion", "specificity", "single_binary"],
    "re_engagement": ["asking_the_merchant", "curiosity"],
    "ask_the_merchant": ["asking_the_merchant"],
    "intent_handoff": ["effort_externalization", "single_binary"],
    "recall_reminder": ["specificity", "effort_externalization", "single_binary"],
    "appointment_reminder": ["specificity", "single_binary"],
    "customer_recovery": ["loss_aversion", "reciprocity", "single_binary"],
    "trial_conversion": ["specificity", "single_binary"],
    "generic_nudge": ["specificity"],
}


def levers_for(opportunity_type: str) -> list[str]:
    return LEVER_MAP.get(opportunity_type, ["specificity"])
