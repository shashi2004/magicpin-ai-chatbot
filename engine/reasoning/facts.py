"""
Stage 2+3+6: Understand Trigger, Understand Category, Find Business Opportunity.

One extractor per trigger `kind`. Each extractor pulls a *verifiable* primary fact
straight out of trigger.payload / merchant / category / customer — never invents
one. If a generated (non-seed) trigger only carries a placeholder payload, the
extractor falls back to the richest real number available on the merchant/customer
object itself, so specificity never degrades to "check your account".
"""
from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Callable, Optional

from engine.models import Category, Customer, Fact, FactBundle, Merchant, Trigger

Extractor = Callable[[Trigger, Merchant, Category, Optional[Customer]], FactBundle]

_REGISTRY: dict[str, Extractor] = {}


def register(*kinds: str):
    def deco(fn: Extractor) -> Extractor:
        for k in kinds:
            _REGISTRY[k] = fn
        return fn
    return deco


def extract(trigger: Trigger, merchant: Merchant, category: Category, customer: Optional[Customer]) -> FactBundle:
    if trigger.payload.get("placeholder"):
        # ~75% of the generated (non-seed) triggers carry no kind-specific fields at
        # all — just {"placeholder": true, "metric_or_topic": kind}. Rather than
        # printing "None" for missing payload fields, route to real, verifiable data
        # already sitting on merchant/category/customer for this trigger's theme.
        return _placeholder_extract(trigger, merchant, category, customer)
    fn = _REGISTRY.get(trigger.kind, _fallback)
    return fn(trigger, merchant, category, customer)


def _fallback(trigger: Trigger, merchant: Merchant, category: Category, customer: Optional[Customer]) -> FactBundle:
    perf = merchant.performance
    if perf.get("views") is not None:
        fact = Fact(f"{perf.get('views')} views / {perf.get('calls')} calls in the last {perf.get('window_days', 30)}d")
    else:
        fact = Fact(f"trigger '{trigger.kind}' flagged on your account")
    return FactBundle("generic_nudge", fact, suggested_cta_kind="open_ended",
                       reasoning=[f"no dedicated extractor for kind={trigger.kind}, used merchant performance snapshot"])


# ---------------------------------------------------------------- placeholder-payload fallback

_KIND_TO_OPPORTUNITY = {
    "research_digest": "research_hook", "regulation_change": "compliance_alert",
    "cde_opportunity": "cde_invite", "category_seasonal": "seasonal_prep",
    "festival_upcoming": "seasonal_prep", "ipl_match_today": "occasion_spike",
    "perf_spike": "performance_win", "perf_dip": "loss_aversion", "seasonal_perf_dip": "loss_aversion",
    "milestone_reached": "milestone_celebration", "review_theme_emerged": "social_listening",
    "competitor_opened": "competitive_pressure", "gbp_unverified": "compliance_alert",
    "supply_alert": "compliance_alert", "renewal_due": "loss_aversion", "dormant_with_vera": "re_engagement",
    "winback_eligible": "loss_aversion", "curious_ask_due": "ask_the_merchant",
    "active_planning_intent": "intent_handoff", "recall_due": "recall_reminder",
    "appointment_tomorrow": "appointment_reminder", "customer_lapsed_soft": "customer_recovery",
    "customer_lapsed_hard": "customer_recovery", "chronic_refill_due": "recall_reminder",
    "trial_followup": "trial_conversion", "wedding_package_followup": "milestone_push",
}


