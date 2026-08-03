"""Public orchestration and canonical report models for parser validation."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Literal, TypeAlias, cast

from pypdf.errors import PyPdfError

from ansim_review.canonical_json import dump_bytes
from ansim_review.parser_reproducibility.comparison import (
    ParsedRunPair,
    ReproducibilityStatus,
    StructuralDifference,
    compare_parser_runs,
    parse_loaded_run,
)
from ansim_review.parser_reproducibility.contract import ReproducibilityConfig
from ansim_review.parser_reproducibility.normalization import AppliedNormalization
from ansim_review.parser_reproducibility.queue import (
    ParserReviewQueue,
    build_review_queue,
)
from ansim_review.parser_reproducibility.run_manifest import (
    ParserRunManifest,
    load_parser_run,
    load_parser_run_for_identity,
)
from ansim_review.parser_reproducibility.source_identity import SourceIdentity
from ansim_review.parser_reproducibility.warnings import (
    ParserWarningReport,
    WarningContext,
    build_warning_report,
)


@dataclass(frozen=True, slots=True)
class ParserValidationFinding:
    severity: Literal["ERROR"]
    code: str
    message: str


@dataclass(frozen=True, slots=True)
class ParserReproducibilityReport:
    format: Literal["evidence-review/parser-reproducibility-report"]
    version: Literal[1]
    status: ReproducibilityStatus
    source_sha256: str | None
    run_a: ParserRunManifest | None
    run_b: ParserRunManifest | None
    canonical_equivalent: bool | None
    applied_normalizations: tuple[AppliedNormalization, ...]
    differences: tuple[StructuralDifference, ...]
    findings: tuple[ParserValidationFinding, ...]
    error_count: int
    warning_count: int
    summary: str


@dataclass(frozen=True, slots=True)
class WarningCollectionResult:
    warning_report: ParserWarningReport
    review_queue: ParserReviewQueue


PublicReport: TypeAlias = (
    ParserReproducibilityReport | ParserWarningReport | ParserReviewQueue
)


def _failure_code(exc: Exception) -> str:
    if isinstance(exc, FileNotFoundError):
        return "PARSER_ARTIFACT_MISSING"
    if isinstance(exc, PermissionError):
        return "PARSER_ARTIFACT_UNREADABLE"
    if isinstance(exc, PyPdfError):
        return "PARSER_SOURCE_PDF_INVALID"
    message = str(exc).casefold()
    if "page count" in message:
        return "PARSER_PAGE_COUNT_MISMATCH"
    if "hash" in message or "size" in message:
        return "PARSER_AUTHORITY_MISMATCH"
    if "utf-8" in message or "json" in message:
        return "PARSER_ARTIFACT_INVALID"
    return "PARSER_VALIDATION_FAILED"


def _failure_message(code: str) -> str:
    messages = {
        "PARSER_ARTIFACT_MISSING": "A required parser artifact is missing.",
        "PARSER_ARTIFACT_UNREADABLE": "A required parser artifact is unreadable.",
        "PARSER_SOURCE_PDF_INVALID": "The source PDF is malformed or unreadable.",
        "PARSER_PAGE_COUNT_MISMATCH": (
            "Source and parser page authority do not match."
        ),
        "PARSER_AUTHORITY_MISMATCH": (
            "Source bytes do not match parser-run authority."
        ),
        "PARSER_ARTIFACT_INVALID": (
            "A parser artifact is not valid UTF-8 JSON or text."
        ),
        "PARSER_VALIDATION_FAILED": "Parser run validation failed closed.",
    }
    return messages[code]


def _failed_report(
    exc: Exception,
    run_a: ParserRunManifest | None = None,
) -> ParserReproducibilityReport:
    code = _failure_code(exc)
    finding = ParserValidationFinding(
        severity="ERROR",
        code=code,
        message=_failure_message(code),
    )
    return ParserReproducibilityReport(
        format="evidence-review/parser-reproducibility-report",
        version=1,
        status="PARSER_FAILED",
        source_sha256=None if run_a is None else run_a.source_sha256,
        run_a=run_a,
        run_b=None,
        canonical_equivalent=None,
        applied_normalizations=(),
        differences=(),
        findings=(finding,),
        error_count=1,
        warning_count=0,
        summary=f"PARSER_FAILED: {code}",
    )


def validate_opendataloader_reproducibility(
    source_pdf: Path,
    run_a_root: Path,
    run_b_root: Path,
    config: ReproducibilityConfig,
) -> ParserReproducibilityReport:
    """Validate two immutable parser runs and return deterministic evidence."""

    try:
        loaded_a = load_parser_run(source_pdf, run_a_root, config)
    except (OSError, ValueError, PyPdfError) as exc:
        return _failed_report(exc)
    try:
        loaded_b = load_parser_run(source_pdf, run_b_root, config)
    except (OSError, ValueError, PyPdfError) as exc:
        return _failed_report(exc, loaded_a.manifest)

    pair = ParsedRunPair(
        left=parse_loaded_run(loaded_a, config),
        right=parse_loaded_run(loaded_b, config),
    )
    result = compare_parser_runs(pair, config)
    warning_count = max(
        loaded_a.manifest.warning_count,
        loaded_b.manifest.warning_count,
    )
    summary = (
        f"{result.status}: differences={len(result.differences)}, "
        f"warnings={warning_count}"
    )
    return ParserReproducibilityReport(
        format="evidence-review/parser-reproducibility-report",
        version=1,
        status=result.status,
        source_sha256=loaded_a.manifest.source_sha256,
        run_a=loaded_a.manifest,
        run_b=loaded_b.manifest,
        canonical_equivalent=result.canonical_equivalent,
        applied_normalizations=result.applied_normalizations,
        differences=result.differences,
        findings=(),
        error_count=(
            1
            if result.status in {"MISMATCH", "ENVIRONMENT_MISMATCH"}
            else 0
        ),
        warning_count=warning_count,
        summary=summary,
    )


def collect_opendataloader_warnings(
    source_identity: SourceIdentity,
    run_root: Path,
    config: ReproducibilityConfig,
    previous_queue: ParserReviewQueue | None = None,
) -> WarningCollectionResult:
    """Collect warnings after source-manifest identity resolution."""

    loaded = load_parser_run_for_identity(source_identity, run_root, config)
    warning_context = WarningContext(
        source_sha256=loaded.manifest.source_sha256,
        document_id=loaded.manifest.document_id,
        revision_id=loaded.manifest.revision_id,
        parser_kind=loaded.manifest.parser_kind,
        parser_version=loaded.manifest.parser_version,
        configuration_sha256=loaded.manifest.configuration_sha256,
        run_id=loaded.manifest.run_id,
        run_root=loaded.run_root,
        parser_page_count=loaded.manifest.parser_page_count,
    )
    return WarningCollectionResult(
        warning_report=build_warning_report(
            loaded.warnings,
            warning_context,
        ),
        review_queue=build_review_queue(
            loaded.warnings,
            loaded.manifest.run_id,
            previous_queue,
        ),
    )


def report_document(report: PublicReport) -> dict[str, object]:
    """Convert a frozen public report to JSON-ready values."""

    return cast(dict[str, object], asdict(report))


def report_bytes(report: PublicReport) -> bytes:
    """Encode one canonical report with LF and one trailing newline."""

    return dump_bytes(report_document(report)) + b"\n"
