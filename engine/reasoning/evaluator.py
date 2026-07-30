"""
Stage 9 (Score Every Candidate) + Self-Improvement (Critique/Reject).

Deterministic heuristic scorer approximating the judge's 5-dimension rubric
(challenge-brief.md §8), so the composer can reject weak candidates and pick the
best one *before* ever sending. Not a replacement for the real judge — a
best-effort proxy that also doubles as a Quality/Safety Validator (anti-patterns
in §11 are hard-penalized here).
"""
from __future__ import annotations

import re

from engine.models import Candidate, Category, FactBundle, Merchant, ScoreCard
from engine.reasoning.mental_model import MerchantMentalModel

_GENERIC_PHRASES = [
    "increase your sales", "boost your business", "amazing deal", "flat 30% off",
    "i hope you're doing well", "reaching out today", "grow your business",
    "% off",
]
_PROMO_MARKERS = ["!!!", "AMAZING", "HURRY", "LIMITED TIME"]
_MULTI_CTA_MARKERS = ["reply yes for", "reply 1 for x", "maybe for"]


def _num_anchors(text: str) -> int:
    return len(re.findall(r"\d", text))


def _has_citation(text: str) -> bool:
    return "—" in text and bool(re.search(r"[A-Za-z].*\d{4}|p\.\d+", text))


def score_specificity(body: str, bundle: FactBundle) -> float:
    score = 3.0
    digits = _num_anchors(body)
    score += min(digits, 6) * 0.6
    if _has_citation(body):
        score += 1.5
    if any(g in body.lower() for g in _GENERIC_PHRASES):
        score -= 4.0
    return max(0.0, min(10.0, score))


def score_category_fit(body: str, category: Category) -> float:
    score = 7.0
    voice = category.voice
    taboo = [t.lower() for t in voice.get("vocab_taboo", [])]
    for t in taboo:
        base = t.split(" (")[0]
        if base and base in body.lower():
            score -= 3.0
    if any(m in body for m in _PROMO_MARKERS):
        score -= 3.0
    tone = voice.get("tone", "")
    if tone == "peer_clinical" and body.count("!") > 0:
        score -= 1.0
    return max(0.0, min(10.0, score))


def score_merchant_fit(body: str, merchant: Merchant, mental_model: MerchantMentalModel) -> float:
    score = 6.0
    if mental_model.prefers_hindi_mix:
        hindi_tokens = ["hai", "kya", "aap", "chahenge", "karein", "lijiye", "boon", "hain"]
        if any(tok in body.lower() for tok in hindi_tokens):
            score += 2.0
        else:
            score -= 2.0
    if mental_model.is_new_conversation and body.strip().lower().startswith(("hi ", "hello ")):
        score += 1.0
    if not mental_model.is_new_conversation and re.search(r"\b(hi|hello)\b,? \w+,", body.lower()):
        score -= 2.0  # re-introducing itself mid-conversation
    return max(0.0, min(10.0, score))


def score_trigger_relevance(body: str, bundle: FactBundle) -> float:
    score = 4.0
    fact_words = {w.lower() for w in re.findall(r"[A-Za-z0-9%₹]+", bundle.primary_fact.text) if len(w) > 2}
    body_words = {w.lower() for w in re.findall(r"[A-Za-z0-9%₹]+", body)}
    overlap = len(fact_words & body_words)
    score += min(overlap, 6) * 0.9
    return max(0.0, min(10.0, score))


def score_engagement(body: str, candidate: Candidate) -> float:
    score = 5.0
    lower = body.lower()
    if any(m in lower for m in _MULTI_CTA_MARKERS):
        score -= 3.0
    if candidate.cta == "none" and "?" in body:
        score -= 1.0
    if candidate.cta != "none" and body.rstrip().endswith(("?", ".", "STOP.")):
        score += 1.0
    if len(body) > 500:
        score -= 2.0
    if any(g in lower for g in _GENERIC_PHRASES):
        score -= 2.0
    if "?" in body or "reply" in lower:
        score += 1.5
    return max(0.0, min(10.0, score))


def score(candidate: Candidate, bundle: FactBundle, merchant: Merchant, category: Category,
          mental_model: MerchantMentalModel) -> ScoreCard:
    body = candidate.body
    return ScoreCard(
        specificity=score_specificity(body, bundle),
        category_fit=score_category_fit(body, category),
        merchant_fit=score_merchant_fit(body, merchant, mental_model),
        trigger_relevance=score_trigger_relevance(body, bundle),
        engagement=score_engagement(body, candidate),
    )
