"""
Stage: Conversation Intelligence + Recovery. Implements the `respond()` contract
(challenge-brief.md §7.4) and backs POST /v1/reply. Decides one of three actions:
send / wait / end — never a fourth option, per the testing-brief contract.

Directly targets the two named failure modes:
  - Pattern B (auto-reply): try once to reach a human, then exit gracefully
    rather than burning turns (challenge-brief.md §3.1, §9 Pattern B).
  - Pattern D (intent handoff): explicit join/accept intent routes straight to
    action, never back to another qualifying question (§9 Pattern D).
Also handles hostility and off-topic curveballs by staying politely on-mission
(challenge-testing-brief.md Phase 4, scenario 3).
"""
from __future__ import annotations

from typing import Any

from engine.conversation.detection import detect_intent, detect_language, is_auto_reply, is_hostile, is_off_topic
from engine.conversation.state import ConversationState

MAX_TURNS = 5


def respond(state: ConversationState, merchant_message: str, from_role: str = "merchant") -> dict[str, Any]:
    prior_bodies = state.merchant_bodies()
    state.add_turn(from_role, merchant_message)

    if len(state.turns) >= MAX_TURNS * 2:
        state.ended = True
        return {"action": "end", "rationale": f"reached max conversation depth ({MAX_TURNS} turns); exiting gracefully"}

    if is_auto_reply(merchant_message, prior_bodies):
        if state.auto_reply_attempts == 0:
            state.auto_reply_attempts += 1
            body = "Samajh gayi — this reads like an auto-reply. If you're the owner/manager, a 2-minute reply saves a follow-up call. Chalega?"
            state.add_turn("vera", body)
            return {"action": "send", "body": body, "cta": "binary",
                    "rationale": "auto-reply detected (verbatim/canned phrasing); attempting one direct human handoff before exiting"}
        state.ended = True
        return {"action": "end",
                "rationale": "auto-reply detected a second time; stopping turn-burn and exiting gracefully per anti-auto-reply-pollution rule"}

    if is_hostile(merchant_message):
        state.hostile_strikes += 1
        if state.hostile_strikes >= 2:
            state.ended = True
            return {"action": "end", "rationale": "repeated hostility; disengaging"}
        body = "No worries, I'll stay on the original topic — happy to help whenever you're ready."
        state.add_turn("vera", body)
        return {"action": "send", "body": body, "cta": "none",
                "rationale": "hostile message detected; de-escalating without engaging, staying on-mission"}

    if is_off_topic(merchant_message):
        body = "That's outside what I can help with here, but happy to keep going on your profile/growth question whenever you like."
        state.add_turn("vera", body)
        return {"action": "send", "body": body, "cta": "none",
                "rationale": "off-topic request detected; politely declined and redirected to original mission"}

    intent = detect_intent(merchant_message)

    if intent == "reject":
        state.ended = True
        return {"action": "end", "rationale": "merchant signaled not-interested/stop; exiting gracefully, no further nudges"}

    if intent in ("join", "accept"):
        body = "Great — starting that now, no more questions needed. I'll confirm here once it's done."
        state.add_turn("vera", body)
        return {"action": "send", "body": body, "cta": "none",
                "rationale": f"explicit '{intent}' intent detected; routing directly to action instead of re-qualifying (avoids Pattern-D failure)"}

    if intent == "question":
        body = "Good question — let me get you a precise answer rather than guessing. In the meantime, want me to go ahead with what we discussed?"
        state.add_turn("vera", body)
        return {"action": "send", "body": body, "cta": "binary",
                "rationale": "merchant asked a question; acknowledged honestly, kept a single binary CTA moving forward"}

    language = detect_language(merchant_message)
    body = "Got it — here's the next step whenever you're ready. Reply YES to proceed."
    state.add_turn("vera", body)
    return {"action": "send", "body": body, "cta": "binary",
            "rationale": f"no strong signal detected (language={language}); advancing with a low-friction single CTA"}
