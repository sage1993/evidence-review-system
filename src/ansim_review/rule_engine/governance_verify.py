"""Fail-closed verification for governed rule activation artifacts."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Literal, TypeAlias, cast

from ansim_review.contracts.identifiers import validate_identifier, validate_version
from ansim_review.rule_engine.governance_contract import (
    ActiveRuleEntry,
    RuleActivationApproval,
    RuleGoldenReport,
    load_rule_activation_approval_bytes,
    load_rule_golden_report_bytes,
)
from ansim_review.rule_engine.loader import load_rule
from ansim_review.rule_engine.schema import RuleSpec

VerificationMode: TypeAlias = Literal["ACTIVATION", "RUNTIME"]
JsonObject: TypeAlias = dict[str, object]


class GovernanceVerificationError(ValueError):
    """One stable fail-closed governance verification failure."""

    def __init__(
        self,
        code: str,
        artifact_path: str | None = None,
        detail: str | None = None,
    ) -> None:
        self.code = code
        self.artifact_path = artifact_path
        self.detail = detail
        parts = [code]
        if artifact_path is not None:
            parts.append(artifact_path)
        if detail:
            parts.append(detail)
        super().__init__(": ".join(parts))


@dataclass(frozen=True, slots=True)
class VerifiedApproval:
    """A complete verified activation authority chain."""

    approval_path: str
    approval: RuleActivationApproval
    rule: RuleSpec
    golden_report: RuleGoldenReport


@dataclass(frozen=True, slots=True)
class _FixtureCase:
    case_id: str
    fixture_path: str
    expected_path: str
    actual_path: str


@dataclass(frozen=True, slots=True)
class _FixtureManifest:
    rule_id: str
    rule_version: str
    candidate_path: str
    approved_rule_path: str
    cases: tuple[_FixtureCase, ...]


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _duplicate_free_object(pairs: list[tuple[str, object]]) -> JsonObject:
    result: JsonObject = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _load_json_object(data: bytes, label: str) -> JsonObject:
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as error:
        raise GovernanceVerificationError(
            f"{label.upper().replace(' ', '_')}_INVALID",
            detail="artifact must be UTF-8",
        ) from error
    try:
        value: object = json.loads(text, object_pairs_hook=_duplicate_free_object)
    except (json.JSONDecodeError, ValueError) as error:
        raise GovernanceVerificationError(
            f"{label.upper().replace(' ', '_')}_INVALID",
            detail=str(error),
        ) from error
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise GovernanceVerificationError(
            f"{label.upper().replace(' ', '_')}_INVALID",
            detail="artifact must be an object",
        )
    return cast(JsonObject, value)


def _object(value: object, field: str) -> JsonObject:
    if not isinstance(value, Mapping) or not all(isinstance(key, str) for key in value):
        raise GovernanceVerificationError(
            "GOLDEN_FIXTURE_MANIFEST_INVALID",
            detail=f"{field} must be an object",
        )
    return dict(cast(Mapping[str, object], value))


def _array(value: object, field: str) -> list[object]:
    if isinstance(value, (str, bytes, bytearray)) or not isinstance(value, Sequence):
        raise GovernanceVerificationError(
            "GOLDEN_FIXTURE_MANIFEST_INVALID",
            detail=f"{field} must be an array",
        )
    return list(cast(Sequence[object], value))


def _exact_fields(
    payload: Mapping[str, object],
    expected: frozenset[str],
    field: str,
) -> None:
    unknown = sorted(set(payload) - expected)
    missing = sorted(expected - set(payload))
    if unknown:
        raise GovernanceVerificationError(
            "GOLDEN_FIXTURE_MANIFEST_INVALID",
            detail=f"{field} has unknown fields: {', '.join(unknown)}",
        )
    if missing:
        raise GovernanceVerificationError(
            "GOLDEN_FIXTURE_MANIFEST_INVALID",
            detail=f"{field} is missing fields: {', '.join(missing)}",
        )


def _safe_declared_path(value: object, field: str) -> str:
    if not isinstance(value, str) or not value:
        raise GovernanceVerificationError("UNSAFE_ARTIFACT_PATH", detail=field)
    if "\\" in value or ":" in value or "\x00" in value:
        raise GovernanceVerificationError("UNSAFE_ARTIFACT_PATH", value, field)
    path = PurePosixPath(value)
    if (
        path.is_absolute()
        or path.as_posix() != value
        or value in {".", ".."}
        or any(part in {"", ".", ".."} for part in path.parts)
    ):
        raise GovernanceVerificationError("UNSAFE_ARTIFACT_PATH", value, field)
    return value


def _repository_root(root: Path) -> Path:
    try:
        resolved = root.resolve(strict=True)
    except OSError as error:
        raise GovernanceVerificationError(
            "REPOSITORY_ROOT_INVALID",
            str(root),
            str(error),
        ) from error
    if not resolved.is_dir() or root.is_symlink():
        raise GovernanceVerificationError("REPOSITORY_ROOT_INVALID", str(root))
    return resolved


def _resolve_relative(
    root: Path,
    relative: str,
    *,
    missing_code: str = "ARTIFACT_MISSING",
) -> Path:
    declared = _safe_declared_path(relative, "artifact path")
    resolved_root = _repository_root(root)
    current = resolved_root
    for part in PurePosixPath(declared).parts:
        current = current / part
        if current.is_symlink():
            raise GovernanceVerificationError("UNSAFE_ARTIFACT_PATH", declared)
    if not current.exists() or not current.is_file():
        raise GovernanceVerificationError(missing_code, declared)
    try:
        resolved = current.resolve(strict=True)
    except OSError as error:
        raise GovernanceVerificationError(missing_code, declared, str(error)) from error
    if resolved_root not in resolved.parents:
        raise GovernanceVerificationError("UNSAFE_ARTIFACT_PATH", declared)
    return resolved


def resolve_governance_path(root: Path, relative: str) -> Path:
    """Resolve one declared repository member without following symlinks."""
    return _resolve_relative(root, relative)


def _argument_path(root: Path, path: Path) -> tuple[str, Path]:
    resolved_root = _repository_root(root)
    candidate = path if path.is_absolute() else resolved_root / path
    try:
        relative = candidate.relative_to(resolved_root).as_posix()
    except ValueError as error:
        raise GovernanceVerificationError("UNSAFE_ARTIFACT_PATH", str(path)) from error
    return relative, _resolve_relative(resolved_root, relative)


def _verify_hash(path: Path, expected: str, code: str, relative: str) -> None:
    actual = _sha256(path)
    if actual != expected:
        raise GovernanceVerificationError(
            code,
            relative,
            f"expected {expected}, found {actual}",
        )


def _load_approval(path: Path, relative: str) -> RuleActivationApproval:
    try:
        return load_rule_activation_approval_bytes(path.read_bytes())
    except ValueError as error:
        message = str(error)
        if "repository-relative POSIX path" in message:
            raise GovernanceVerificationError(
                "UNSAFE_ARTIFACT_PATH",
                relative,
                message,
            ) from error
        raise GovernanceVerificationError(
            "ACTIVATION_APPROVAL_INVALID",
            relative,
            message,
        ) from error


def _load_report(path: Path, relative: str) -> RuleGoldenReport:
    try:
        return load_rule_golden_report_bytes(path.read_bytes())
    except ValueError as error:
        message = str(error)
        if "repository-relative POSIX path" in message:
            raise GovernanceVerificationError(
                "UNSAFE_ARTIFACT_PATH",
                relative,
                message,
            ) from error
        raise GovernanceVerificationError(
            "GOLDEN_REPORT_INVALID",
            relative,
            message,
        ) from error


def _load_rule(path: Path, relative: str, label: str) -> RuleSpec:
    payload = _load_json_object(path.read_bytes(), label)
    try:
        return load_rule(payload)
    except ValueError as error:
        raise GovernanceVerificationError(
            "RULE_ARTIFACT_INVALID",
            relative,
            str(error),
        ) from error


def _load_fixture_manifest(path: Path, relative: str) -> _FixtureManifest:
    payload = _load_json_object(path.read_bytes(), "golden fixture manifest")
    expected = frozenset(
        {
            "format",
            "version",
            "rule_id",
            "rule_version",
            "candidate_path",
            "approved_rule_path",
            "cases",
        }
    )
    _exact_fields(payload, expected, "golden fixture manifest")
    if (
        payload["format"] != "evidence-review/rule-golden-fixture"
        or payload["version"] != 1
    ):
        raise GovernanceVerificationError(
            "GOLDEN_FIXTURE_MANIFEST_INVALID",
            relative,
            "unsupported format or version",
        )
    cases: list[_FixtureCase] = []
    seen: set[str] = set()
    for index, item in enumerate(_array(payload["cases"], "cases")):
        case = _object(item, f"cases[{index}]")
        _exact_fields(
            case,
            frozenset({"case_id", "fixture_path", "expected_path", "actual_path"}),
            f"cases[{index}]",
        )
        try:
            case_id = validate_identifier(case["case_id"], f"cases[{index}].case_id")
        except ValueError as error:
            raise GovernanceVerificationError(
                "GOLDEN_FIXTURE_MANIFEST_INVALID",
                relative,
                str(error),
            ) from error
        if case_id in seen:
            raise GovernanceVerificationError(
                "GOLDEN_FIXTURE_MANIFEST_INVALID",
                relative,
                f"duplicate case_id: {case_id}",
            )
        seen.add(case_id)
        cases.append(
            _FixtureCase(
                case_id=case_id,
                fixture_path=_safe_declared_path(
                    case["fixture_path"], f"cases[{index}].fixture_path"
                ),
                expected_path=_safe_declared_path(
                    case["expected_path"], f"cases[{index}].expected_path"
                ),
                actual_path=_safe_declared_path(
                    case["actual_path"], f"cases[{index}].actual_path"
                ),
            )
        )
    if not cases:
        raise GovernanceVerificationError(
            "GOLDEN_FIXTURE_MANIFEST_INVALID",
            relative,
            "cases must not be empty",
        )
    try:
        rule_id = validate_identifier(payload["rule_id"], "rule_id")
        rule_version = validate_version(payload["rule_version"], "rule_version")
    except ValueError as error:
        raise GovernanceVerificationError(
            "GOLDEN_FIXTURE_MANIFEST_INVALID",
            relative,
            str(error),
        ) from error
    return _FixtureManifest(
        rule_id=rule_id,
        rule_version=rule_version,
        candidate_path=_safe_declared_path(payload["candidate_path"], "candidate_path"),
        approved_rule_path=_safe_declared_path(
            payload["approved_rule_path"], "approved_rule_path"
        ),
        cases=tuple(cases),
    )


def _reject_casefold_collisions(paths: Sequence[str]) -> None:
    by_folded: dict[str, str] = {}
    for declared in paths:
        previous = by_folded.get(declared.casefold())
        if previous is not None and previous != declared:
            raise GovernanceVerificationError(
                "CASEFOLD_PATH_COLLISION",
                declared,
                f"collides with {previous}",
            )
        by_folded[declared.casefold()] = declared


def _verify_identity(
    approval: RuleActivationApproval,
    report: RuleGoldenReport,
    fixture: _FixtureManifest,
    candidate: RuleSpec,
    approved: RuleSpec,
) -> None:
    identities = {
        (approval.rule_id, approval.rule_version),
        (report.rule_id, report.rule_version),
        (fixture.rule_id, fixture.rule_version),
        (candidate.rule_id, candidate.version),
        (approved.rule_id, approved.version),
    }
    if len(identities) != 1:
        raise GovernanceVerificationError(
            "RULE_IDENTITY_MISMATCH",
            detail=", ".join(f"{rule_id}@{version}" for rule_id, version in sorted(identities)),
        )


def _verify_report_binding(
    approval: RuleActivationApproval,
    report: RuleGoldenReport,
) -> None:
    expected = (
        approval.rule_id,
        approval.rule_version,
        approval.candidate_path,
        approval.candidate_sha256,
        approval.approved_rule_path,
        approval.approved_rule_sha256,
    )
    actual = (
        report.rule_id,
        report.rule_version,
        report.candidate_path,
        report.candidate_sha256,
        report.approved_rule_path,
        report.approved_rule_sha256,
    )
    if actual != expected:
        raise GovernanceVerificationError("GOLDEN_REPORT_BINDING_MISMATCH")


def _verify_fixture_binding(
    report: RuleGoldenReport,
    fixture: _FixtureManifest,
) -> None:
    if (
        fixture.rule_id != report.rule_id
        or fixture.rule_version != report.rule_version
        or fixture.candidate_path != report.candidate_path
        or fixture.approved_rule_path != report.approved_rule_path
    ):
        raise GovernanceVerificationError("GOLDEN_FIXTURE_BINDING_MISMATCH")
    fixture_cases = {item.case_id: item for item in fixture.cases}
    if set(fixture_cases) != {item.case_id for item in report.cases}:
        raise GovernanceVerificationError("GOLDEN_FIXTURE_BINDING_MISMATCH")
    for report_case in report.cases:
        fixture_case = fixture_cases[report_case.case_id]
        if (
            fixture_case.fixture_path != report_case.fixture_path
            or fixture_case.expected_path != report_case.expected_path
            or fixture_case.actual_path != report_case.actual_path
        ):
            raise GovernanceVerificationError("GOLDEN_FIXTURE_BINDING_MISMATCH")


def verify_approval(
    repository_root: Path,
    approval_path: Path,
    *,
    mode: VerificationMode,
) -> VerifiedApproval:
    """Verify every artifact bound by one human activation approval."""
    if mode not in {"ACTIVATION", "RUNTIME"}:
        raise ValueError(f"unsupported verification mode: {mode}")
    approval_relative, approval_file = _argument_path(repository_root, approval_path)
    approval = _load_approval(approval_file, approval_relative)

    candidate_file = _resolve_relative(repository_root, approval.candidate_path)
    _verify_hash(
        candidate_file,
        approval.candidate_sha256,
        "CANDIDATE_HASH_MISMATCH",
        approval.candidate_path,
    )
    approved_file = _resolve_relative(repository_root, approval.approved_rule_path)
    _verify_hash(
        approved_file,
        approval.approved_rule_sha256,
        "ACTIVE_RULE_HASH_MISMATCH",
        approval.approved_rule_path,
    )
    report_file = _resolve_relative(repository_root, approval.golden_report_path)
    _verify_hash(
        report_file,
        approval.golden_report_sha256,
        "GOLDEN_REPORT_HASH_MISMATCH",
        approval.golden_report_path,
    )
    report = _load_report(report_file, approval.golden_report_path)
    if report.status != "PASS" or report.failed_count != 0 or report.case_count < 1:
        raise GovernanceVerificationError(
            "GOLDEN_REPORT_NOT_PASSING",
            approval.golden_report_path,
        )
    _verify_report_binding(approval, report)

    fixture_manifest_file = _resolve_relative(
        repository_root, report.fixture_manifest_path
    )
    _verify_hash(
        fixture_manifest_file,
        report.fixture_manifest_sha256,
        "GOLDEN_FIXTURE_MANIFEST_HASH_MISMATCH",
        report.fixture_manifest_path,
    )
    fixture_manifest = _load_fixture_manifest(
        fixture_manifest_file, report.fixture_manifest_path
    )
    _verify_fixture_binding(report, fixture_manifest)

    all_paths = [
        approval_relative,
        approval.candidate_path,
        approval.approved_rule_path,
        approval.golden_report_path,
        report.fixture_manifest_path,
    ]
    for item in report.cases:
        all_paths.extend((item.fixture_path, item.expected_path, item.actual_path))
    _reject_casefold_collisions(all_paths)

    candidate_rule = _load_rule(candidate_file, approval.candidate_path, "candidate rule")
    approved_rule = _load_rule(
        approved_file, approval.approved_rule_path, "approved rule"
    )
    _verify_identity(
        approval,
        report,
        fixture_manifest,
        candidate_rule,
        approved_rule,
    )

    for item in report.cases:
        fixture_file = _resolve_relative(repository_root, item.fixture_path)
        _verify_hash(
            fixture_file,
            item.fixture_sha256,
            "GOLDEN_FIXTURE_HASH_MISMATCH",
            item.fixture_path,
        )
        expected_file = _resolve_relative(repository_root, item.expected_path)
        _verify_hash(
            expected_file,
            item.expected_sha256,
            "GOLDEN_EXPECTED_HASH_MISMATCH",
            item.expected_path,
        )
        if mode == "ACTIVATION":
            actual_file = _resolve_relative(
                repository_root,
                item.actual_path,
                missing_code="GOLDEN_ACTUAL_MISSING",
            )
            _verify_hash(
                actual_file,
                item.actual_sha256,
                "GOLDEN_ACTUAL_HASH_MISMATCH",
                item.actual_path,
            )
            if item.expected_sha256 != item.actual_sha256:
                raise GovernanceVerificationError(
                    "GOLDEN_EXPECTED_ACTUAL_MISMATCH",
                    item.actual_path,
                )

    return VerifiedApproval(
        approval_path=approval_relative,
        approval=approval,
        rule=approved_rule,
        golden_report=report,
    )


def _entry_binding(entry: ActiveRuleEntry) -> tuple[object, ...]:
    return (
        entry.rule_id,
        entry.rule_version,
        entry.candidate_path,
        entry.candidate_sha256,
        entry.approved_rule_path,
        entry.approved_rule_sha256,
        entry.golden_report_path,
        entry.golden_report_sha256,
        entry.scope,
        entry.reviewer_id,
        entry.reviewed_at,
        entry.reason,
    )


def _approval_binding(approval: RuleActivationApproval) -> tuple[object, ...]:
    return (
        approval.rule_id,
        approval.rule_version,
        approval.candidate_path,
        approval.candidate_sha256,
        approval.approved_rule_path,
        approval.approved_rule_sha256,
        approval.golden_report_path,
        approval.golden_report_sha256,
        approval.scope,
        approval.reviewer_id,
        approval.reviewed_at,
        approval.reason,
    )


def verify_manifest_entry(
    repository_root: Path,
    entry: ActiveRuleEntry,
    *,
    mode: VerificationMode,
) -> VerifiedApproval:
    """Verify one active manifest entry and its exact approval authority."""
    approval_file = _resolve_relative(repository_root, entry.approval_path)
    _verify_hash(
        approval_file,
        entry.approval_sha256,
        "APPROVAL_HASH_MISMATCH",
        entry.approval_path,
    )
    approval = _load_approval(approval_file, entry.approval_path)
    if _entry_binding(entry) != _approval_binding(approval):
        raise GovernanceVerificationError(
            "ACTIVE_ENTRY_MISMATCH",
            entry.approval_path,
        )
    return verify_approval(repository_root, approval_file, mode=mode)
