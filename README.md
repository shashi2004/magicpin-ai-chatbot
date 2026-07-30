# Submission: Vera-class Merchant AI Assistant

## Approach

The system is a **deterministic reasoning pipeline**, not a single prompt. For every
`(category, merchant, trigger, customer?)` it runs: trigger-kind fact extraction
(`engine/reasoning/facts.py`, one extractor per trigger `kind`, 25 kinds covered) →
merchant mental model (`mental_model.py`: language pref, conversation state,
auto-reply/intent already in history) → compulsion-lever selection
(`levers.py`, biased toward social-proof and ask-the-merchant per the brief's
own diagnosis of Vera's biggest miss) → templated candidate generation, two
structural variants (`templates.py`) → heuristic self-evaluation against the
5-dimension rubric (`evaluator.py`) → best-of selection → optional LLM polish
that can only improve phrasing, never introduce a fact (`llm.py`).

The same `compose()` core backs both deliverable shapes: the static
`bot.py`/`submission.jsonl` path (challenge-brief.md §7) and the live 5-endpoint
HTTP harness (`engine/api/server.py`, challenge-testing-brief.md §2) — one
reasoning engine, two thin adapters.

**Why rule-based-first rather than LLM-first:** the spec requires determinism
(temp=0, identical output for identical input) and explicitly penalizes
hallucination. A template renderer that only ever fills verified fields from the
four contexts satisfies both by construction — it cannot invent a citation or a
number. The LLM stage is opt-in (`ANTHROPIC_API_KEY`/`OPENAI_API_KEY`), rewrites
prose only, and is rejected if it drops a numeric anchor the draft had or scores
lower than the draft. The bot is fully functional with zero API keys.

**Key fix — placeholder-trigger fallback:** ~75% of the generated (non-seed)
triggers in the expanded dataset carry no kind-specific payload fields at all
(`{"placeholder": true, "metric_or_topic": "<kind>"}`). Naive per-kind extractors
would print `"None"` or empty facts for most of the dataset. `facts.py` detects
this and falls back to real, verifiable data already present on the
merchant/category/customer objects (peer-stat gaps, customer_aggregate, real
7-day performance deltas, category seasonal beats) — so specificity never
degrades to "check your account" even when the trigger itself is thin. Every
individual extractor also guards its own kind-specific fields the same way, so
a live-injected trigger during the judge's Phase 3 (new triggers mid-test,
challenge-testing-brief.md) that doesn't match the seed shape degrades the same
way instead of leaking `"None"` — covered by `tests/test_facts_defensive.py`.

**Phrase-variety pass:** the first version of the template renderer had a real
weakness — a small fixed set of CTA/lever sentences meant many of the 30 test
messages shared identical closing lines verbatim, which reads as templated and
risks the anti-repetition penalty (challenge-brief.md §11). Fixed by giving
each lever/CTA 4 equivalent phrasings (rewritten for a warmer, less corporate
tone) plus opener variety (Hi/Hey/Namaste/Hello instead of always "Hi"),
selecting deterministically via `sha256(merchant_id + customer_id +
opportunity_type + primary_fact)` — same input still always produces the same
output, but different (merchant, trigger) pairs no longer collide on
boilerplate.

## Tradeoffs

- **No live LLM validation run.** `judge_simulator.py` requires a hardcoded API
  key in the file (no env var override) — none was available. Instead I stood
  up the actual HTTP harness locally and drove it through the real dataset:
  idempotent context push, suppression-key dedup on repeat ticks, auto-reply
  detection with a single graceful-exit retry, and instant intent→action
  routing all verified against the running server, plus 38 pytest regressions
  covering all 30 canonical test pairs. Real judge scoring is unverified.
- **Template diversity is structural, not stylistic.** Two candidate orderings
  per opportunity type (fact-first vs. hook-first) rather than N free-form LLM
  generations — deliberate, to keep determinism airtight, at the cost of prose
  variety when no LLM key is present.
- **No dashboards/Docker/Redis/CI.** None of these move the 5-dimension score;
  scope was kept to the judge-facing surface (composer + HTTP harness + tests).
- **Multi-turn cadence planning (open challenge §12.3)** is reactive (per-reply)
  rather than a planned multi-message sequence within the 24h window — the
  `/v1/tick` suppression-key dedup prevents spam, but there's no explicit
  "day 1 nudge, day 3 follow-up" scheduler.

## What additional context would have helped most

- **A live LLM key + one real `judge_simulator.py` run** before submitting, to
  calibrate the internal heuristic evaluator against the actual rubric rather
  than a proxy of it.
- **Timestamps on conversation_history turns relative to "now"** — several
  placeholder triggers (`dormant_with_vera`, `curious_ask_due`) would benefit
  from a real elapsed-time figure instead of falling back to static signals.
- **Explicit multi-turn cadence rules** (e.g. max nudges/week per merchant)
  would remove one guessed design decision (currently: fire once per
  suppression key, never re-fire).

## Running it

```bash
pip install fastapi uvicorn pydantic pytest
python3 -m pytest tests/ -q                  # 48 tests
python3 generate_submission.py               # writes submission.jsonl
uvicorn engine.api.server:app --host 0.0.0.0 --port 8080   # live harness
```

Optional LLM polish: set `ANTHROPIC_API_KEY` or `OPENAI_API_KEY` before running.