def _placeholder_extract(trigger: Trigger, merchant: Merchant, category: Category, customer: Optional[Customer]) -> FactBundle:
    kind = trigger.kind
    opp = _KIND_TO_OPPORTUNITY.get(kind, "generic_nudge")
    reasoning = [f"kind={kind} trigger payload was a generated placeholder; anchored on real merchant/category/customer data instead"]

    # Customer-scoped kinds: the customer's own relationship data is always real and specific.
    if trigger.scope == "customer" and customer:
        rel = customer.relationship
        last_visit, visits = rel.get("last_visit"), rel.get("visits_total")
        if last_visit:
            fact = Fact(f"last visit {last_visit}" + (f", {visits} visits total" if visits else ""))
        else:
            fact = Fact(f"currently {customer.state.replace('_', ' ')}")
        return FactBundle(opp, fact, suggested_cta_kind="binary", reasoning=reasoning)

    # Category seasonal knowledge is real, curated, category-specific data.
    if kind in ("festival_upcoming", "category_seasonal") and category.seasonal_beats:
        beat = category.seasonal_beats[0]
        fact = Fact(f"{beat.get('month_range')}: {beat.get('note')}")
        return FactBundle("seasonal_prep", fact, suggested_cta_kind="binary", reasoning=reasoning)

    # Competitive pressure without a named competitor -> fall back to a real peer-benchmark gap.
    if kind == "competitor_opened":
        ctr, peer_ctr = merchant.performance.get("ctr"), category.peer_stats.get("avg_ctr")
        if ctr is not None and peer_ctr is not None:
            fact = Fact(f"your CTR is {ctr*100:.1f}% vs the {peer_ctr*100:.1f}% category median")
            return FactBundle("competitive_pressure", fact, suggested_cta_kind="binary", reasoning=reasoning)

    # Milestones without a named metric -> use real customer_aggregate numbers.
    # Only ever state a stat that's actually present — a missing field must never
    # render as "0%", which would misreport a real (if unknown) number as zero.
    if kind == "milestone_reached":
        agg = merchant.customer_aggregate
        if agg.get("total_unique_ytd"):
            fact_text = f"{agg['total_unique_ytd']} unique customers YTD"
            if agg.get("retention_6mo_pct") is not None:
                fact_text += f", {agg['retention_6mo_pct']*100:.0f}% 6-month retention"
            return FactBundle("milestone_celebration", Fact(fact_text), suggested_cta_kind="open_ended", reasoning=reasoning)

    # Dormancy / re-engagement -> use the merchant's own signals list (real, derived upstream).
    if kind == "dormant_with_vera" and merchant.signals:
        fact = Fact(f"flagged signals on your account: {', '.join(s.split(':')[0].replace('_', ' ') for s in merchant.signals[:2])}")
        return FactBundle("re_engagement", fact, suggested_cta_kind="open_ended", reasoning=reasoning)

    # Performance-themed kinds -> the merchant's real 7-day delta, picking the metric
    # whose sign actually matches the trigger's framing (a "dip" must anchor on a
    # declining metric, a "spike" on a rising one — not just whichever key exists).
    if kind in ("perf_spike", "perf_dip", "seasonal_perf_dip", "renewal_due", "winback_eligible", "gbp_unverified"):
        perf = merchant.performance
        delta = perf.get("delta_7d", {})
        candidates = [(k, v) for k, v in delta.items() if k.endswith("_pct") and v is not None]
        if candidates:
            wants_negative = kind in ("perf_dip", "seasonal_perf_dip")
            matching = [c for c in candidates if (c[1] < 0) == wants_negative]
            metric, pct = (matching or candidates)[0]
            metric_name = metric.replace("_pct", "")
            fact = Fact(f"{metric_name} {'+' if pct >= 0 else ''}{pct*100:.0f}% over 7d vs your own baseline")
            if not matching and kind in ("perf_spike", "perf_dip", "seasonal_perf_dip"):
                # data doesn't actually support the trigger's dip/spike framing (e.g. a
                # "dip" trigger fired but every real delta on file is positive) — don't
                # pair a positive number with loss-aversion framing or vice versa.
                opp = "performance_win" if pct >= 0 else "loss_aversion"
                reasoning.append(f"real delta sign ({pct:+.2f}) contradicted trigger kind={kind}; reframed opportunity to {opp}")
            return FactBundle(opp, fact, suggested_cta_kind="binary" if opp == "loss_aversion" else "open_ended",
                               reasoning=reasoning)
        sub = merchant.get("subscription", {})
        if sub.get("days_remaining") is not None:
            fact = Fact(f"{sub['plan']} plan, {sub['days_remaining']} days remaining")
            return FactBundle(opp, fact, suggested_cta_kind="binary", reasoning=reasoning)

    # Research/compliance/CDE without a resolved digest item -> the category's top real digest item.
    if kind in ("research_digest", "regulation_change", "cde_opportunity") and category.digest:
        item = category.digest[0]
        fact = Fact(item.get("title", ""), source=item.get("source", ""))
        return FactBundle(opp, fact, suggested_cta_kind="open_ended", reasoning=reasoning)

    return _fallback(trigger, merchant, category, customer)


# ---------------------------------------------------------------- research / knowledge

