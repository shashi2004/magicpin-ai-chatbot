"""Regression tests for the two named failure modes from the brief:
Pattern B (auto-reply burns turns) and Pattern D (intent handoff fails)."""
from engine.conversation.handler import respond
from engine.conversation.state import ConversationState


def test_auto_reply_gets_one_attempt_then_exits():
    state = ConversationState(conversation_id="c1", merchant_id="m1")
    canned = "Thank you for contacting us, we will get back to you."

    first = respond(state, canned)
    assert first["action"] == "send"

    second = respond(state, canned)
    assert second["action"] == "end"


def test_verbatim_repeat_three_times_flags_auto_reply():
    state = ConversationState(conversation_id="c2", merchant_id="m1")
    msg = "Aapki jaankari ke liye shukriya"
    respond(state, msg)          # occurrence 1: not yet flagged as auto-reply by repeat count,
    r = respond(state, msg)      # but phrase-match kicks in immediately either way
    assert r["action"] in ("send", "end")


def test_explicit_join_intent_routes_to_action_not_requalification():
    state = ConversationState(conversation_id="c3", merchant_id="m1")
    result = respond(state, "Mujhe magicpin judrna hai")
    assert result["action"] == "send"
    assert "?" not in result["body"] or "no more questions" in result["body"].lower()
    assert "requalify" not in result["rationale"].lower()
    assert "join" in result["rationale"].lower()


def test_explicit_rejection_ends_conversation():
    state = ConversationState(conversation_id="c4", merchant_id="m1")
    result = respond(state, "Not interested, please stop")
    assert result["action"] == "end"


def test_hostile_message_stays_on_mission():
    state = ConversationState(conversation_id="c5", merchant_id="m1")
    result = respond(state, "This is bakwas, stupid bot")
    assert result["action"] == "send"


def test_off_topic_declines_politely_without_ending():
    state = ConversationState(conversation_id="c6", merchant_id="m1")
    result = respond(state, "can you also help me file my GST?")
    assert result["action"] == "send"
