"""
The Reasoning Engine's orchestrator — runs the full pipeline described in the
mission brief:

  Normalize Context -> Merchant Mental Model -> Detect Opportunity ->
  Predict Best Next Action -> Generate Candidates -> Self-Evaluate ->
  Rewrite (optional LLM polish) -> Score -> Return Best Candidate

Every message that leaves this module has been reasoned about before a single
word of prose existed (facts + opportunity_type + levers came first; templates
only render what reasoning already decided).
"""
from __future__ import annotations

from dataclasses import asdict
from typing import Any, Optional

from engine.models import Category, Customer, Merchant, Trigger
from engine.reasoning import evaluator, facts, llm, templates
from engine.reasoning.mental_model import build as build_mental_model

MIN_ACCEPTABLE_SCORE = 20.0  # out of 50; below this we still return best-of but flag it in rationale


def compose(
    category_raw: dict,
    merchant_raw: dict,
    trigger_raw: dict,
    customer_raw: Optional[dict] = None,
) -> dict[str, Any]:
    category = Category(category_raw)
    merchant = Merchant(merchant_raw)
    trigger = Trigger(trigger_raw)
    customer = Customer(customer_raw) if customer_raw else None

    # Stage 1+4+5: merchant mental model (voice, conversation state, existing intent)
    mental_model = build_mental_model(merchant)

    # Stage 2+3+6: trigger + category understanding -> business opportunity
    bundle = facts.extract(trigger, merchant, category, customer)

    # Stage 8: candidate generation (deterministic templates, 2 structural variants)
    candidates = templates.render(bundle, mental_model, merchant, category, customer)

    # Stage 9: self-evaluate every candidate against the 5-dimension rubric proxy
    scored = [(c, evaluator.score(c, bundle, merchant, category, mental_model)) for c in candidates]
    scored.sort(key=lambda pair: pair[1].total, reverse=True)
    best_candidate, best_score = scored[0]

    # Anti-repetition: never resend a body verbatim already in conversation_history
    prior_bodies = {t.get("body", "") for t in merchant.conversation_history if t.get("from") == "vera"}
    if best_candidate.body in prior_bodies and len(scored) > 1:
        best_candidate, best_score = scored[1]

    # Rewrite: optional LLM polish, re-scored and only kept if it doesn't regress
    final_body = best_candidate.body
    was_polished = False
    if llm.available():
        polished_body, was_polished = llm.safe_polish(best_candidate.body)
        if was_polished:
            polished_candidate = type(best_candidate)(
                body=polished_body, cta=best_candidate.cta,
                rationale=best_candidate.rationale, send_as=best_candidate.send_as,
            )
            polished_score = evaluator.score(polished_candidate, bundle, merchant, category, mental_model)
            if polished_score.total >= best_score.total:
                final_body, best_score = polished_body, polished_score
            else:
                was_polished = False

    suppression_key = trigger.suppression_key
    rationale = (
        f"why_now: trigger={trigger.kind} (urgency={trigger.urgency}, source={trigger.source}); "
        f"why_offer/fact: {bundle.opportunity_type} anchored on '{bundle.primary_fact.text}'; "
        f"why_tone: category={category.slug} voice={category.voice.get('tone', 'n/a')}, "
        f"hindi_mix={mental_model.prefers_hindi_mix}; "
        f"why_cta: {best_candidate.cta}; "
        f"self_eval_score: {best_score.total:.1f}/50 "
        f"(specificity={best_score.specificity:.1f}, category_fit={best_score.category_fit:.1f}, "
        f"merchant_fit={best_score.merchant_fit:.1f}, trigger_relevance={best_score.trigger_relevance:.1f}, "
        f"engagement={best_score.engagement:.1f}); "
        f"llm_polished={was_polished}"
    )

    return {
        "body": final_body,
        "cta": best_candidate.cta,
        "send_as": best_candidate.send_as,
        "suppression_key": suppression_key,
        "rationale": rationale,
    }