@register("research_digest", "regulation_change")
def _research_or_regulation(trigger, merchant, category, customer):
    item_id = trigger.payload.get("top_item_id")
    item = category.digest_item(item_id) if item_id else None
    if not item:
        return _fallback(trigger, merchant, category, customer)
    is_compliance = item.get("kind") == "compliance" or trigger.kind == "regulation_change"
    if is_compliance:
        deadline = trigger.payload.get("deadline_iso", item.get("date", ""))
        title = item.get("title", "")
        needs_deadline = deadline and deadline[:10] not in title
        fact = Fact(f"{title}" + (f" — effective {deadline}" if needs_deadline else ""), source=item.get("source", ""))
        opp = "compliance_alert"
    else:
        segment = item.get("patient_segment") or item.get("segment") or ""
        n = item.get("trial_n")
        n_str = f"{n}-patient " if n else ""
        fact = Fact(f"{n_str}trial: {item.get('title')}", source=item.get("source", ""))
        opp = "research_hook"
    secondary = []
    if item.get("actionable"):
        secondary.append(Fact(item["actionable"]))
    high_risk = merchant.customer_aggregate.get("high_risk_adult_count")
    if segment_matches := (item.get("patient_segment") == "high_risk_adults" and high_risk):
        secondary.append(Fact(f"{high_risk} of your patients are in the high-risk-adult cohort this applies to"))
    return FactBundle(opp, fact, secondary, suggested_cta_kind="open_ended",
                       reasoning=[f"digest item {item_id} matched, compliance={is_compliance}"])


@register("cde_opportunity")
def _cde(trigger, merchant, category, customer):
    item_id = trigger.payload.get("digest_item_id")
    item = category.digest_item(item_id)
    credits = trigger.payload.get("credits")
    fee = trigger.payload.get("fee", "").replace("_", " ")
    if item:
        fact = Fact(f"{item.get('title')} — {credits} CDE credits, {fee}", source=item.get("source", ""))
    else:
        fact = Fact(f"CDE session worth {credits} credits ({fee})")
    return FactBundle("cde_invite", fact, suggested_cta_kind="binary")


@register("category_seasonal")
def _category_seasonal(trigger, merchant, category, customer):
    raw_trends = trigger.payload.get("trends", [])
    trends = [re.sub(r"_([+-]\d+)$", r" \1%", t).replace("_", " ") for t in raw_trends]
    season = trigger.payload.get("season", "").replace("_", " ")
    fact = Fact(f"{season}: {trends[0]}" if trends else f"{season} demand shift")
    return FactBundle("seasonal_prep", fact, suggested_cta_kind="binary",
                       secondary_facts=[Fact(", ".join(trends[1:3]))] if len(trends) > 1 else [])


@register("festival_upcoming")
def _festival(trigger, merchant, category, customer):
    festival = trigger.payload.get("festival", "")
    days = trigger.payload.get("days_until")
    fact = Fact(f"{festival} in {days} days" if days is not None else festival)
    return FactBundle("seasonal_prep", fact, suggested_cta_kind="binary")


@register("ipl_match_today")
def _ipl(trigger, merchant, category, customer):
    match = trigger.payload.get("match", "")
    venue = trigger.payload.get("venue", "")
    t = trigger.payload.get("match_time_iso", "")
    fact = Fact(f"{match} tonight at {venue}" + (f" ({t[11:16]} start)" if len(t) > 16 else ""))
    return FactBundle("occasion_spike", fact, suggested_cta_kind="binary")


# ---------------------------------------------------------------- performance signals

@register("perf_spike", "perf_dip", "seasonal_perf_dip")
def _perf_delta(trigger, merchant, category, customer):
    metric = trigger.payload.get("metric", "views")
    delta = trigger.payload.get("delta_pct", 0.0)
    window = trigger.payload.get("window", "7d")
    baseline = trigger.payload.get("vs_baseline")
    pct = f"{abs(delta) * 100:.0f}%"
    direction = "up" if delta >= 0 else "down"
    peer = category.peer_stats.get(f"avg_{metric}_30d")
    fact = Fact(f"{metric} {direction} {pct} over {window}" + (f" (baseline {baseline}/day)" if baseline else ""))
    secondary = []
    driver = trigger.payload.get("likely_driver")
    if driver:
        secondary.append(Fact(f"likely driver: {driver.replace('_', ' ')}"))
    if trigger.payload.get("is_expected_seasonal"):
        secondary.append(Fact(trigger.payload.get("season_note", "").replace("_", " ")))
    elif peer:
        secondary.append(Fact(f"category median is {peer}"))
    opp = "performance_win" if delta >= 0 else "loss_aversion"
    return FactBundle(opp, fact, secondary, suggested_cta_kind="open_ended" if delta >= 0 else "binary")


