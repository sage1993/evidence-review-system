# Rule-as-Code Engine Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Execute human-approved, source-backed regulatory rules as reproducible JSON expression trees.

**Architecture:** A constrained loader accepts only declared node/operator types. Rules use project inputs and registered Math Engine results, resolve governing citations before execution, and return machine evaluation statuses without filling the human decision.

**Tech Stack:** Python 3.11+, JSON, dataclasses, Decimal values supplied by Math Engine, pytest.

## Global Constraints

- Only rules in `rules/approved/` and the active manifest execute.
- No `eval`, Python expressions, arbitrary functions, or inferred missing inputs.
- Every rule has resolvable document/revision/page/element/hash citations.
- Candidate rules require explicit human promotion.

---

### Task 1: Constrained Rule Schema

**Files:** Create `src/ansim_review/rule_engine/schema.py`, `src/ansim_review/rule_engine/loader.py`; test `tests/unit/rule_engine/test_loader.py`.

- [ ] Write a test rejecting `{"python": "__import__('os')"}` with `unsupported rule node`.
- [ ] Run and observe failure.
- [ ] Implement nodes `all`, `any`, `not`, `compare`, `exists`, `calculation`; operators `eq`, `ne`, `gt`, `gte`, `lt`, `lte`, `in`, `contains`.
- [ ] Require source citations, input schema, version, and `human_decision_required: true`.
- [ ] Commit: `git commit -m "feat: define constrained rule schema"`.

### Task 2: Deterministic Evaluator

**Files:** Create `src/ansim_review/rule_engine/operators.py`, `src/ansim_review/rule_engine/evaluator.py`; test `tests/unit/rule_engine/test_evaluator.py`.

- [ ] Test missing required input returns `INDETERMINATE` with exact missing field list; same input yields same result hash.
- [ ] Run and observe failure.
- [ ] Implement typed comparisons without truthy coercion; false=`NOT_SATISFIED`, true=`SATISFIED`.
- [ ] Run unit and property-style boundary tests.
- [ ] Commit: `git commit -m "feat: evaluate rules with explicit statuses"`.

### Task 3: Math Result References

**Files:** Modify `src/ansim_review/rule_engine/evaluator.py`; test `tests/integration/rule_engine/test_rule_math_integration.py`.

- [ ] Test the frontage rule consumes `calculation_result_id` and returns `NOT_SATISFIED` for 30/320.
- [ ] Run and observe failure.
- [ ] Resolve registered calculation fields and verify result/formula manifest hashes; do not recalculate.
- [ ] Run integration tests.
- [ ] Commit: `git commit -m "feat: bind rules to deterministic calculations"`.

### Task 4: Source Citation Gate

**Files:** Modify `src/ansim_review/rule_engine/evaluator.py`; test `tests/integration/rule_engine/test_rule_source_gate.py`.

- [ ] Test an unresolved or source-hash-mismatched citation returns `ENGINE_ERROR/UNRESOLVED_RULE_SOURCE`.
- [ ] Run and observe failure.
- [ ] Resolve by document revision, page, evidence ID, bbox, and source hash; quote text alone is not identity.
- [ ] Run source-gate tests.
- [ ] Commit: `git commit -m "feat: require source-backed executable rules"`.

### Task 5: Candidate Promotion and Active Manifest

**Files:** Create `src/ansim_review/rule_engine/promotion.py`, `src/ansim_review/rule_engine/manifest.py`, `rules/manifests/active.json`; test `tests/unit/rule_engine/test_promotion.py`.

- [ ] Test a candidate cannot be promoted without human reviewer identity and review date.
- [ ] Run and observe failure.
- [ ] Copy candidates to `<rule_id>@<version>.json`, hash files, and update the manifest without editing candidates in place.
- [ ] Run tests and verify only manifested approved rules load.
- [ ] Commit: `git commit -m "feat: add human-approved rule promotion"`.

### Task 6: Representative Ansim Rules

**Files:** Add candidate/approved rules and `tests/golden/rules/ansim_representative_cases.json`.

**Coverage:** two road sides >=6 m, arterial frontage >=1/8, minimum site area >=1500 m², plus missing inputs and boundary equality.

- [ ] Write golden expected engine outputs before rule files.
- [ ] Run and observe absent-rule failures.
- [ ] Create source-backed candidates using migrated evidence IDs; promote through the human command.
- [ ] Run cases twice and compare result bytes.
- [ ] Commit: `git commit -m "feat: add source-backed ansim housing rules"`.
