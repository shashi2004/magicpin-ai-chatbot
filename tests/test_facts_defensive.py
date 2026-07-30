"""
Regression tests for malformed/incomplete trigger payloads — the exact shape a
live judge test can throw at us mid-run (challenge-testing-brief.md Phase 3:
"new triggers... spread across the test window", not guaranteed to match the
seed dataset's fully-populated shape). Every kind must degrade to a real
merchant/category/customer-backed fact, never a literal "None" in the output.
"""
import json
from pathlib import Path

import pytest

from engine.reasoning.composer import compose

DATASET = Path(__file__).parent.parent / "dataset" / "expanded"
MERCHANT = json.loads((DATASET / "merchants" / "m_001_drmeera_dentist_delhi.json").read_text())
CATEGORY = json.loads((DATASET / "categories" / "dentists.json").read_text())


def _bare_trigger(kind: str, scope: str = "merchant") -> dict:
    """A trigger with only the fields every trigger is guaranteed to have —
    no kind-specific payload fields at all."""
    return {
        "id": f"trg_test_{kind}",
        "scope": scope,
        "kind": kind,
        "source": "internal",
        "merchant_id": MERCHANT["merchant_id"],
        "customer_id": None,
        "payload": {},
        "urgency": 2,
        "suppression_key": f"test:{kind}",
        "expires_at": "2026-12-31T00:00:00Z",
    }


@pytest.mark.parametrize("kind", [
    "competitor_opened", "renewal_due", "dormant_with_vera", "winback_eligible",
    "milestone_reached", "review_theme_emerged", "recall_due", "gbp_unverified",
    "perf_dip", "perf_spike",
])
def test_bare_payload_never_leaks_none(kind):
    trigger = _bare_trigger(kind)
    result = compose(CATEGORY, MERCHANT, trigger, None)
    assert "None" not in result["body"], f"{kind}: leaked None with a bare payload"
    assert result["body"].strip(), f"{kind}: produced an empty body"
