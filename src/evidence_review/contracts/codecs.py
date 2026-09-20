"""Explicit type-checked decoders for untrusted JSON payloads."""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from typing import cast

from evidence_review.contracts.common import BBox, Citation
from evidence_review.contracts.engines import (
    CalculationComparison,
    CalculationResult,
    CalculationStatus,
    RuleResult,
    RuleStatus,
)
from evidence_review.contracts.review import (
    Claim,
    ConfidenceFactor,
    ConfidenceFactorState,
    ConfidenceLevel,
    ConfidenceResult,
    FinalizerStatus,
    IssueResult,
    IssueStatus,
    ReviewPacket,
)

_SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
_ISSUE_STATUSES: tuple[IssueStatus, ...] = (
    "RESOLVED",
    "CONDITIONAL",
    "CONFLICT",
    "SOURCE_MISSING",
    "UNRESOLVED",
)


def _expect_mapping(value: object, field: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{field} must be an object")
    if not all(isinstance(key, str) for key in value):
        raise ValueError(f"{field} keys must be strings")
    return cast(Mapping[str, object], value)


def _expect_sequence(value: object, field: str) -> Sequence[object]:
    if isinstance(value, (str, bytes, bytearray)) or not isinstance(value, Sequence):
        raise ValueError(f"{field} must be an array")
    return cast(Sequence[object], value)


def _expect_string(value: object, field: str, *, allow_empty: bool = False) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{field} must be a string")
    if not allow_empty and not value:
        raise ValueError(f"{field} must not be empty")
    return value


def _expect_optional_string(value: object, field: str) -> str | None:
    if value is None:
        return None
    return _expect_string(value, field, allow_empty=True)


def _expect_int(value: object, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{field} must be an integer")
    return value


def _expect_number(value: object, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{field} must be a number")
    result = float(value)
    if result != result or result in (float("inf"), float("-inf")):
        raise ValueError(f"{field} must be finite")
    return result


def _expect_literal[T: str](value: object, field: str, allowed: tuple[T, ...]) -> T:
    candidate = _expect_string(value, field)
    if candidate not in allowed:
        raise ValueError(f"unsupported {field}: {candidate}")
    return candidate


def _expect_string_tuple(value: object, field: str) -> tuple[str, ...]:
    items = _expect_sequence(value, field)
    return tuple(_expect_string(item, f"{field}[{index}]") for index, item in enumerate(items))


def _expect_unique_string_tuple(value: object, field: str) -> tuple[str, ...]:
    items = _expect_string_tuple(value, field)
    if len(items) != len(set(items)):
        raise ValueError(f"{field} must contain unique values")
    return items


def _expect_string_dict(value: object, field: str) -> dict[str, str]:
    payload = _expect_mapping(value, field)
    return {
        key: _expect_string(item, f"{field}.{key}", allow_empty=True)
        for key, item in payload.items()
    }


def _reject_unknown(payload: Mapping[str, object], allowed: set[str], field: str) -> None:
    unknown = sorted(set(payload) - allowed)
    if unknown:
        raise ValueError(f"{field} has unknown fields: {', '.join(unknown)}")


def decode_bbox(value: object) -> BBox:
    """Decode a canonical four-number bounding box."""
    items = _expect_sequence(value, "bbox")
    if len(items) != 4:
        raise ValueError("bbox must contain four numbers")
    return BBox(
        left=_expect_number(items[0], "bbox[0]"),
        bottom=_expect_number(items[1], "bbox[1]"),
        right=_expect_number(items[2], "bbox[2]"),
        top=_expect_number(items[3], "bbox[3]"),
    )


def decode_citation(value: object) -> Citation:
    """Decode a resolved evidence citation."""
    payload = _expect_mapping(value, "citation")
    allowed = {
        "citation_id",
        "document_id",
        "revision_id",
        "page_number",
        "evidence_id",
        "bbox",
        "source_hash",
    }
    _reject_unknown(payload, allowed, "citation")
    page_number = _expect_int(payload.get("page_number"), "page_number")
    if page_number < 1:
        raise ValueError("page_number must be positive")
    source_hash = _expect_string(payload.get("source_hash"), "source_hash")
    if not _SHA256_PATTERN.fullmatch(source_hash):
        raise ValueError("source_hash must be a lowercase SHA-256 digest")
    return Citation(
        citation_id=_expect_string(payload.get("citation_id"), "citation_id"),
        document_id=_expect_string(payload.get("document_id"), "document_id"),
        revision_id=_expect_string(payload.get("revision_id"), "revision_id"),
        page_number=page_number,
        evidence_id=_expect_string(payload.get("evidence_id"), "evidence_id"),
        bbox=decode_bbox(payload.get("bbox")),
        source_hash=source_hash,
    )


def decode_claim(value: object) -> Claim:
    """Decode one cited factual claim, preserving optional issue lineage."""
    payload = _expect_mapping(value, "claim")
    _reject_unknown(
        payload,
        {"claim_id", "text", "citation_ids", "numeric_tokens", "issue_ids", "fulfilled_facet_ids"},
        "claim",
    )
    return Claim(
        claim_id=_expect_string(payload.get("claim_id"), "claim_id"),
        text=_expect_string(payload.get("text"), "text"),
        citation_ids=_expect_string_tuple(payload.get("citation_ids"), "citation_ids"),
        numeric_tokens=_expect_string_tuple(payload.get("numeric_tokens", []), "numeric_tokens"),
        issue_ids=_expect_unique_string_tuple(payload.get("issue_ids", []), "issue_ids"),
        fulfilled_facet_ids=_expect_unique_string_tuple(
            payload.get("fulfilled_facet_ids", []), "fulfilled_facet_ids"
        ),
    )


def decode_issue_result(value: object) -> IssueResult:
    """Decode one deterministic planned-issue coverage result."""
    payload = _expect_mapping(value, "issue_result")
    allowed = {
        "issue_id",
        "status",
        "evidence_ids",
        "covered_roles",
        "missing_roles",
        "gap_codes",
        "covered_facet_ids",
        "missing_facet_ids",
        "comparison_ids",
    }
    _reject_unknown(payload, allowed, "issue_result")
    return IssueResult(
        issue_id=_expect_string(payload.get("issue_id"), "issue_id"),
        status=_expect_literal(payload.get("status"), "status", _ISSUE_STATUSES),
        evidence_ids=_expect_unique_string_tuple(payload.get("evidence_ids", []), "evidence_ids"),
        covered_roles=_expect_unique_string_tuple(
            payload.get("covered_roles", []), "covered_roles"
        ),
        missing_roles=_expect_unique_string_tuple(
            payload.get("missing_roles", []), "missing_roles"
        ),
        gap_codes=_expect_unique_string_tuple(payload.get("gap_codes", []), "gap_codes"),
        covered_facet_ids=_expect_unique_string_tuple(
            payload.get("covered_facet_ids", []), "covered_facet_ids"
        ),
        missing_facet_ids=_expect_unique_string_tuple(
            payload.get("missing_facet_ids", []), "missing_facet_ids"
        ),
        comparison_ids=_expect_unique_string_tuple(
            payload.get("comparison_ids", []), "comparison_ids"
        ),
    )


def decode_calculation_result(value: object) -> CalculationResult:
    """Decode a Math Engine result without coercing numeric values."""
    payload = _expect_mapping(value, "calculation")
    allowed = {
        "calculation_result_id",
        "status",
        "formula_id",
        "formula_version",
        "inputs",
        "substitution",
        "raw_result",
        "display_result",
        "comparison",
        "formula_manifest_hash",
        "result_hash",
        "error_codes",
        "input_sources",
        "input_units",
        "precision",
        "rounding",
        "intermediate_rounding_policy",
    }
    _reject_unknown(payload, allowed, "calculation")
    status = _expect_literal(
        payload.get("status"),
        "status",
        ("SUCCESS", "INVALID_INPUT", "DIVISION_BY_ZERO", "FORMULA_NOT_FOUND", "ENGINE_ERROR"),
    )
    comparison_value = payload.get("comparison")
    comparison: CalculationComparison | None
    if comparison_value is None:
        comparison = None
    else:
        comparison = cast(
            CalculationComparison,
            _expect_literal(
                comparison_value,
                "comparison",
                (
                    "BELOW_THRESHOLD",
                    "AT_THRESHOLD",
                    "ABOVE_THRESHOLD",
                    "EQUAL",
                    "NOT_EQUAL",
                    "NOT_APPLICABLE",
                ),
            ),
        )
    precision_value = payload.get("precision")
    precision = None if precision_value is None else _expect_int(precision_value, "precision")
    if precision is not None and precision < 1:
        raise ValueError("precision must be a positive integer")
    return CalculationResult(
        calculation_result_id=_expect_string(
            payload.get("calculation_result_id"), "calculation_result_id"
        ),
        status=cast(CalculationStatus, status),
        formula_id=_expect_string(payload.get("formula_id"), "formula_id"),
        formula_version=_expect_string(payload.get("formula_version"), "formula_version"),
        inputs=_expect_string_dict(payload.get("inputs", {}), "inputs"),
        substitution=_expect_optional_string(payload.get("substitution"), "substitution"),
        raw_result=_expect_optional_string(payload.get("raw_result"), "raw_result"),
        display_result=_expect_optional_string(payload.get("display_result"), "display_result"),
        comparison=comparison,
        formula_manifest_hash=_expect_optional_string(
            payload.get("formula_manifest_hash"), "formula_manifest_hash"
        ),
        result_hash=_expect_optional_string(payload.get("result_hash"), "result_hash"),
        error_codes=_expect_string_tuple(payload.get("error_codes", []), "error_codes"),
        input_sources=_expect_string_dict(payload.get("input_sources", {}), "input_sources"),
        input_units=_expect_string_dict(payload.get("input_units", {}), "input_units"),
        precision=precision,
        rounding=_expect_optional_string(payload.get("rounding"), "rounding"),
        intermediate_rounding_policy=_expect_optional_string(
            payload.get("intermediate_rounding_policy"),
            "intermediate_rounding_policy",
        ),
    )


def decode_rule_result(value: object) -> RuleResult:
    """Decode a deterministic Rule Engine result."""
    payload = _expect_mapping(value, "rule")
    allowed = {
        "rule_result_id",
        "rule_id",
        "rule_version",
        "status",
        "citations",
        "missing_inputs",
        "calculation_result_ids",
        "reason_codes",
        "result_hash",
    }
    _reject_unknown(payload, allowed, "rule")
    citations = tuple(
        decode_citation(item)
        for item in _expect_sequence(payload.get("citations", []), "citations")
    )
    status = _expect_literal(
        payload.get("status"),
        "status",
        ("SATISFIED", "NOT_SATISFIED", "INDETERMINATE", "NOT_APPLICABLE", "ENGINE_ERROR"),
    )
    return RuleResult(
        rule_result_id=_expect_string(payload.get("rule_result_id"), "rule_result_id"),
        rule_id=_expect_string(payload.get("rule_id"), "rule_id"),
        rule_version=_expect_string(payload.get("rule_version"), "rule_version"),
        status=cast(RuleStatus, status),
        citations=citations,
        missing_inputs=_expect_string_tuple(payload.get("missing_inputs", []), "missing_inputs"),
        calculation_result_ids=_expect_string_tuple(
            payload.get("calculation_result_ids", []), "calculation_result_ids"
        ),
        reason_codes=_expect_string_tuple(payload.get("reason_codes", []), "reason_codes"),
        result_hash=_expect_optional_string(payload.get("result_hash"), "result_hash"),
    )


def decode_confidence_result(value: object) -> ConfidenceResult:
    """Decode deterministic confidence-policy output."""
    payload = _expect_mapping(value, "confidence")
    _reject_unknown(
        payload,
        {"policy_version", "score", "level", "factors", "hard_gate_failures"},
        "confidence",
    )
    factors: list[ConfidenceFactor] = []
    for index, item in enumerate(_expect_sequence(payload.get("factors"), "factors")):
        factor = _expect_mapping(item, f"factors[{index}]")
        _reject_unknown(
            factor,
            {"name", "value", "weight", "contribution", "source", "state"},
            f"factors[{index}]",
        )
        state = _expect_literal(
            factor.get("state", "VERIFIED"),
            f"factors[{index}].state",
            ("VERIFIED", "FAILED", "NOT_VERIFIED", "NOT_APPLICABLE"),
        )
        factors.append(
            ConfidenceFactor(
                name=_expect_string(factor.get("name"), f"factors[{index}].name"),
                value=_expect_string(factor.get("value"), f"factors[{index}].value"),
                weight=_expect_string(factor.get("weight"), f"factors[{index}].weight"),
                contribution=_expect_string(
                    factor.get("contribution"), f"factors[{index}].contribution"
                ),
                source=_expect_string(factor.get("source"), f"factors[{index}].source"),
                state=cast(ConfidenceFactorState, state),
            )
        )
    level = _expect_literal(payload.get("level"), "level", ("HIGH", "MEDIUM", "LOW"))
    return ConfidenceResult(
        policy_version=_expect_string(payload.get("policy_version"), "policy_version"),
        score=_expect_string(payload.get("score"), "score"),
        level=cast(ConfidenceLevel, level),
        factors=tuple(factors),
        hard_gate_failures=_expect_string_tuple(
            payload.get("hard_gate_failures", []), "hard_gate_failures"
        ),
    )


def decode_review_packet(value: object) -> ReviewPacket:
    """Decode a final machine packet and enforce human decision ownership."""
    payload = _expect_mapping(value, "review_packet")
    if payload.get("human_decision") is not None:
        raise ValueError("human_decision must be null in a machine review packet")
    allowed = {
        "run_id",
        "status",
        "human_decision",
        "question",
        "claims",
        "calculations",
        "rules",
        "confidence",
        "abstention_reasons",
        "snapshot_sha256",
        "missing_inputs",
        "issue_results",
    }
    _reject_unknown(payload, allowed, "review_packet")
    status = _expect_literal(
        payload.get("status"),
        "status",
        ("READY_FOR_HUMAN_REVIEW", "PARTIALLY_RESOLVED", "ABSTAIN"),
    )
    claims = tuple(decode_claim(item) for item in _expect_sequence(payload.get("claims"), "claims"))
    calculations = tuple(
        decode_calculation_result(item)
        for item in _expect_sequence(payload.get("calculations"), "calculations")
    )
    rules = tuple(
        decode_rule_result(item) for item in _expect_sequence(payload.get("rules"), "rules")
    )
    issue_results = tuple(
        decode_issue_result(item)
        for item in _expect_sequence(payload.get("issue_results", []), "issue_results")
    )
    issue_ids = [item.issue_id for item in issue_results]
    if len(issue_ids) != len(set(issue_ids)):
        raise ValueError("issue_results must contain unique issue identifiers")
    confidence_value = payload.get("confidence")
    confidence = None if confidence_value is None else decode_confidence_result(confidence_value)
    snapshot_value = payload.get("snapshot_sha256")
    snapshot_sha256: str | None
    if snapshot_value is None:
        snapshot_sha256 = None
    else:
        snapshot_sha256 = _expect_string(snapshot_value, "snapshot_sha256")
        if not _SHA256_PATTERN.fullmatch(snapshot_sha256):
            raise ValueError("snapshot_sha256 must be a lowercase SHA-256 digest")
    serialized_lineage_fields = tuple(
        name for name in ("snapshot_sha256", "missing_inputs", "issue_results") if name in payload
    )
    return ReviewPacket(
        run_id=_expect_string(payload.get("run_id"), "run_id"),
        status=cast(FinalizerStatus, status),
        human_decision=None,
        question=_expect_string(payload.get("question"), "question"),
        claims=claims,
        calculations=calculations,
        rules=rules,
        confidence=confidence,
        abstention_reasons=_expect_string_tuple(
            payload.get("abstention_reasons"), "abstention_reasons"
        ),
        snapshot_sha256=snapshot_sha256,
        missing_inputs=_expect_string_tuple(payload.get("missing_inputs", []), "missing_inputs"),
        issue_results=issue_results,
        _serialized_lineage_fields=serialized_lineage_fields,
    )
