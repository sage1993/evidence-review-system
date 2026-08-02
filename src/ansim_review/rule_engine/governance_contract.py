"""Strict versioned contracts for governed rule activation."""

from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import PurePosixPath
from typing import Literal, TypeAlias, cast

from ansim_review.canonical_json import dump_bytes
from ansim_review.contracts.formats import (
    ACTIVE_RULE_MANIFEST_FORMAT,
    RULE_ACTIVATION_APPROVAL_FORMAT,
    RULE_GOLDEN_REPORT_FORMAT,
)
from ansim_review.contracts.identifiers import validate_identifier, validate_version

GoldenStatus: TypeAlias = Literal["PASS", "FAIL"]
ActivationStatus: TypeAlias = Literal["ACTIVATED", "BLOCKED"]
SelectionStatus: TypeAlias = Literal["SELECTED", "ABSTAIN", "BLOCKED"]
ExclusionCode: TypeAlias = Literal["MISSING_SCOPE_VALUE", "SCOPE_MISMATCH"]

_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_COMMIT_SHA = re.compile(r"^[0-9a-f]{40}$")
_SCOPE_FIELDS = frozenset(
    {"document_family", "document_kind", "jurisdiction", "program"}
)


@dataclass(frozen=True, slots=True)
class RuleScope:
    document_family: str
    document_kind: str | None = None
    jurisdiction: str | None = None
    program: str | None = None


@dataclass(frozen=True, slots=True)
class GoldenCaseRecord:
    case_id: str
    fixture_path: str
    fixture_sha256: str
    expected_path: str
    expected_sha256: str
    actual_path: str
    actual_sha256: str
    status: GoldenStatus


@dataclass(frozen=True, slots=True)
class RuleGoldenReport:
    rule_id: str
    rule_version: str
    candidate_path: str
    candidate_sha256: str
    approved_rule_path: str
    approved_rule_sha256: str
    runner_version: str
    source_commit: str
    command: str
    fixture_manifest_path: str
    fixture_manifest_sha256: str
    case_count: int
    passed_count: int
    failed_count: int
    status: GoldenStatus
    cases: tuple[GoldenCaseRecord, ...]


@dataclass(frozen=True, slots=True)
class RuleActivationApproval:
    rule_id: str
    rule_version: str
    candidate_path: str
    candidate_sha256: str
    approved_rule_path: str
    approved_rule_sha256: str
    golden_report_path: str
    golden_report_sha256: str
    scope: RuleScope
    reviewer_id: str
    reviewed_at: str
    decision: Literal["APPROVED"]
    reason: str


@dataclass(frozen=True, slots=True)
class ActiveRuleEntry:
    rule_id: str
    rule_version: str
    candidate_path: str
    candidate_sha256: str
    approved_rule_path: str
    approved_rule_sha256: str
    golden_report_path: str
    golden_report_sha256: str
    approval_path: str
    approval_sha256: str
    scope: RuleScope
    reviewer_id: str
    reviewed_at: str
    reason: str


@dataclass(frozen=True, slots=True)
class ActiveRuleManifest:
    rules: tuple[ActiveRuleEntry, ...]


@dataclass(frozen=True, slots=True)
class ActivationFinding:
    artifact_path: str | None
    rule_id: str | None
    code: str
    message: str


@dataclass(frozen=True, slots=True)
class ActivationReport:
    status: ActivationStatus
    approval_count: int
    activated_rule_count: int
    approval_files: tuple[str, ...]
    findings: tuple[ActivationFinding, ...]
    active_manifest_sha256: str | None


@dataclass(frozen=True, slots=True)
class RuleSelectionContext:
    document_family: str | None = None
    document_kind: str | None = None
    jurisdiction: str | None = None
    program: str | None = None


@dataclass(frozen=True, slots=True)
class ExcludedRule:
    rule_id: str
    rule_version: str
    code: ExclusionCode


@dataclass(frozen=True, slots=True)
class SelectedRule:
    rule_id: str
    rule_version: str
    approved_rule_path: str
    approved_rule_sha256: str
    scope: RuleScope


@dataclass(frozen=True, slots=True)
class RuleSelectionResult:
    status: SelectionStatus
    context: RuleSelectionContext
    manifest_sha256: str | None
    selected_rules: tuple[SelectedRule, ...]
    excluded_rules: tuple[ExcludedRule, ...]
    reasons: tuple[str, ...]


JsonObject: TypeAlias = dict[str, object]


