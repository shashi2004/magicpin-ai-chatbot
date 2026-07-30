"""Determinism + anti-pattern regression tests against the real dataset."""
import json
from pathlib import Path

import pytest

from bot import compose

DATASET = Path(__file__).parent.parent / "dataset" / "expanded"


def _load(scope, cid):
    with open(DATASET / scope / f"{cid}.json") as f:
        return json.load(f)


def _test_pairs():
    return json.loads((DATASET / "test_pairs.json").read_text())["pairs"]


@pytest.mark.parametrize("pair", _test_pairs(), ids=lambda p: p["test_id"])
def test_all_canonical_pairs_produce_valid_message(pair):
    merchant = _load("merchants", pair["merchant_id"])
    trigger = _load("triggers", pair["trigger_id"])
    category = _load("categories", merchant["category_slug"])
    customer = _load("customers", pair["customer_id"]) if pair.get("customer_id") else None

    result = compose(category, merchant, trigger, customer)

    for key in ("body", "cta", "send_as", "suppression_key", "rationale"):
        assert result.get(key), f"{pair['test_id']}: missing/empty '{key}'"

    assert "None" not in result["body"], f"{pair['test_id']}: leaked a None into body"
    assert result["cta"] in ("binary", "open_ended", "none")
    assert result["send_as"] in ("vera", "merchant_on_behalf")
    assert len(result["body"]) < 700, f"{pair['test_id']}: body too long"
    # anti-pattern: no multi-choice CTA phrasing
    assert "maybe for" not in result["body"].lower()


def test_determinism():
    merchant = _load("merchants", "m_001_drmeera_dentist_delhi")
    trigger = _load("triggers", "trg_001_research_digest_dentists")
    category = _load("categories", "dentists")
    r1 = compose(category, merchant, trigger, None)
    r2 = compose(category, merchant, trigger, None)
    assert r1 == r2


def test_customer_facing_send_as():
    pairs = [p for p in _test_pairs() if p.get("customer_id")]
    assert pairs, "expected at least one customer-facing test pair"
    for pair in pairs:
        merchant = _load("merchants", pair["merchant_id"])
        trigger = _load("triggers", pair["trigger_id"])
        category = _load("categories", merchant["category_slug"])
        customer = _load("customers", pair["customer_id"])
        result = compose(category, merchant, trigger, customer)
        assert result["send_as"] == "merchant_on_behalf"