@register("milestone_reached")
def _milestone(trigger, merchant, category, customer):
    metric = trigger.payload.get("metric", "reviews").replace("_", " ")
    now, target = trigger.payload.get("value_now"), trigger.payload.get("milestone_value")
    if now is None or target is None:
        return _placeholder_extract(trigger, merchant, category, customer)
    imminent = trigger.payload.get("is_imminent")
    fact = Fact(f"{now}/{target} {metric}" + (" — almost there" if imminent else ""))
    return FactBundle("milestone_celebration" if not imminent else "milestone_push", fact,
                       suggested_cta_kind="open_ended" if not imminent else "binary")


@register("review_theme_emerged")
def _review_theme(trigger, merchant, category, customer):
    theme = trigger.payload.get("theme", "").replace("_", " ")
    n = trigger.payload.get("occurrences_30d")
    if not theme or n is None:
        return _placeholder_extract(trigger, merchant, category, customer)
    quote = trigger.payload.get("common_quote", "")
    fact = Fact(f'"{theme}" mentioned in {n} reviews this month' + (f' — e.g. "{quote}"' if quote else ""))
    return FactBundle("loss_aversion" if trigger.payload.get("trend") == "rising" else "social_listening",
                       fact, suggested_cta_kind="open_ended")


@register("competitor_opened")
def _competitor(trigger, merchant, category, customer):
    name = trigger.payload.get("competitor_name")
    dist = trigger.payload.get("distance_km")
    offer = trigger.payload.get("their_offer")
    if not name:
        # a live-injected trigger with no competitor name is indistinguishable from a
        # placeholder — reuse the same real-data (CTR vs peer median) fallback rather
        # than ever printing "None opened Nonekm away".
        return _placeholder_extract(trigger, merchant, category, customer)
    fact = Fact(f"{name} opened" + (f" {dist}km away" if dist is not None else " nearby") + (f", running \"{offer}\"" if offer else ""))
    return FactBundle("competitive_pressure", fact, suggested_cta_kind="binary")


@register("gbp_unverified")
def _gbp_unverified(trigger, merchant, category, customer):
    uplift = trigger.payload.get("estimated_uplift_pct")
    fact = Fact("your Google profile isn't verified yet" + (f" — verified listings see ~{int(uplift*100)}% more visibility" if uplift else ""))
    return FactBundle("compliance_alert", fact, suggested_cta_kind="binary")


@register("supply_alert")
def _supply_alert(trigger, merchant, category, customer):
    molecule = trigger.payload.get("molecule", "")
    batches = trigger.payload.get("affected_batches", [])
    fact = Fact(f"{molecule} recall — batches {', '.join(batches)}" if batches else f"{molecule} recall notice")
    return FactBundle("compliance_alert", fact, suggested_cta_kind="binary")


# ---------------------------------------------------------------- lifecycle / subscription

@register("renewal_due")
def _renewal(trigger, merchant, category, customer):
    days = trigger.payload.get("days_remaining")
    plan = trigger.payload.get("plan")
    amount = trigger.payload.get("renewal_amount")
    if days is None or plan is None:
        return _placeholder_extract(trigger, merchant, category, customer)
    fact = Fact(f"{plan} plan renews in {days} days" + (f" (₹{amount})" if amount else ""))
    return FactBundle("loss_aversion", fact, suggested_cta_kind="binary")


@register("dormant_with_vera")
def _dormant(trigger, merchant, category, customer):
    days = trigger.payload.get("days_since_last_merchant_message")
    if days is None:
        return _placeholder_extract(trigger, merchant, category, customer)
    last_topic = trigger.payload.get("last_topic", "").replace("_", " ")
    fact = Fact(f"{days} days since we last spoke" + (f" (were discussing {last_topic})" if last_topic else ""))
    return FactBundle("re_engagement", fact, suggested_cta_kind="open_ended")


