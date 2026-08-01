# LLM Dual-Track, Confidence, and Abstention Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Define file-based Track A and Track B contracts, validate LLM boundaries, compute deterministic confidence, and abstain when review evidence is unsafe or incomplete.

**Architecture:** The runtime prepares prompt/input bundles but never calls a model. Codex or ChatGPT writes two separate JSON outputs. Validators compare them with evidence, rule, and math artifacts before the finalizer may produce a review packet.

**Tech Stack:** Python 3.11+, JSON, Markdown templates, Decimal confidence scoring, pytest.

## Global Constraints

- Track A/B files are untrusted until validated.
- Track A cannot calculate, set rule status, confidence, abstention, or human decision.
- Track B audits every Track A claim and emits findings; it does not rewrite Track A.
- Numeric claim tokens must exactly match a cited source or registered Math Engine result.

---

### Task 1: Track A Bundle and Validator

**Files:** Create `src/ansim_review/llm_layer/track_a.py`, `src/ansim_review/llm_layer/templates/track-a.md`; test `tests/unit/llm_layer/test_track_a_validator.py`.

- [ ] Test that `human_decision`, `confidence`, or a self-authored rule result causes validation failure.
- [ ] Run and observe failure.
- [ ] Build a bundle containing question, inputs, evidence, rule results, and calculations; require claims, citations, missing inputs, exceptions, conflicts, and explanation sections.
- [ ] Run tests.
- [ ] Commit: `git commit -m "feat: define evidence-only track a contract"`.

### Task 2: Calculation and Rule Integrity Validation

**Files:** Create `src/ansim_review/llm_layer/validators.py`; modify `tests/unit/llm_layer/test_track_a_validator.py`.

- [ ] Test that `9.4%` is rejected when Math Engine output is `9.375%` and source evidence does not contain `9.4%`.
- [ ] Run and observe failure.
- [ ] Extract numeric/percent tokens and accept only exact source or linked CalculationResult values; verify rule status references by result ID/hash.
- [ ] Run tests.
- [ ] Commit: `git commit -m "feat: prevent llm-authored calculations"`.

### Task 3: Track B Audit Contract

**Files:** Create `src/ansim_review/llm_layer/track_b.py`, `src/ansim_review/llm_layer/templates/track-b.md`; test `tests/unit/llm_layer/test_track_b_validator.py`.

- [ ] Test Track B fails if any Track A claim ID is unaudited.
- [ ] Run and observe failure.
- [ ] Implement dispositions `ACCEPT`, `REJECT`, `INCOMPLETE` and finding codes `MISSING_EXCEPTION`, `CITATION_MISMATCH`, `UNSUPPORTED_CLAIM`, `CALCULATION_MISMATCH`, `RULE_STATUS_MISMATCH`, `FINAL_DECISION_LANGUAGE`, `SOURCE_CONFLICT`.
- [ ] Run tests.
- [ ] Commit: `git commit -m "feat: define independent track b audit"`.

### Task 4: Confidence Policy V1

**Files:** Create `src/ansim_review/confidence/policy.py`, `src/ansim_review/confidence/scorer.py`; test `tests/unit/confidence/test_scorer.py`.

- [ ] Write exact weighted-score and boundary tests using Decimal.
- [ ] Run and observe failure.
- [ ] Implement the design-spec weights, quantize to four decimals with `ROUND_HALF_UP`, and include factor/weight/contribution/source in output.
- [ ] Run tests for HIGH/MEDIUM/LOW boundaries.
- [ ] Commit: `git commit -m "feat: add auditable confidence policy v1"`.

### Task 5: Hard Abstention Gates

**Files:** Create `src/ansim_review/abstention/gates.py`; test `tests/unit/abstention/test_gates.py`.

- [ ] Test unresolved conflict abstains even at confidence `0.99`.
- [ ] Run and observe failure.
- [ ] Implement all design hard gates plus `LOW_CONFIDENCE` below 0.70; return all reason codes in declared order.
- [ ] Run tests.
- [ ] Commit: `git commit -m "feat: enforce deterministic abstention gates"`.

### Task 6: Finalizer

**Files:** Create `src/ansim_review/abstention/finalizer.py`; test `tests/integration/abstention/test_finalizer.py`.

- [ ] Test complete run yields `READY_FOR_HUMAN_REVIEW` with `human_decision is None`; Track B rejection yields `ABSTAIN`.
- [ ] Run and observe failure.
- [ ] Verify every input artifact against `run-manifest.json`; write `final-review-packet.json` only after all validators pass; refuse overwrite.
- [ ] Run all LLM/confidence/abstention integration tests.
- [ ] Commit: `git commit -m "feat: finalize review packets with abstention"`.
