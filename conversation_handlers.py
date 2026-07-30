"""Optional multi-turn entrypoint (challenge-brief.md §7.4)."""
from __future__ import annotations

from engine.conversation.handler import respond as _respond
from engine.conversation.state import ConversationState


def respond(state: ConversationState, merchant_message: str) -> dict:
    """Given the conversation so far + the merchant's latest message, produce the reply."""
    return _respond(state, merchant_message)