def _duplicate_free_object(pairs: list[tuple[str, object]]) -> JsonObject:
    result: JsonObject = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _load_object(data: bytes, label: str) -> JsonObject:
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as error:
        raise ValueError(f"{label} must be UTF-8") from error
    try:
        value: object = json.loads(text, object_pairs_hook=_duplicate_free_object)
    except json.JSONDecodeError as error:
        raise ValueError(f"{label} must be valid JSON") from error
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise ValueError(f"{label} must be an object")
    return cast(JsonObject, value)


def _object(value: object, field: str) -> JsonObject:
    if not isinstance(value, Mapping) or not all(isinstance(key, str) for key in value):
        raise ValueError(f"{field} must be an object")
    return dict(cast(Mapping[str, object], value))


def _array(value: object, field: str) -> list[object]:
    if isinstance(value, (str, bytes, bytearray)) or not isinstance(value, Sequence):
        raise ValueError(f"{field} must be an array")
    return list(cast(Sequence[object], value))


def _exact_fields(payload: Mapping[str, object], expected: frozenset[str], label: str) -> None:
    actual = set(payload)
    unknown = sorted(actual - expected)
    if unknown:
        raise ValueError(f"{label} has unknown fields: {', '.join(unknown)}")
    missing = sorted(expected - actual)
    if missing:
        raise ValueError(f"{label} is missing fields: {', '.join(missing)}")


