#!/usr/bin/env python3
"""Produce submission.jsonl for the 30 canonical test pairs (challenge-brief.md §6-7)."""
from __future__ import annotations

import json
from pathlib import Path

from bot import compose

DATASET = Path(__file__).parent / "dataset" / "expanded"


def load(scope: str, context_id: str) -> dict:
    path = DATASET / scope / f"{context_id}.json"
    with open(path) as f:
        return json.load(f)


def load_category_for(merchant: dict) -> dict:
    return load("categories", merchant["category_slug"])


def main() -> None:
    test_pairs = json.loads((DATASET / "test_pairs.json").read_text())["pairs"]
    out_path = Path(__file__).parent / "submission.jsonl"
    with open(out_path, "w") as out:
        for pair in test_pairs:
            merchant = load("merchants", pair["merchant_id"])
            trigger = load("triggers", pair["trigger_id"])
            category = load_category_for(merchant)
            customer = load("customers", pair["customer_id"]) if pair.get("customer_id") else None

            composed = compose(category, merchant, trigger, customer)
            record = {"test_id": pair["test_id"], **composed}
            out.write(json.dumps(record, ensure_ascii=False) + "\n")
            print(f"{pair['test_id']}: {composed['body'][:90]}...")

    print(f"\nWrote {len(test_pairs)} lines to {out_path}")


if __name__ == "__main__":
    main()
