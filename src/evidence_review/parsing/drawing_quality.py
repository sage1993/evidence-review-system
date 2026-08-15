"""Deterministic quality assessment for immutable drawing sources."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from evidence_review.contracts.attachments import ImmutableAttachment
from evidence_review.contracts.drawing import (
    DrawingQualityAssessment,
    PhysicalSizeTrust,
    decode_drawing_quality,
    drawing_quality_document,
)
from evidence_review.contracts.formats import DRAWING_QUALITY_FORMAT
from evidence_review.contracts.validation import expect_sha256, expect_string
from evidence_review.contracts.workflow import ReasonCode
from evidence_review.parsing.drawing_case import (
    CaseManifestEntry,
    case_artifact_path,
    validate_artifact_id,
    write_canonical_create_only,
)
from evidence_review.parsing.drawing_source import DrawingIntakePolicy

ParserOutcome = Literal[
    "SUCCESS",
    "TIMEOUT",
    "MEMORY_LIMIT",
    "INVALID_OUTPUT",
    "UNAVAILABLE",
]

_PARSER_OUTCOMES: tuple[ParserOutcome, ...] = (
    "SUCCESS",
    "TIMEOUT",
    "MEMORY_LIMIT",
    "INVALID_OUTPUT",
    "UNAVAILABLE",
)
_PHYSICAL_SIZE_TRUST: tuple[PhysicalSizeTrust, ...] = (
    "PDF_MEDIABOX_VERIFIED",
    "USER_CONFIRMED",
    "METADATA_ONLY",
    "UNKNOWN",
)
_PARSER_REASON: dict[ParserOutcome, str] = {
    "SUCCESS": "",
    "TIMEOUT": "PARSER_TIMEOUT",
    "MEMORY_LIMIT": "PARSER_MEMORY_LIMIT",
    "INVALID_OUTPUT": "PARSER_OUTPUT_INVALID",
    "UNAVAILABLE": "PARSER_UNAVAILABLE",
}


@dataclass(frozen=True, slots=True)
class TrustedSourceMetadata:
    """Hash-bound metadata returned by an isolated parser adapter."""

    source_sha256: str
    adapter: str
    adapter_version: str
    parser_outcome: ParserOutcome
    page_count: int | None
    width: int | None
    height: int | None
    physical_size_trust: PhysicalSizeTrust
    lossy_or_screen_capture: bool

    def __post_init__(self) -> None:
        expect_sha256(self.source_sha256, "source_sha256")
        expect_string(self.adapter, "adapter")
        expect_string(self.adapter_version, "adapter_version")
        if self.parser_outcome not in _PARSER_OUTCOMES:
            raise ValueError(f"unsupported parser_outcome: {self.parser_outcome}")
        if self.physical_size_trust not in _PHYSICAL_SIZE_TRUST:
            raise ValueError(
                f"unsupported physical_size_trust: {self.physical_size_trust}"
            )
        for field, value in (
            ("page_count", self.page_count),
            ("width", self.width),
            ("height", self.height),
        ):
            if value is not None and (isinstance(value, bool) or value < 1):
                raise ValueError(f"{field} must be positive when present")
        if not isinstance(self.lossy_or_screen_capture, bool):
            raise ValueError("lossy_or_screen_capture must be a boolean")


@dataclass(frozen=True, slots=True)
class DrawingQualityResult:
    """Quality contract plus deterministic diagnostic and resource metadata."""

    assessment: DrawingQualityAssessment
    detailed_reasons: tuple[str, ...]
    policy_id: str
    image_pixels: int | None


def _result(
    quality: Literal["PASS", "REVIEW_REQUIRED", "REJECTED"],
    metadata: TrustedSourceMetadata,
    reasons: list[str],
    policy: DrawingIntakePolicy,
    image_pixels: int | None,
) -> DrawingQualityResult:
    assessment = DrawingQualityAssessment(
        quality=quality,
        physical_size_trust=metadata.physical_size_trust,
        reason_codes=tuple(reasons),
    )
    validated = decode_drawing_quality(drawing_quality_document(assessment))
    return DrawingQualityResult(
        assessment=validated,
        detailed_reasons=tuple(reasons),
        policy_id=policy.policy_id,
        image_pixels=image_pixels,
    )


def assess_drawing_quality(
    attachment: ImmutableAttachment,
    metadata: TrustedSourceMetadata,
    policy: DrawingIntakePolicy,
    existing_case_image_pixels: int = 0,
) -> DrawingQualityResult:
    """Assess one source without opening or allocating its decoded image payload."""
    if isinstance(existing_case_image_pixels, bool) or existing_case_image_pixels < 0:
        raise ValueError("existing_case_image_pixels must be non-negative")

    if metadata.source_sha256 != attachment.sha256:
        return _result(
            "REJECTED",
            metadata,
            ["SOURCE_HASH_MISMATCH"],
            policy,
            None,
        )

    reasons: list[str] = []
    rejected = False
    if attachment.byte_size > policy.max_file_bytes:
        reasons.append("FILE_SIZE_LIMIT_EXCEEDED")
        rejected = True

    if metadata.parser_outcome != "SUCCESS":
        reasons.append(_PARSER_REASON[metadata.parser_outcome])
        quality: Literal["REVIEW_REQUIRED", "REJECTED"] = (
            "REJECTED" if rejected else "REVIEW_REQUIRED"
        )
        return _result(quality, metadata, reasons, policy, None)

    image_pixels: int | None = None
    if attachment.mime == "application/pdf":
        if metadata.page_count is None:
            reasons.append("PDF_PAGE_COUNT_UNKNOWN")
        elif metadata.page_count > policy.max_pdf_pages:
            reasons.append("PDF_PAGE_LIMIT_EXCEEDED")
            rejected = True
    elif attachment.mime in {"image/png", "image/tiff", "image/jpeg"}:
        if metadata.width is None or metadata.height is None:
            reasons.append("IMAGE_DIMENSIONS_UNKNOWN")
        else:
            image_pixels = metadata.width * metadata.height
            if image_pixels > policy.max_image_pixels:
                reasons.append("IMAGE_PIXEL_LIMIT_EXCEEDED")
                rejected = True
            if existing_case_image_pixels + image_pixels > policy.max_case_image_pixels:
                reasons.append("CASE_PIXEL_LIMIT_EXCEEDED")
                rejected = True
    else:
        reasons.append("UNSUPPORTED_MIME")
        rejected = True

    if metadata.lossy_or_screen_capture:
        reasons.append("LOSSY_OR_SCREEN_CAPTURE_SOURCE")
    if metadata.physical_size_trust == "METADATA_ONLY":
        reasons.append("METADATA_ONLY_PHYSICAL_SIZE")
    elif metadata.physical_size_trust == "UNKNOWN":
        reasons.append("UNKNOWN_PHYSICAL_SIZE")

    if rejected:
        quality_value: Literal["PASS", "REVIEW_REQUIRED", "REJECTED"] = "REJECTED"
    elif reasons:
        quality_value = "REVIEW_REQUIRED"
    else:
        quality_value = "PASS"
    return _result(quality_value, metadata, reasons, policy, image_pixels)


def drawing_quality_result_document(
    source_sha256: str,
    result: DrawingQualityResult,
) -> dict[str, object]:
    """Return a source-bound canonical quality artifact."""
    return {
        "format": DRAWING_QUALITY_FORMAT,
        "version": 1,
        "source_sha256": expect_sha256(source_sha256, "source_sha256"),
        "policy_id": expect_string(result.policy_id, "policy_id"),
        "assessment": drawing_quality_document(result.assessment),
        "detailed_reasons": list(result.detailed_reasons),
        "image_pixels": result.image_pixels,
    }


def persist_drawing_quality(
    case_dir: Path,
    attachment_id: str,
    source_sha256: str,
    result: DrawingQualityResult,
) -> CaseManifestEntry:
    """Persist one quality assessment as immutable case evidence."""
    validate_artifact_id(attachment_id, "attachment_id")
    artifact_id = f"QUALITY-{attachment_id}"
    relative_path = f"quality/{attachment_id}.json"
    path = case_artifact_path(case_dir, relative_path)
    digest = write_canonical_create_only(
        path,
        drawing_quality_result_document(source_sha256, result),
    )
    return CaseManifestEntry(
        artifact_id=artifact_id,
        relative_path=relative_path,
        sha256=digest,
    )


def workflow_reason_for_quality(result: DrawingQualityResult) -> ReasonCode | None:
    """Map detailed quality output into the fixed M0 workflow reason namespace."""
    if "SOURCE_HASH_MISMATCH" in result.detailed_reasons:
        return "SOURCE_HASH_MISMATCH"
    if result.assessment.quality == "REJECTED":
        return "DRAWING_QUALITY_REJECTED"
    if result.assessment.quality == "REVIEW_REQUIRED":
        return "DRAWING_CONFIRMATION_REQUIRED"
    return None