def _trimmed_string(value: object, field: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{field} must be a string")
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{field} must be non-empty")
    return normalized


def _integer(value: object, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{field} must be an integer")
    if value < 0:
        raise ValueError(f"{field} must be non-negative")
    return value


def _sha256(value: object, field: str) -> str:
    if not isinstance(value, str) or _SHA256.fullmatch(value) is None:
        raise ValueError(f"{field} must be a lowercase SHA-256")
    return value


def _source_commit(value: object) -> str:
    if not isinstance(value, str) or _COMMIT_SHA.fullmatch(value) is None:
        raise ValueError("source_commit must be a lowercase 40-character commit SHA")
    return value


def _safe_path(value: object, field: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{field} must be a repository-relative POSIX path")
    if "\\" in value or ":" in value or "\x00" in value:
        raise ValueError(f"{field} must be a repository-relative POSIX path")
    path = PurePosixPath(value)
    if path.is_absolute() or value != path.as_posix() or any(part == ".." for part in path.parts):
        raise ValueError(f"{field} must be a repository-relative POSIX path")
    if value in {".", ".."}:
        raise ValueError(f"{field} must be a repository-relative POSIX path")
    return value


def _timestamp(value: object, field: str) -> str:
    text = _trimmed_string(value, field)
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError as error:
        raise ValueError(f"{field} must be an ISO 8601 timestamp") from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"{field} must include a timezone offset")
    return text


def _status(value: object, field: str) -> GoldenStatus:
    if value not in {"PASS", "FAIL"}:
        raise ValueError(f"{field} must be PASS or FAIL")
    return cast(GoldenStatus, value)


def _load_scope(value: object, field: str = "scope") -> RuleScope:
    payload = _object(value, field)
    _exact_fields(payload, frozenset(payload) | {"document_family"}, field)
    unknown = sorted(set(payload) - _SCOPE_FIELDS)
    if unknown:
        raise ValueError(f"{field} has unknown fields: {', '.join(unknown)}")
    if "document_family" not in payload:
        raise ValueError(f"{field}.document_family is required")

    def optional(name: str) -> str | None:
        if name not in payload:
            return None
        return _trimmed_string(payload[name], f"{field}.{name}")

    return RuleScope(
        document_family=_trimmed_string(
            payload["document_family"], f"{field}.document_family"
        ),
        document_kind=optional("document_kind"),
        jurisdiction=optional("jurisdiction"),
        program=optional("program"),
    )


def _scope_payload(scope: RuleScope) -> JsonObject:
    payload: JsonObject = {"document_family": scope.document_family}
    if scope.document_kind is not None:
        payload["document_kind"] = scope.document_kind
    if scope.jurisdiction is not None:
        payload["jurisdiction"] = scope.jurisdiction
    if scope.program is not None:
        payload["program"] = scope.program
    return payload


def _load_case(value: object, index: int) -> GoldenCaseRecord:
    field = f"golden report.cases[{index}]"
    payload = _object(value, field)
    expected = frozenset(
        {
            "case_id",
            "fixture_path",
            "fixture_sha256",
            "expected_path",
            "expected_sha256",
            "actual_path",
            "actual_sha256",
            "status",
        }
    )
    _exact_fields(payload, expected, "golden case")
    status = _status(payload["status"], f"{field}.status")
    expected_hash = _sha256(payload["expected_sha256"], f"{field}.expected_sha256")
    actual_hash = _sha256(payload["actual_sha256"], f"{field}.actual_sha256")
    if status == "PASS" and expected_hash != actual_hash:
        raise ValueError("PASS golden case hashes must match")
    return GoldenCaseRecord(
        case_id=validate_identifier(payload["case_id"], f"{field}.case_id"),
        fixture_path=_safe_path(payload["fixture_path"], f"{field}.fixture_path"),
        fixture_sha256=_sha256(payload["fixture_sha256"], f"{field}.fixture_sha256"),
        expected_path=_safe_path(payload["expected_path"], f"{field}.expected_path"),
        expected_sha256=expected_hash,
        actual_path=_safe_path(payload["actual_path"], f"{field}.actual_path"),
        actual_sha256=actual_hash,
        status=status,
    )


def load_rule_golden_report_bytes(data: bytes) -> RuleGoldenReport:
    """Strictly decode one version 1 rule golden report."""
    payload = _load_object(data, "golden report")
    expected = frozenset(
        {
            "format",
            "version",
            "rule_id",
            "rule_version",
            "candidate_path",
            "candidate_sha256",
            "approved_rule_path",
            "approved_rule_sha256",
            "runner_version",
            "source_commit",
            "command",
            "fixture_manifest_path",
            "fixture_manifest_sha256",
            "case_count",
            "passed_count",
            "failed_count",
            "status",
            "cases",
        }
    )
    _exact_fields(payload, expected, "golden report")
    if payload["format"] != RULE_GOLDEN_REPORT_FORMAT or payload["version"] != 1:
        raise ValueError("unsupported golden report format or version")
    cases = tuple(
        _load_case(item, index)
        for index, item in enumerate(_array(payload["cases"], "golden report.cases"))
    )
    case_ids = [item.case_id for item in cases]
    if len(case_ids) != len(set(case_ids)):
        raise ValueError("duplicate golden case_id")
    case_count = _integer(payload["case_count"], "golden report.case_count")
    passed_count = _integer(payload["passed_count"], "golden report.passed_count")
    failed_count = _integer(payload["failed_count"], "golden report.failed_count")
    actual_passed = sum(item.status == "PASS" for item in cases)
    actual_failed = sum(item.status == "FAIL" for item in cases)
    if (
        case_count == 0
        or case_count != len(cases)
        or passed_count != actual_passed
        or failed_count != actual_failed
        or passed_count + failed_count != case_count
    ):
        raise ValueError("golden report counts are inconsistent")
    status = _status(payload["status"], "golden report.status")
    expected_status: GoldenStatus = "PASS" if failed_count == 0 else "FAIL"
    if status != expected_status:
        raise ValueError("golden report status is inconsistent with case results")
    return RuleGoldenReport(
        rule_id=validate_identifier(payload["rule_id"], "golden report.rule_id"),
        rule_version=validate_version(payload["rule_version"], "golden report.rule_version"),
        candidate_path=_safe_path(payload["candidate_path"], "golden report.candidate_path"),
        candidate_sha256=_sha256(
            payload["candidate_sha256"], "golden report.candidate_sha256"
        ),
        approved_rule_path=_safe_path(
            payload["approved_rule_path"], "golden report.approved_rule_path"
        ),
        approved_rule_sha256=_sha256(
            payload["approved_rule_sha256"], "golden report.approved_rule_sha256"
        ),
        runner_version=_trimmed_string(
            payload["runner_version"], "golden report.runner_version"
        ),
        source_commit=_source_commit(payload["source_commit"]),
        command=_trimmed_string(payload["command"], "golden report.command"),
        fixture_manifest_path=_safe_path(
            payload["fixture_manifest_path"], "golden report.fixture_manifest_path"
        ),
        fixture_manifest_sha256=_sha256(
            payload["fixture_manifest_sha256"],
            "golden report.fixture_manifest_sha256",
        ),
        case_count=case_count,
        passed_count=passed_count,
        failed_count=failed_count,
        status=status,
        cases=cases,
    )


def _golden_case_payload(case: GoldenCaseRecord) -> JsonObject:
    return {
        "case_id": case.case_id,
        "fixture_path": case.fixture_path,
        "fixture_sha256": case.fixture_sha256,
        "expected_path": case.expected_path,
        "expected_sha256": case.expected_sha256,
        "actual_path": case.actual_path,
        "actual_sha256": case.actual_sha256,
        "status": case.status,
    }


def rule_golden_report_bytes(report: RuleGoldenReport) -> bytes:
    """Serialize one golden report to canonical JSON bytes."""
    return dump_bytes(
        {
            "format": RULE_GOLDEN_REPORT_FORMAT,
            "version": 1,
            "rule_id": report.rule_id,
            "rule_version": report.rule_version,
            "candidate_path": report.candidate_path,
            "candidate_sha256": report.candidate_sha256,
            "approved_rule_path": report.approved_rule_path,
            "approved_rule_sha256": report.approved_rule_sha256,
            "runner_version": report.runner_version,
            "source_commit": report.source_commit,
            "command": report.command,
            "fixture_manifest_path": report.fixture_manifest_path,
            "fixture_manifest_sha256": report.fixture_manifest_sha256,
            "case_count": report.case_count,
            "passed_count": report.passed_count,
            "failed_count": report.failed_count,
            "status": report.status,
            "cases": [_golden_case_payload(item) for item in report.cases],
        }
    )


def load_rule_activation_approval_bytes(data: bytes) -> RuleActivationApproval:
    """Strictly decode one version 1 human activation approval."""
    payload = _load_object(data, "activation approval")
    expected = frozenset(
        {
            "format",
            "version",
            "rule_id",
            "rule_version",
            "candidate_path",
            "candidate_sha256",
            "approved_rule_path",
            "approved_rule_sha256",
            "golden_report_path",
            "golden_report_sha256",
            "scope",
            "reviewer_id",
            "reviewed_at",
            "decision",
            "reason",
        }
    )
    _exact_fields(payload, expected, "activation approval")
    if payload["format"] != RULE_ACTIVATION_APPROVAL_FORMAT or payload["version"] != 1:
        raise ValueError("unsupported activation approval format or version")
    if payload["decision"] != "APPROVED":
        raise ValueError("activation approval decision must be APPROVED")
    return RuleActivationApproval(
        rule_id=validate_identifier(payload["rule_id"], "activation approval.rule_id"),
        rule_version=validate_version(
            payload["rule_version"], "activation approval.rule_version"
        ),
        candidate_path=_safe_path(
            payload["candidate_path"], "activation approval.candidate_path"
        ),
        candidate_sha256=_sha256(
            payload["candidate_sha256"], "activation approval.candidate_sha256"
        ),
        approved_rule_path=_safe_path(
            payload["approved_rule_path"], "activation approval.approved_rule_path"
        ),
        approved_rule_sha256=_sha256(
            payload["approved_rule_sha256"],
            "activation approval.approved_rule_sha256",
        ),
        golden_report_path=_safe_path(
            payload["golden_report_path"], "activation approval.golden_report_path"
        ),
        golden_report_sha256=_sha256(
            payload["golden_report_sha256"],
            "activation approval.golden_report_sha256",
        ),
        scope=_load_scope(payload["scope"]),
        reviewer_id=_trimmed_string(
            payload["reviewer_id"], "activation approval.reviewer_id"
        ),
        reviewed_at=_timestamp(
            payload["reviewed_at"], "activation approval.reviewed_at"
        ),
        decision="APPROVED",
        reason=_trimmed_string(payload["reason"], "activation approval.reason"),
    )


def rule_activation_approval_bytes(approval: RuleActivationApproval) -> bytes:
    """Serialize one activation approval to canonical JSON bytes."""
    return dump_bytes(
        {
            "format": RULE_ACTIVATION_APPROVAL_FORMAT,
            "version": 1,
            "rule_id": approval.rule_id,
            "rule_version": approval.rule_version,
            "candidate_path": approval.candidate_path,
            "candidate_sha256": approval.candidate_sha256,
            "approved_rule_path": approval.approved_rule_path,
            "approved_rule_sha256": approval.approved_rule_sha256,
            "golden_report_path": approval.golden_report_path,
            "golden_report_sha256": approval.golden_report_sha256,
            "scope": _scope_payload(approval.scope),
            "reviewer_id": approval.reviewer_id,
            "reviewed_at": approval.reviewed_at,
            "decision": approval.decision,
            "reason": approval.reason,
        }
    )


def _load_active_entry(value: object, index: int) -> ActiveRuleEntry:
    field = f"active manifest.rules[{index}]"
    payload = _object(value, field)
    expected = frozenset(
        {
            "rule_id",
            "rule_version",
            "candidate_path",
            "candidate_sha256",
            "approved_rule_path",
            "approved_rule_sha256",
            "golden_report_path",
            "golden_report_sha256",
            "approval_path",
            "approval_sha256",
            "scope",
            "reviewer_id",
            "reviewed_at",
            "reason",
        }
    )
    _exact_fields(payload, expected, "active rule entry")
    return ActiveRuleEntry(
        rule_id=validate_identifier(payload["rule_id"], f"{field}.rule_id"),
        rule_version=validate_version(payload["rule_version"], f"{field}.rule_version"),
        candidate_path=_safe_path(payload["candidate_path"], f"{field}.candidate_path"),
        candidate_sha256=_sha256(
            payload["candidate_sha256"], f"{field}.candidate_sha256"
        ),
        approved_rule_path=_safe_path(
            payload["approved_rule_path"], f"{field}.approved_rule_path"
        ),
        approved_rule_sha256=_sha256(
            payload["approved_rule_sha256"], f"{field}.approved_rule_sha256"
        ),
        golden_report_path=_safe_path(
            payload["golden_report_path"], f"{field}.golden_report_path"
        ),
        golden_report_sha256=_sha256(
            payload["golden_report_sha256"], f"{field}.golden_report_sha256"
        ),
        approval_path=_safe_path(payload["approval_path"], f"{field}.approval_path"),
        approval_sha256=_sha256(
            payload["approval_sha256"], f"{field}.approval_sha256"
        ),
        scope=_load_scope(payload["scope"], f"{field}.scope"),
        reviewer_id=_trimmed_string(payload["reviewer_id"], f"{field}.reviewer_id"),
        reviewed_at=_timestamp(payload["reviewed_at"], f"{field}.reviewed_at"),
        reason=_trimmed_string(payload["reason"], f"{field}.reason"),
    )


def _semantic_version_key(version: str) -> tuple[int, int, int, int, tuple[str, ...]]:
    without_build = version.split("+", 1)[0]
    base, separator, prerelease = without_build.partition("-")
    major, minor, patch = (int(part) for part in base.split("."))
    return (major, minor, patch, 1 if not separator else 0, tuple(prerelease.split(".")))


def _entry_sort_key(entry: ActiveRuleEntry) -> tuple[object, ...]:
    return (entry.rule_id, _semantic_version_key(entry.rule_version), entry.approval_path)


def load_active_rule_manifest_bytes(data: bytes) -> ActiveRuleManifest:
    """Strictly decode the derived version 2 active rule manifest."""
    payload = _load_object(data, "active manifest")
    if set(payload) == {"rules"}:
        raise ValueError("legacy active rule manifest is not supported")
    expected = frozenset({"format", "version", "rules"})
    _exact_fields(payload, expected, "active manifest")
    if payload["format"] != ACTIVE_RULE_MANIFEST_FORMAT or payload["version"] != 2:
        raise ValueError("unsupported active rule manifest format or version")
    rules = tuple(
        _load_active_entry(item, index)
        for index, item in enumerate(_array(payload["rules"], "active manifest.rules"))
    )
    rule_ids = [item.rule_id for item in rules]
    if len(rule_ids) != len(set(rule_ids)):
        raise ValueError("duplicate active rule_id")
    approval_paths = [item.approval_path.casefold() for item in rules]
    if len(approval_paths) != len(set(approval_paths)):
        raise ValueError("duplicate active approval_path")
    approval_hashes = [item.approval_sha256 for item in rules]
    if len(approval_hashes) != len(set(approval_hashes)):
        raise ValueError("duplicate active approval_sha256")
    if list(rules) != sorted(rules, key=_entry_sort_key):
        raise ValueError("active manifest rules must be sorted")
    return ActiveRuleManifest(rules=rules)


def _active_entry_payload(entry: ActiveRuleEntry) -> JsonObject:
    return {
        "rule_id": entry.rule_id,
        "rule_version": entry.rule_version,
        "candidate_path": entry.candidate_path,
        "candidate_sha256": entry.candidate_sha256,
        "approved_rule_path": entry.approved_rule_path,
        "approved_rule_sha256": entry.approved_rule_sha256,
        "golden_report_path": entry.golden_report_path,
        "golden_report_sha256": entry.golden_report_sha256,
        "approval_path": entry.approval_path,
        "approval_sha256": entry.approval_sha256,
        "scope": _scope_payload(entry.scope),
        "reviewer_id": entry.reviewer_id,
        "reviewed_at": entry.reviewed_at,
        "reason": entry.reason,
    }


def active_rule_manifest_bytes(manifest: ActiveRuleManifest) -> bytes:
    """Serialize one derived active manifest to canonical JSON bytes."""
    return dump_bytes(
        {
            "format": ACTIVE_RULE_MANIFEST_FORMAT,
            "version": 2,
            "rules": [_active_entry_payload(item) for item in manifest.rules],
        }
    )
