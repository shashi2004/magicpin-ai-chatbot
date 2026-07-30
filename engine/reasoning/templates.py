"""
Stage 8: Generate Multiple Candidate Responses.

Facts and numbers are NEVER translated or reworded — only the connective tissue
(openers, CTA phrasing) varies, so a Hindi-English merchant gets natural code-mix
without any risk of the underlying number/date/citation drifting (AGENTS: "don't
fabricate", "specificity wins").

Each opportunity_type gets a same-content structural template (fact -> secondary
-> lever -> CTA) rendered in two orderings, so the evaluator has genuine variants
to score rather than cosmetic rewording.
"""
from __future__ import annotations

import hashlib

from engine.models import Candidate, Category, Customer, FactBundle, Merchant
from engine.reasoning import levers as lv
from engine.reasoning.mental_model import MerchantMentalModel

# lever_name -> list of (english, hindi-mix) phrase variants, given (fact, secondary).
# Multiple variants exist so that different (merchant, trigger) pairs don't all read
# the exact same boilerplate sentence — a real risk when 30+ messages share a small
# set of opportunity types. Selection is a deterministic hash, not randomness, so a
# given input still always produces the same output (testing-brief §7: determinism).
_LEVER_PHRASES: dict[str, list[tuple[str, str]]] = {
    "specificity": [("", "")],  # specificity lives in the fact sentence itself, no extra phrase
    "loss_aversion": [
        ("before this window shuts", "yeh mauka haath se nikalne se pehle"),
        ("while it's still live", "jab tak yeh chalu hai"),
        ("before it quietly lapses", "chupke se lapse hone se pehle"),
        ("only while this stays open", "sirf jab tak yeh khula hai"),
    ],
    "social_proof": [
        ("other locality peers have already jumped on this", "aas-paas ke peers isme pehle hi lag chuke hain"),
        ("a couple of nearby shops are already acting on it", "kuch nearby dukaanein isse already follow kar rahi hain"),
        ("this is trending among your locality peers right now", "yeh abhi aapke locality peers mein chal raha hai"),
        ("peers close to you are not sitting on this one", "aapke aas-paas ke peers isse chhod nahi rahe"),
    ],
    "reciprocity": [
        ("wanted you to be the first to know", "socha aapko sabse pehle pata chale"),
        ("flagging this before it does the rounds", "yeh sabko pata chale usse pehle aapko bata raha hoon"),
        ("this felt worth a heads-up from me", "laga yeh baat aapko batani chahiye"),
        ("didn't want you to hear this last", "chaha ki yeh aapko sabse aakhir mein na pata chale"),
    ],
    "effort_externalization": [
        ("I've already put the next step together", "agla step maine already taiyaar kar diya hai"),
        ("groundwork's done on my end, just need a go-ahead", "kaam ho chuka hai mere taraf se, bas aapka go-ahead chahiye"),
        ("it's drafted and sitting ready", "draft ban ke ready pada hai"),
        ("I've handled the setup already", "setup mein maine kaam kar diya hai"),
    ],
    "curiosity": [
        ("worth a look", "ek baar zaroor dekhiye"),
        ("worth a quick peek", "zara nazar daaliye"),
        ("might be worth checking", "check kar lena shayad kaam aaye"),
        ("take a look when you get a sec", "time mile to ek baar dekh lijiyega"),
    ],
    "asking_the_merchant": [
        ("curious how this looks from your side", "aapki taraf se yeh kaisa lag raha hai, bataiye"),
        ("what are you noticing on the ground?", "ground par aapko kya nazar aa raha hai?"),
        ("would love your read on this", "aapki raay jaanna chahunga is baare mein"),
        ("what's your take, from where you're sitting?", "aapki jagah se dekhein to kya lagta hai?"),
    ],
    "single_binary": [("", "")],  # handled by CTA sentence, not a standalone phrase
}

_CTA_BINARY_VARIANTS = [
    {"en": "Reply YES to go ahead, or STOP if not.", "hi": "YES likh dijiye agar karna hai, warna STOP."},
    {"en": "One YES and I'll get moving, or STOP to skip.", "hi": "Ek YES aur main shuru kar doon, ya STOP karke chhod dein."},
    {"en": "Just say YES to proceed, STOP to pass.", "hi": "Bas YES boliye aage badhne ke liye, STOP agar nahi."},
    {"en": "YES gets it done, STOP skips it — your call.", "hi": "YES se kaam ho jayega, STOP se skip — aapki marzi."},
]
_CTA_OPEN_VARIANTS = [
    {"en": "Want me to take it from here?", "hi": "Chahenge main yahan se aage le loon?"},
    {"en": "Should I go ahead?", "hi": "Main aage badhu?"},
    {"en": "Shall I handle the rest?", "hi": "Baaki main dekh loon?"},
    {"en": "Say the word and I'll get started.", "hi": "Ek ishaara kijiye, main shuru kar doon."},
]


