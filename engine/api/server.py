"""
The 5 HTTP endpoints from challenge-testing-brief.md §2. This is the actual
judge-facing surface: everything in bot/reasoning and bot/conversation is
wired together here, but this file itself stays thin — routing + persistence
only, no business logic.
"""
from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import FastAPI
from pydantic import BaseModel

from engine.api.store import ContextStore
from engine.conversation.handler import respond as conversation_respond
from engine.conversation.state import ConversationStore
from engine.reasoning.composer import compose

app = FastAPI(title="Vera-class Merchant AI Assistant")

_START = time.time()
_METADATA = {
    "team_name": "Solo",
    "team_members": ["Abhishek"],
    "model": "template-first deterministic composer + optional LLM polish (temperature=0)",
    "approach": "Multi-stage reasoning engine: fact extraction per trigger kind -> "
                "merchant mental model -> compulsion-lever selection -> templated "
                "candidate generation -> heuristic self-evaluation against the 5-dim "
                "rubric -> optional anchor-preserving LLM rewrite -> best candidate.",
    "contact_email": "",
    "version": "1.0.0",
    "submitted_at": datetime.now(timezone.utc).isoformat(),
}

contexts = ContextStore()
conversations = ConversationStore()
_fired_suppression_keys: set[str] = set()
_next_conv_seq = 0


def _next_conversation_id(merchant_id: str, trigger_id: str) -> str:
    global _next_conv_seq
    _next_conv_seq += 1
    return f"conv_{merchant_id}_{trigger_id}_{_next_conv_seq}"


class ContextPush(BaseModel):
    scope: str
    context_id: str
    version: int
    payload: dict[str, Any]
    delivered_at: str


@app.post("/v1/context")
async def push_context(body: ContextPush):
    accepted, current_version = contexts.push(body.scope, body.context_id, body.version, body.payload)
    if not accepted:
        return {"accepted": False, "reason": "stale_version", "current_version": current_version}
    return {"accepted": True, "ack_id": f"ack_{body.context_id}_v{body.version}",
            "stored_at": datetime.now(timezone.utc).isoformat()}


class TickBody(BaseModel):
    now: str
    available_triggers: list[str] = []


@app.post("/v1/tick")
async def tick(body: TickBody):
    actions: list[dict[str, Any]] = []
    for trg_id in body.available_triggers[:20]:
        trigger_payload = contexts.get("trigger", trg_id)
        if not trigger_payload:
            continue
        suppression_key = trigger_payload.get("suppression_key", trg_id)
        if suppression_key in _fired_suppression_keys:
            continue  # already sent this trigger's message; restraint over spam

        merchant_id = trigger_payload.get("merchant_id")
        merchant_payload = contexts.get("merchant", merchant_id) if merchant_id else None
        if not merchant_payload:
            continue
        category_slug = merchant_payload.get("category_slug")
        category_payload = contexts.get("category", category_slug) if category_slug else None
        if not category_payload:
            continue

        customer_id = trigger_payload.get("customer_id")
        customer_payload = contexts.get("customer", customer_id) if customer_id else None

        composed = compose(category_payload, merchant_payload, trigger_payload, customer_payload)
        conversation_id = _next_conversation_id(merchant_id, trg_id)
        conv_state = conversations.get_or_create(conversation_id, merchant_id, customer_id, trg_id)
        conv_state.add_turn(composed["send_as"], composed["body"])
        _fired_suppression_keys.add(suppression_key)

        actions.append({
            "conversation_id": conversation_id,
            "merchant_id": merchant_id,
            "customer_id": customer_id,
            "send_as": composed["send_as"],
            "trigger_id": trg_id,
            "template_name": f"vera_{trigger_payload.get('kind', 'generic')}_v1",
            "template_params": [merchant_payload.get("identity", {}).get("name", ""), trigger_payload.get("kind", "")],
            "body": composed["body"],
            "cta": composed["cta"],
            "suppression_key": suppression_key,
            "rationale": composed["rationale"],
        })
    return {"actions": actions}


class ReplyBody(BaseModel):
    conversation_id: str
    merchant_id: Optional[str] = None
    customer_id: Optional[str] = None
    from_role: str
    message: str
    received_at: str
    turn_number: int


@app.post("/v1/reply")
async def reply(body: ReplyBody):
    state = conversations.get_or_create(body.conversation_id, body.merchant_id or "", body.customer_id)
    result = conversation_respond(state, body.message, body.from_role)
    return result


@app.get("/v1/healthz")
async def healthz():
    return {"status": "ok", "uptime_seconds": int(time.time() - _START), "contexts_loaded": contexts.counts()}


@app.get("/v1/metadata")
async def metadata():
    return _METADATA


@app.post("/v1/teardown")
async def teardown():
    contexts.clear()
    conversations.clear()
    _fired_suppression_keys.clear()
    return {"status": "wiped"}
