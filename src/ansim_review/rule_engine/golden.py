"""Deterministic create-only runner for governed rule golden cases."""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import tempfile
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from pathlib import Path, PurePosixPath
from typing import TypeAlias, cast

from ansim_review.canonical_json import dump_bytes
from ansim_review.contracts.common import BBox
from ansim_review.contracts.engines import (
    CalculationComparison,
    CalculationResult,
    CalculationStatus,
)
from ansim_review.contracts.evidence import EvidenceRecord
from ansim_review.contracts.identifiers import validate_identifier, validate_version
from ansim_review.rule_engine.evaluator import evaluate_rule
from ansim_review.rule_engine.governance_contract import (
    GoldenCaseRecord,
    RuleGoldenReport,
    load_rule_golden_report_bytes,
    rule_golden_report_bytes,
)
from ansim_review.rule_engine.governance_verify import resolve_governance_path
from ansim_review.rule_engine.loader import load_rule
from ansim_review.rule_engine.schema import RuleSpec

_GOLDEN_FIXTURE_FORMAT = "evidence-review/rule-golden-fixture"
_GOLDEN_CASE_FORMAT = "evidence-review/rule-golden-case"
_RUNNER_VERSION = "1"
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_COMMIT_SHA = re.compile(r"^[0-9a-f]{40}$")
_CALCULATION_STATUSES = frozenset(
    {
        "SUCCESS",
        "INVALID_INPUT",
        "DIVISION_BY_ZERO",
        "FORMULA_NOT_FOUND",
        "ENGINE_ERROR",
    }
)
_CALCULATION_COMPARISONS = frozenset(
    {
        "BELOW_THRESHOLD",
        "AT_THRESHOLD",
        "ABOVE_THRESHOLD",
        "EQUAL",
        "NOT_EQUAL",
        "NOT_APPLICABLE",
    }
)

JsonObject: TypeAlias = dict[str, object]


@dataclass(frozen=True, slots=True)
class GoldenFixtureCase:
    case_id: str
    fixture_path: str
    expected_path: str
    actual_path: str


@dataclass(frozen=True, slots=True)
class RuleGoldenFixture:
    rule_id: str
    rule_version: str
    candidate_path: str
    approved_rule_path: str
    cases: tuple[GoldenFixtureCase, ...]


@dataclass(frozen=True, slots=True)
class GoldenCaseInput:
    inputs: Mapping[str, object]
    calculations: tuple[CalculationResult, ...]
    expected_formula_manifest_hash: str | None
    evidence_records: tuple[EvidenceRecord, ...]


@dataclass(frozen=True, slots=True)
class _PreparedPublication:
    private_path: Path
    destination: Path


@dataclass(frozen=True, slots=True)
class _PublishedInode:
    destination: Path
    device: int
    inode: int


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sha256_file(path: Path) -> str:
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


def _exact_fields(payload: Mapping[str, object], expected: frozenset[str], field: str) -> None:
    unknown = sorted(set(payload) - expected)
    missing = sorted(expected - set(payload))
    if unknown:
        raise ValueError(f"{field} has unknown fields: {', '.join(unknown)}")
    if missing:
        raise ValueError(f"{field} is missing fields: {', '.join(missing)}")


