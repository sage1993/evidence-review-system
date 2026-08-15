import pytest

from evidence_review.contracts.attachments import ImmutableAttachment
from evidence_review.parsing.drawing_quality import (
    DrawingQualityResult,
    TrustedSourceMetadata,
    assess_drawing_quality,
    workflow_reason_for_quality,
)
from evidence_review.parsing.drawing_source import DrawingIntakePolicy


def attachment(mime: str = "image/png", byte_size: int = 100) -> ImmutableAttachment:
    extension = {
        "image/png": ".png",
        "application/pdf": ".pdf",
        "image/jpeg": ".jpg",
    }[mime]
    return ImmutableAttachment(
        attachment_id="ATT-001",
        original_name=f"drawing{extension}",
        stored_path=f"inputs/original/ATT-001{extension}",
        sha256="a" * 64,
        byte_size=byte_size,
        mime=mime,
        role="CASE_DRAWING",
    )


def metadata(
    *,
    mime: str = "image/png",
    parser_outcome: str = "SUCCESS",
    page_count: int | None = None,
    width: int | None = 4000,
    height: int | None = 3000,
    physical_size_trust: str = "USER_CONFIRMED",
    lossy_or_screen_capture: bool = False,
    source_sha256: str = "a" * 64,
) -> TrustedSourceMetadata:
    if mime == "application/pdf":
        width = None
        height = None
        page_count = 1 if page_count is None else page_count
        physical_size_trust = "PDF_MEDIABOX_VERIFIED"
    return TrustedSourceMetadata(
        source_sha256=source_sha256,
        adapter="fixture",
        adapter_version="1",
        parser_outcome=parser_outcome,
        page_count=page_count,
        width=width,
        height=height,
        physical_size_trust=physical_size_trust,
        lossy_or_screen_capture=lossy_or_screen_capture,
    )


def test_metadata_only_cannot_pass() -> None:
    result = assess_drawing_quality(
        attachment(),
        metadata(physical_size_trust="METADATA_ONLY"),
        DrawingIntakePolicy(),
    )
    assert result.assessment.quality == "REVIEW_REQUIRED"
    assert "METADATA_ONLY_PHYSICAL_SIZE" in result.detailed_reasons
    assert workflow_reason_for_quality(result) == "DRAWING_CONFIRMATION_REQUIRED"


def test_pdf_page_limit_rejects_source() -> None:
    result = assess_drawing_quality(
        attachment("application/pdf"),
        metadata(mime="application/pdf", page_count=201),
        DrawingIntakePolicy(max_pdf_pages=200),
    )
    assert result.assessment.quality == "REJECTED"
    assert result.detailed_reasons == ("PDF_PAGE_LIMIT_EXCEEDED",)
    assert workflow_reason_for_quality(result) == "DRAWING_QUALITY_REJECTED"


def test_image_pixel_limit_rejects_without_allocating_pixels() -> None:
    result = assess_drawing_quality(
        attachment(),
        metadata(width=20_000, height=10_000),
        DrawingIntakePolicy(max_image_pixels=150_000_000),
    )
    assert result.assessment.quality == "REJECTED"
    assert result.detailed_reasons == ("IMAGE_PIXEL_LIMIT_EXCEEDED",)


def test_case_pixel_limit_includes_existing_images() -> None:
    result = assess_drawing_quality(
        attachment(),
        metadata(width=4000, height=3000),
        DrawingIntakePolicy(max_case_image_pixels=20_000_000),
        existing_case_image_pixels=10_000_000,
    )
    assert result.assessment.quality == "REJECTED"
    assert result.detailed_reasons == ("CASE_PIXEL_LIMIT_EXCEEDED",)


@pytest.mark.parametrize(
    ("outcome", "detail"),
    [
        ("TIMEOUT", "PARSER_TIMEOUT"),
        ("MEMORY_LIMIT", "PARSER_MEMORY_LIMIT"),
        ("INVALID_OUTPUT", "PARSER_OUTPUT_INVALID"),
    ],
)
def test_parser_failures_are_quality_data(outcome: str, detail: str) -> None:
    result = assess_drawing_quality(
        attachment("application/pdf"),
        metadata(mime="application/pdf", parser_outcome=outcome),
        DrawingIntakePolicy(),
    )
    assert result.assessment.quality == "REVIEW_REQUIRED"
    assert result.detailed_reasons == (detail,)
    assert workflow_reason_for_quality(result) == "DRAWING_CONFIRMATION_REQUIRED"


def test_source_hash_mismatch_is_rejected_and_maps_to_m0_reason() -> None:
    result = assess_drawing_quality(
        attachment(),
        metadata(source_sha256="b" * 64),
        DrawingIntakePolicy(),
    )
    assert result.assessment.quality == "REJECTED"
    assert result.detailed_reasons == ("SOURCE_HASH_MISMATCH",)
    assert workflow_reason_for_quality(result) == "SOURCE_HASH_MISMATCH"


def test_lossy_source_requires_review() -> None:
    result = assess_drawing_quality(
        attachment("image/jpeg"),
        metadata(mime="image/jpeg", lossy_or_screen_capture=True),
        DrawingIntakePolicy(),
    )
    assert result.assessment.quality == "REVIEW_REQUIRED"
    assert result.detailed_reasons == ("LOSSY_OR_SCREEN_CAPTURE_SOURCE",)


def test_trusted_png_can_pass() -> None:
    result = assess_drawing_quality(
        attachment(), metadata(), DrawingIntakePolicy()
    )
    assert result == DrawingQualityResult(
        assessment=result.assessment,
        detailed_reasons=(),
        policy_id="DRAWING-INTAKE-1",
        image_pixels=12_000_000,
    )
    assert result.assessment.quality == "PASS"
    assert workflow_reason_for_quality(result) is None
