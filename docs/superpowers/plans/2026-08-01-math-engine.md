# Deterministic Math Engine Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Own every arithmetic operation, comparison, rounding rule, and display value in a versioned Decimal engine.

**Architecture:** Registered formula functions accept string-encoded decimal inputs and return canonical result objects with formula/version, inputs, substitution, raw result, display result, comparison, manifest hash, and result hash.

**Tech Stack:** Python 3.11+, decimal, dataclasses, JSON, pytest.

## Global Constraints

- Reject Python float inputs and free-form expressions.
- Rule code references Math Engine results; it never repeats arithmetic.
- LLM text may quote only registered result values or cited source values.
- Threshold comparison uses raw values, never rounded display values.

---

### Task 1: Decimal Context and Formula Registry

**Files:** Create `src/ansim_review/math_engine/decimal_context.py`, `src/ansim_review/math_engine/registry.py`; test `tests/unit/math_engine/test_registry.py`.

- [ ] Write a test rejecting duplicate `formula_id@version` registration.
- [ ] Run and observe failure.
- [ ] Implement `FormulaSpec` and local Decimal contexts; never mutate global context.
- [ ] Run registry/type tests.
- [ ] Commit: `git commit -m "feat: add versioned math formula registry"`.

### Task 2: Frontage Ratio Formula V1

**Files:** Create `src/ansim_review/math_engine/formulas.py`, `tests/golden/math/frontage_ratio_cases.json`; test `tests/unit/math_engine/test_frontage_ratio.py`.

**Interfaces:** `FRONTAGE_RATIO@1.0.0`, inputs `frontage_length_m`, `perimeter_length_m`, `threshold_ratio`.

- [ ] Write the failing exact test:

```python
result = run_calculation("FRONTAGE_RATIO", "1.0.0", {
    "frontage_length_m": "30", "perimeter_length_m": "320", "threshold_ratio": "0.125"
})
assert result.raw_result == "0.09375"
assert result.display_result == "9.375%"
assert result.comparison == "BELOW_THRESHOLD"
```

- [ ] Run and observe failure.
- [ ] Implement exact Decimal division; percent display has at most three decimals and strips trailing zeros.
- [ ] Run boundary tests at exactly `0.125`, below, above, and invalid perimeter.
- [ ] Commit: `git commit -m "feat: add deterministic frontage ratio calculation"`.

### Task 3: Strict Requests and Structured Errors

**Files:** Create `src/ansim_review/math_engine/requests.py`, `src/ansim_review/math_engine/runner.py`; test `tests/unit/math_engine/test_input_validation.py`.

- [ ] Test that float input raises `decimal inputs must be strings` and zero denominator returns `DIVISION_BY_ZERO` without a numeric result.
- [ ] Run and observe failure.
- [ ] Implement explicit request decoding and statuses `SUCCESS`, `INVALID_INPUT`, `DIVISION_BY_ZERO`, `FORMULA_NOT_FOUND`, `ENGINE_ERROR`.
- [ ] Run unit tests.
- [ ] Commit: `git commit -m "feat: validate deterministic calculation requests"`.

### Task 4: Formula Manifest and Result Hashes

**Files:** Create `src/ansim_review/math_engine/manifest.py`; test `tests/unit/math_engine/test_manifest.py`.

- [ ] Test that formula registration order does not change the manifest hash.
- [ ] Run and observe failure.
- [ ] Canonically hash formula ID, version, precision, rounding, input schema, and output policy.
- [ ] Add formula manifest and result hashes to each CalculationResult.
- [ ] Commit: `git commit -m "feat: hash formula manifests and results"`.

### Task 5: Math CLI and Golden Reproducibility

**Files:** Modify `src/ansim_review/cli.py`; test `tests/integration/math_engine/test_math_cli.py`.

**Interface:** `python -m ansim_review math-run --request request.json --output result.json`.

- [ ] Write a test running the command twice and asserting byte-identical outputs.
- [ ] Run and observe missing-command failure.
- [ ] Implement canonical output, no overwrite, exit code 2 for invalid request and 3 for engine error.
- [ ] Run all Math Engine tests twice.
- [ ] Commit: `git commit -m "feat: expose deterministic math cli"`.
