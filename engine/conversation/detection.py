"""
Conversation intelligence: auto-reply detection, intent detection, language
detection, sentiment (acceptance/rejection/confusion). Rule-based and
deterministic on purpose — these gate control flow (send/wait/end), so they
must not vary run to run.

Anti-patterns this file exists to fix (challenge-brief.md §3, "today's biggest
pain points" and §9 Pattern D): burning turns on WhatsApp Business canned
auto-replies, and re-qualifying a merchant who already said yes.
"""
from __future__ import annotations

import re

_AUTO_REPLY_PHRASES = [
    "thank you for contacting",
    "we will get back to you",
    "hamari team tak pahuncha",
    "automated assistant",
    "aapki jaankari ke liye",
    "currently unavailable",
    "business hours",
    "we have received your message",
]

_INTENT_JOIN = [
    r"\bmujhe (magicpin )?jud[ai]?rna hai\b",
    r"\bi want to join\b",
    r"\blet'?s do it\b",
    r"\bok(ay)? let'?s\b",
    r"\bhaan chalo\b",
    r"\bsign me up\b",
]
_INTENT_ACCEPT = [
    r"^\s*yes\b", r"^\s*yep\b", r"^\s*sure\b", r"^\s*haan\b", r"^\s*ok(ay)?\b",
    r"\bplease (check|update|proceed|go ahead)\b", r"\bgo ahead\b",
]
_INTENT_REJECT = [
    r"\bnot interested\b", r"\bstop\b", r"\bno thanks\b", r"\bnahi chahiye\b",
    r"\bplease stop\b", r"\bunsubscribe\b",
]
_INTENT_QUESTION = [r"\?\s*$", r"^\s*(what|how|why|kab|kaise|kya)\b"]


def is_auto_reply(latest: str, prior_merchant_messages: list[str]) -> bool:
    """Same verbatim body 3+ times = auto-reply (challenge-brief.md §12 hint).
    Also flags known WhatsApp Business canned-reply phrasing on first occurrence."""
    if not latest:
        return False
    repeats = sum(1 for m in prior_merchant_messages if m.strip() == latest.strip())
    if repeats >= 2:  # this occurrence would be the 3rd+ verbatim repeat
        return True
    lowered = latest.lower()
    return any(phrase in lowered for phrase in _AUTO_REPLY_PHRASES)


def detect_intent(message: str) -> str:
    """Returns one of: join, accept, reject, question, confusion, none."""
    if not message:
        return "none"
    m = message.lower().strip()
    for pat in _INTENT_JOIN:
        if re.search(pat, m):
            return "join"
    for pat in _INTENT_REJECT:
        if re.search(pat, m):
            return "reject"
    for pat in _INTENT_ACCEPT:
        if re.search(pat, m):
            return "accept"
    for pat in _INTENT_QUESTION:
        if re.search(pat, m):
            return "question"
    return "none"


_HINDI_MARKERS = re.compile(r"[ऀ-ॿ]|\b(hai|kya|nahi|aap|kaise|chalo|bhai|kar|karo|haan)\b", re.IGNORECASE)


def detect_language(message: str) -> str:
    """Returns 'hi-en' if Devanagari or common Hindi-English code-mix tokens present, else 'en'."""
    return "hi-en" if _HINDI_MARKERS.search(message or "") else "en"


def is_hostile(message: str) -> bool:
    hostile_markers = ["idiot", "useless", "bakwas", "bekar", "shut up", "stupid"]
    m = (message or "").lower()
    return any(h in m for h in hostile_markers)


def is_off_topic(message: str) -> bool:
    off_topic_markers = ["gst", "income tax", "loan", "insurance claim", "visa"]
    m = (message or "").lower()
    return any(t in m for t in off_topic_markers)