def _variant_index(seed_key: str, n: int) -> int:
    """Stable across processes/runs (unlike builtin hash(), which is salted per-process),
    so the same (merchant, trigger, customer) always selects the same phrasing."""
    digest = hashlib.sha256(seed_key.encode("utf-8")).hexdigest()
    return int(digest, 16) % n


_GREETING_OPENERS_EN = ["Hi", "Hey", "Hello"]
_GREETING_OPENERS_HI = ["Hi", "Namaste", "Hello"]


def _greeting(subject: str, is_new: bool, hindi: bool, seed_key: str = "") -> str:
    if not is_new:
        return ""
    openers = _GREETING_OPENERS_HI if hindi else _GREETING_OPENERS_EN
    opener = openers[_variant_index(seed_key + ":greeting", len(openers))] if seed_key else openers[0]
    return f"{opener} {subject},"


def _fact_clause(fact) -> str:
    base = fact.text[0].upper() + fact.text[1:] if fact.text else ""
    return f"{base} — {fact.source}." if fact.source else f"{base}."


def _lever_clause(lever: str, hindi: bool, seed_key: str) -> str:
    variants = _LEVER_PHRASES.get(lever, [("", "")])
    en, hi = variants[_variant_index(seed_key + ":" + lever, len(variants))]
    phrase = hi if hindi else en
    return phrase.capitalize() + "." if phrase else ""


def _cta_clause(cta_kind: str, hindi: bool, seed_key: str) -> str:
    lang = "hi" if hindi else "en"
    if cta_kind == "binary":
        variant = _CTA_BINARY_VARIANTS[_variant_index(seed_key + ":cta_binary", len(_CTA_BINARY_VARIANTS))]
        return variant[lang]
    if cta_kind == "open_ended":
        variant = _CTA_OPEN_VARIANTS[_variant_index(seed_key + ":cta_open", len(_CTA_OPEN_VARIANTS))]
        return variant[lang]
    return ""


def _assemble(parts: list[str]) -> str:
    return " ".join(p for p in parts if p).strip()


def render(
    bundle: FactBundle,
    mental_model: MerchantMentalModel,
    merchant: Merchant,
    category: Category,
    customer: Customer | None,
) -> list[Candidate]:
    subject = customer.name if customer else merchant.first_name
    hindi = customer.wants_hindi_mix if customer else mental_model.prefers_hindi_mix
    levers = lv.levers_for(bundle.opportunity_type)
    primary_lever = next((l for l in levers if l not in ("specificity", "single_binary")), None)

    # Seeds phrase-variant selection: unique per (merchant, customer, opportunity, fact),
    # so different (merchant, trigger) pairs land on different phrasing deterministically,
    # while the SAME pair always reproduces the SAME message on every call.
    seed_key = f"{merchant.merchant_id}:{customer.customer_id if customer else ''}:{bundle.opportunity_type}:{bundle.primary_fact.text}"

    greeting = _greeting(subject, mental_model.is_new_conversation, hindi, seed_key)
    fact_clause = _fact_clause(bundle.primary_fact)
    secondary_clause = _fact_clause(bundle.secondary_facts[0]) if bundle.secondary_facts else ""
    lever_clause = _lever_clause(primary_lever, hindi, seed_key) if primary_lever else ""
    cta_clause = _cta_clause(bundle.suggested_cta_kind, hindi, seed_key)

    send_as = "merchant_on_behalf" if customer else "vera"

    # Variant A: fact leads (most specific-first, good default for research/compliance/perf triggers)
    variant_a = _assemble([greeting, fact_clause, secondary_clause, lever_clause, cta_clause])

    # Variant B: lever/question leads when the lever is curiosity or ask-the-merchant (better hook for
    # engagement-oriented triggers); otherwise a tighter cut that drops the secondary fact.
    if primary_lever in ("curiosity", "asking_the_merchant") and lever_clause:
        variant_b = _assemble([greeting, lever_clause, fact_clause, cta_clause])
    else:
        variant_b = _assemble([greeting, fact_clause, cta_clause])

    rationale_base = (
        f"opportunity={bundle.opportunity_type}, levers={levers}, "
        f"anchor='{bundle.primary_fact.text}'"
    )

    return [
        Candidate(body=variant_a, cta=bundle.suggested_cta_kind, rationale=rationale_base + ", ordering=fact_first", send_as=send_as),
        Candidate(body=variant_b, cta=bundle.suggested_cta_kind, rationale=rationale_base + ", ordering=hook_first_or_tight", send_as=send_as),
    ]