@register("winback_eligible")
def _winback_merchant(trigger, merchant, category, customer):
    days = trigger.payload.get("days_since_expiry")
    if days is None:
        return _placeholder_extract(trigger, merchant, category, customer)
    lapsed = trigger.payload.get("lapsed_customers_added_since_expiry")
    fact = Fact(f"{days} days since your plan expired" + (f" — {lapsed} more customers have gone quiet since" if lapsed else ""))
    return FactBundle("loss_aversion", fact, suggested_cta_kind="binary")


@register("curious_ask_due")
def _curious_ask(trigger, merchant, category, customer):
    topic = trigger.payload.get("ask_template", "").replace("_", " ")
    fact = Fact(topic or "a quick question about your week")
    return FactBundle("ask_the_merchant", fact, suggested_cta_kind="open_ended")


@register("active_planning_intent")
def _active_planning(trigger, merchant, category, customer):
    topic = trigger.payload.get("intent_topic", "").replace("_", " ")
    fact = Fact(f"ready to move on {topic}" if topic else "ready to move on this")
    return FactBundle("intent_handoff", fact, suggested_cta_kind="open_ended")


# ---------------------------------------------------------------- customer-facing

@register("recall_due")
def _recall_due(trigger, merchant, category, customer):
    service = trigger.payload.get("service_due", "").replace("_", " ")
    due = trigger.payload.get("due_date")
    slots = trigger.payload.get("available_slots", [])
    if not service and not due:
        return _placeholder_extract(trigger, merchant, category, customer)
    fact = Fact(f"{service} due {due}" if due else service)
    secondary = [Fact(f"open slot: {s.get('label')}") for s in slots[:2]]
    return FactBundle("recall_reminder", fact, secondary, suggested_cta_kind="binary")


@register("appointment_tomorrow")
def _appointment_tomorrow(trigger, merchant, category, customer):
    if customer and customer.relationship.get("last_visit"):
        fact = Fact(f"appointment tomorrow, last visit was {customer.relationship.get('last_visit')}")
    else:
        fact = Fact("appointment tomorrow")
    return FactBundle("appointment_reminder", fact, suggested_cta_kind="binary")


@register("customer_lapsed_soft", "customer_lapsed_hard")
def _lapsed(trigger, merchant, category, customer):
    days = trigger.payload.get("days_since_last_visit")
    if days is None and customer:
        last_visit = customer.relationship.get("last_visit")
        days = last_visit  # best available anchor if no explicit day-count
    focus = trigger.payload.get("previous_focus", "").replace("_", " ")
    if isinstance(days, int):
        fact = Fact(f"{days} days since last visit" + (f", previously focused on {focus}" if focus else ""))
    elif days:
        fact = Fact(f"last visit was {days}")
    elif customer:
        visits = customer.relationship.get("visits_total")
        fact = Fact(f"{visits} visits on record, currently {customer.state.replace('_', ' ')}")
    else:
        fact = Fact("customer has gone quiet")
    return FactBundle("customer_recovery", fact, suggested_cta_kind="binary")


@register("chronic_refill_due")
def _chronic_refill(trigger, merchant, category, customer):
    molecules = trigger.payload.get("molecule_list", [])
    runs_out = trigger.payload.get("stock_runs_out_iso", "")
    fact = Fact(f"{', '.join(molecules)} — stock runs out {runs_out[:10]}" if molecules else "chronic refill due")
    return FactBundle("recall_reminder", fact, suggested_cta_kind="binary")


@register("trial_followup")
def _trial_followup(trigger, merchant, category, customer):
    trial_date = trigger.payload.get("trial_date")
    options = trigger.payload.get("next_session_options", [])
    fact = Fact(f"trial session on {trial_date}" if trial_date else "trial session completed")
    secondary = [Fact(f"next slot: {o.get('label')}") for o in options[:2]]
    return FactBundle("trial_conversion", fact, secondary, suggested_cta_kind="binary")


@register("wedding_package_followup")
def _wedding_followup(trigger, merchant, category, customer):
    wedding_date = trigger.payload.get("wedding_date")
    days_to = trigger.payload.get("days_to_wedding")
    next_step = trigger.payload.get("next_step_window_open", "").replace("_", " ")
    fact = Fact(f"wedding on {wedding_date} ({days_to} days away)" if wedding_date else "wedding package follow-up")
    secondary = [Fact(f"{next_step} window is open")] if next_step else []
    return FactBundle("milestone_push", fact, secondary, suggested_cta_kind="binary")