def _string(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be a non-empty string")
    return value.strip()


def _nullable_string(value: object, field: str) -> str | None:
    if value is None:
        return None
    return _string(value, field)


def _sha256(value: object, field: str) -> str:
    if not isinstance(value, str) or _SHA256.fullmatch(value) is None:
        raise ValueError(f"{field} must be a lowercase SHA-256")
    return value


def _safe_path(value: object, field: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{field} must be a repository-relative POSIX path")
    if "\\" in value or ":" in value or "\x00" in value:
        raise ValueError(f"{field} must be a repository-relative POSIX path")
    path = PurePosixPath(value)
    if (
        path.is_absolute()
        or path.as_posix() != value
        or value in {".", ".."}
        or any(part in {"", ".", ".."} for part in path.parts)
    ):
        raise ValueError(f"{field} must be a repository-relative POSIX path")
    return value


def _positive_integer(value: object, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValueError(f"{field} must be a positive integer")
    return value


def _number(value: object, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{field} must be a finite number")
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"{field} must be a finite number")
    return result


def load_rule_golden_fixture_bytes(data: bytes) -> RuleGoldenFixture:
    """Strictly decode one version 1 golden fixture manifest."""
    payload = _load_json_object(data, "golden fixture manifest")
    _exact_fields(
        payload,
        frozenset(
            {
                "format",
                "version",
                "rule_id",
                "rule_version",
                "candidate_path",
                "approved_rule_path",
                "cases",
            }
        ),
        "golden fixture manifest",
    )
    if payload["format"] != _GOLDEN_FIXTURE_FORMAT or payload["version"] != 1:
        raise ValueError("unsupported golden fixture manifest format or version")
    cases: list[GoldenFixtureCase] = []
    seen: set[str] = set()
    for index, item in enumerate(_array(payload["cases"], "cases")):
        case = _object(item, f"cases[{index}]")
        _exact_fields(
            case,
            frozenset({"case_id", "fixture_path", "expected_path", "actual_path"}),
            f"cases[{index}]",
        )
        case_id = validate_identifier(case["case_id"], f"cases[{index}].case_id")
        if case_id in seen:
            raise ValueError(f"duplicate case_id: {case_id}")
        seen.add(case_id)
        cases.append(
            GoldenFixtureCase(
                case_id=case_id,
                fixture_path=_safe_path(
                    case["fixture_path"], f"cases[{index}].fixture_path"
                ),
                expected_path=_safe_path(
                    case["expected_path"], f"cases[{index}].expected_path"
                ),
                actual_path=_safe_path(
                    case["actual_path"], f"cases[{index}].actual_path"
                ),
            )
        )
    if not cases:
        raise ValueError("golden fixture manifest cases must not be empty")
    return RuleGoldenFixture(
        rule_id=validate_identifier(payload["rule_id"], "rule_id"),
        rule_version=validate_version(payload["rule_version"], "rule_version"),
        candidate_path=_safe_path(payload["candidate_path"], "candidate_path"),
        approved_rule_path=_safe_path(payload["approved_rule_path"], "approved_rule_path"),
        cases=tuple(cases),
    )


def _load_inputs(value: object) -> Mapping[str, object]:
    payload = _object(value, "inputs")
    return dict(sorted(payload.items()))


def _load_string_map(value: object, field: str) -> dict[str, str]:
    payload = _object(value, field)
    result: dict[str, str] = {}
    for key, item in sorted(payload.items()):
        result[key] = _string(item, f"{field}.{key}")
    return result


def _load_calculation(value: object, index: int) -> CalculationResult:
    field = f"calculations[{index}]"
    payload = _object(value, field)
    _exact_fields(
        payload,
        frozenset(
            {
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
            }
        ),
        field,
    )
    status = payload["status"]
    if status not in _CALCULATION_STATUSES:
        raise ValueError(f"{field}.status is unsupported")
    comparison = payload["comparison"]
    if comparison is not None and comparison not in _CALCULATION_COMPARISONS:
        raise ValueError(f"{field}.comparison is unsupported")
    error_codes = tuple(
        _string(item, f"{field}.error_codes")
        for item in _array(payload["error_codes"], f"{field}.error_codes")
    )
    formula_manifest_hash = payload["formula_manifest_hash"]
    result_hash = payload["result_hash"]
    return CalculationResult(
        calculation_result_id=validate_identifier(
            payload["calculation_result_id"], f"{field}.calculation_result_id"
        ),
        status=cast(CalculationStatus, status),
        formula_id=validate_identifier(payload["formula_id"], f"{field}.formula_id"),
        formula_version=validate_version(
            payload["formula_version"], f"{field}.formula_version"
        ),
        inputs=_load_string_map(payload["inputs"], f"{field}.inputs"),
        substitution=_nullable_string(payload["substitution"], f"{field}.substitution"),
        raw_result=_nullable_string(payload["raw_result"], f"{field}.raw_result"),
        display_result=_nullable_string(
            payload["display_result"], f"{field}.display_result"
        ),
        comparison=cast(CalculationComparison | None, comparison),
        formula_manifest_hash=(
            None
            if formula_manifest_hash is None
            else _sha256(formula_manifest_hash, f"{field}.formula_manifest_hash")
        ),
        result_hash=(
            None if result_hash is None else _sha256(result_hash, f"{field}.result_hash")
        ),
        error_codes=error_codes,
    )


def _load_bbox(value: object, field: str) -> BBox:
    payload = _object(value, field)
    _exact_fields(payload, frozenset({"left", "bottom", "right", "top"}), field)
    return BBox(
        left=_number(payload["left"], f"{field}.left"),
        bottom=_number(payload["bottom"], f"{field}.bottom"),
        right=_number(payload["right"], f"{field}.right"),
        top=_number(payload["top"], f"{field}.top"),
    )


def _load_evidence(value: object, index: int) -> EvidenceRecord:
    field = f"evidence_records[{index}]"
    payload = _object(value, field)
    _exact_fields(
        payload,
        frozenset(
            {
                "evidence_id",
                "document_id",
                "revision_id",
                "page_number",
                "element_id",
                "evidence_type",
                "bbox",
                "source_hash",
                "raw_text",
                "normalized_text",
            }
        ),
        field,
    )
    return EvidenceRecord(
        evidence_id=validate_identifier(payload["evidence_id"], f"{field}.evidence_id"),
        document_id=validate_identifier(payload["document_id"], f"{field}.document_id"),
        revision_id=validate_identifier(payload["revision_id"], f"{field}.revision_id"),
        page_number=_positive_integer(payload["page_number"], f"{field}.page_number"),
        element_id=validate_identifier(payload["element_id"], f"{field}.element_id"),
        evidence_type=_string(payload["evidence_type"], f"{field}.evidence_type"),
        bbox=_load_bbox(payload["bbox"], f"{field}.bbox"),
        source_hash=_sha256(payload["source_hash"], f"{field}.source_hash"),
        raw_text=_nullable_string(payload["raw_text"], f"{field}.raw_text"),
        normalized_text=_nullable_string(
            payload["normalized_text"], f"{field}.normalized_text"
        ),
    )


def load_rule_golden_case_bytes(data: bytes) -> GoldenCaseInput:
    """Strictly decode one version 1 golden case input."""
    payload = _load_json_object(data, "golden case")
    _exact_fields(
        payload,
        frozenset(
            {
                "format",
                "version",
                "inputs",
                "calculations",
                "expected_formula_manifest_hash",
                "evidence_records",
            }
        ),
        "golden case",
    )
    if payload["format"] != _GOLDEN_CASE_FORMAT or payload["version"] != 1:
        raise ValueError("unsupported golden case format or version")
    expected_hash = payload["expected_formula_manifest_hash"]
    calculations = tuple(
        _load_calculation(item, index)
        for index, item in enumerate(_array(payload["calculations"], "calculations"))
    )
    calculation_ids = [item.calculation_result_id for item in calculations]
    if len(calculation_ids) != len(set(calculation_ids)):
        raise ValueError("duplicate calculation_result_id")
    return GoldenCaseInput(
        inputs=_load_inputs(payload["inputs"]),
        calculations=calculations,
        expected_formula_manifest_hash=(
            None
            if expected_hash is None
            else _sha256(expected_hash, "expected_formula_manifest_hash")
        ),
        evidence_records=tuple(
            _load_evidence(item, index)
            for index, item in enumerate(
                _array(payload["evidence_records"], "evidence_records")
            )
        ),
    )


def _load_rule_file(path: Path, label: str) -> RuleSpec:
    payload = _load_json_object(path.read_bytes(), label)
    return load_rule(payload)


def _resolved_root(repository_root: Path) -> Path:
    resolved = repository_root.resolve(strict=True)
    if repository_root.is_symlink() or not resolved.is_dir():
        raise ValueError("repository_root must be a real directory")
    return resolved


def _argument_relative(root: Path, path: Path, field: str) -> str:
    candidate = path if path.is_absolute() else root / path
    try:
        relative = candidate.relative_to(root).as_posix()
    except ValueError as error:
        raise ValueError(f"{field} must be below repository_root") from error
    return _safe_path(relative, field)


def _output_target(root: Path, relative: str) -> Path:
    destination = root / PurePosixPath(relative)
    current = root
    for part in PurePosixPath(relative).parts[:-1]:
        current = current / part
        if current.is_symlink():
            raise ValueError(f"output path traverses a symlink: {relative}")
        if current.exists() and not current.is_dir():
            raise ValueError(f"output parent is not a directory: {relative}")
    if destination.exists() or destination.is_symlink():
        raise FileExistsError(destination)
    return destination


def _is_below(path: str, root: str) -> bool:
    path_parts = PurePosixPath(path).parts
    root_parts = PurePosixPath(root).parts
    return len(path_parts) > len(root_parts) and path_parts[: len(root_parts)] == root_parts


def _reject_output_collisions(paths: Sequence[str]) -> None:
    folded: dict[str, str] = {}
    for path in paths:
        previous = folded.get(path.casefold())
        if previous is not None:
            raise ValueError(f"duplicate or case-fold-colliding output path: {path}")
        folded[path.casefold()] = path


def _prepare_publication(destination: Path, payload: bytes) -> _PreparedPublication:
    destination.parent.mkdir(parents=True, exist_ok=True)
    descriptor, name = tempfile.mkstemp(
        prefix=f".{destination.name}.",
        suffix=".private",
        dir=destination.parent,
    )
    private_path = Path(name)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
    except BaseException:
        private_path.unlink(missing_ok=True)
        raise
    return _PreparedPublication(private_path=private_path, destination=destination)


def _same_inode(path: Path, published: _PublishedInode) -> bool:
    try:
        current = path.stat(follow_symlinks=False)
    except FileNotFoundError:
        return False
    return (
        not path.is_symlink()
        and current.st_dev == published.device
        and current.st_ino == published.inode
    )


def _publish_create_only(publications: Sequence[tuple[Path, bytes]]) -> None:
    prepared: list[_PreparedPublication] = []
    published: list[_PublishedInode] = []
    try:
        for destination, payload in publications:
            prepared.append(_prepare_publication(destination, payload))
        for prepared_item in prepared:
            os.link(prepared_item.private_path, prepared_item.destination)
            status = prepared_item.destination.stat(follow_symlinks=False)
            published.append(
                _PublishedInode(
                    destination=prepared_item.destination,
                    device=status.st_dev,
                    inode=status.st_ino,
                )
            )
    except BaseException:
        for published_item in reversed(published):
            if _same_inode(published_item.destination, published_item):
                published_item.destination.unlink(missing_ok=True)
        raise
    finally:
        for prepared_item in prepared:
            prepared_item.private_path.unlink(missing_ok=True)


def _validate_rule_identity(
    fixture: RuleGoldenFixture,
    candidate: RuleSpec,
    approved: RuleSpec,
) -> None:
    identities = {
        (fixture.rule_id, fixture.rule_version),
        (candidate.rule_id, candidate.version),
        (approved.rule_id, approved.version),
    }
    if len(identities) != 1:
        raise ValueError("golden fixture rule identity mismatch")


def run_rule_golden(
    repository_root: Path,
    fixture_manifest_path: Path,
    actual_root: Path,
    report_path: Path,
    *,
    source_commit: str,
    command: str,
) -> RuleGoldenReport:
    """Evaluate every declared case and publish actuals plus one report create-only."""
    root = _resolved_root(repository_root)
    if _COMMIT_SHA.fullmatch(source_commit) is None:
        raise ValueError("source_commit must be a lowercase 40-character commit SHA")
    normalized_command = _string(command, "command")
    manifest_relative = _argument_relative(root, fixture_manifest_path, "fixture_manifest_path")
    manifest_file = resolve_governance_path(root, manifest_relative)
    manifest_bytes = manifest_file.read_bytes()
    fixture_manifest = load_rule_golden_fixture_bytes(manifest_bytes)

    candidate_file = resolve_governance_path(root, fixture_manifest.candidate_path)
    approved_file = resolve_governance_path(root, fixture_manifest.approved_rule_path)
    candidate_rule = _load_rule_file(candidate_file, "candidate rule")
    approved_rule = _load_rule_file(approved_file, "approved rule")
    _validate_rule_identity(fixture_manifest, candidate_rule, approved_rule)

    actual_root_relative = _argument_relative(root, actual_root, "actual_root")
    report_relative = _argument_relative(root, report_path, "report_path")
    output_relatives = [item.actual_path for item in fixture_manifest.cases]
    output_relatives.append(report_relative)
    _reject_output_collisions(output_relatives)
    for item in fixture_manifest.cases:
        if not _is_below(item.actual_path, actual_root_relative):
            raise ValueError(f"actual_path is outside actual_root: {item.actual_path}")

    destinations = {
        relative: _output_target(root, relative) for relative in output_relatives
    }
    records: list[GoldenCaseRecord] = []
    actual_payloads: list[tuple[Path, bytes]] = []
    for item in fixture_manifest.cases:
        fixture_file = resolve_governance_path(root, item.fixture_path)
        expected_file = resolve_governance_path(root, item.expected_path)
        fixture_bytes = fixture_file.read_bytes()
        expected_bytes = expected_file.read_bytes()
        case = load_rule_golden_case_bytes(fixture_bytes)
        result = evaluate_rule(
            approved_rule,
            case.inputs,
            calculations=case.calculations,
            expected_formula_manifest_hash=case.expected_formula_manifest_hash,
            evidence_records=case.evidence_records,
        )
        actual_bytes = dump_bytes(asdict(result))
        expected_sha256 = _sha256_bytes(expected_bytes)
        actual_sha256 = _sha256_bytes(actual_bytes)
        records.append(
            GoldenCaseRecord(
                case_id=item.case_id,
                fixture_path=item.fixture_path,
                fixture_sha256=_sha256_bytes(fixture_bytes),
                expected_path=item.expected_path,
                expected_sha256=expected_sha256,
                actual_path=item.actual_path,
                actual_sha256=actual_sha256,
                status="PASS" if expected_bytes == actual_bytes else "FAIL",
            )
        )
        actual_payloads.append((destinations[item.actual_path], actual_bytes))

    failed_count = sum(item.status == "FAIL" for item in records)
    report = RuleGoldenReport(
        rule_id=fixture_manifest.rule_id,
        rule_version=fixture_manifest.rule_version,
        candidate_path=fixture_manifest.candidate_path,
        candidate_sha256=_sha256_file(candidate_file),
        approved_rule_path=fixture_manifest.approved_rule_path,
        approved_rule_sha256=_sha256_file(approved_file),
        runner_version=_RUNNER_VERSION,
        source_commit=source_commit,
        command=normalized_command,
        fixture_manifest_path=manifest_relative,
        fixture_manifest_sha256=_sha256_bytes(manifest_bytes),
        case_count=len(records),
        passed_count=len(records) - failed_count,
        failed_count=failed_count,
        status="PASS" if failed_count == 0 else "FAIL",
        cases=tuple(records),
    )
    report_bytes = rule_golden_report_bytes(report)
    validated = load_rule_golden_report_bytes(report_bytes)
    publications = [*actual_payloads, (destinations[report_relative], report_bytes)]
    _publish_create_only(publications)
    return validated
