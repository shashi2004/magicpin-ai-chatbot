"""In-memory per-conversation state. Persisted only for the lifetime of the test
window (challenge-testing-brief.md §11: wipe on /v1/teardown)."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class ConversationState:
    conversation_id: str
    merchant_id: str
    customer_id: Optional[str] = None
    trigger_id: Optional[str] = None
    turns: list[dict] = field(default_factory=list)          # [{"from": "vera"|"merchant", "body": str}]
    auto_reply_attempts: int = 0
    hostile_strikes: int = 0
    ended: bool = False

    def add_turn(self, from_role: str, body: str) -> None:
        self.turns.append({"from": from_role, "body": body})

    def merchant_bodies(self) -> list[str]:
        return [t["body"] for t in self.turns if t["from"] in ("merchant", "customer")]

    def bot_bodies(self) -> list[str]:
        return [t["body"] for t in self.turns if t["from"] in ("vera", "merchant_on_behalf", "bot")]


class ConversationStore:
    def __init__(self) -> None:
        self._states: dict[str, ConversationState] = {}

    def get_or_create(self, conversation_id: str, merchant_id: str, customer_id: Optional[str] = None,
                       trigger_id: Optional[str] = None) -> ConversationState:
        if conversation_id not in self._states:
            self._states[conversation_id] = ConversationState(
                conversation_id=conversation_id, merchant_id=merchant_id,
                customer_id=customer_id, trigger_id=trigger_id,
            )
        return self._states[conversation_id]

    def get(self, conversation_id: str) -> Optional[ConversationState]:
        return self._states.get(conversation_id)

    def clear(self) -> None:
        self._states.clear()
