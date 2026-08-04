from __future__ import annotations

from ansim_review.canonical_json import sha256_json
from ansim_review.contracts.drawing import DrawingQualityAssessment
from ansim_review.parsing.drawing_extractors import extract_drawing_candidates
from ansim_review.parsing.odl_adapter import RawElement

SOURCE_HASH = "b" * 64


def _raw(
    element_id: str,
    element_type: str,
    text: str | None,
    *,
    semantic_type: str | None = None,
) -> RawElement:
    payload: dict[str, object] = {"type": element_type}
    if text is not None:
        payload["content"] = text
    if semantic_type is not None:
        payload["semantic_type"] = semantic_type
    return RawElement(
        element_id=element_id,
        document_id="DOC",
        revision_id="REV",
        page_number=1,
        parser_order=1,
        element_type=element_type,
        source_path=("elements", 0),
        raw_payload=payload,
        raw_payload_hash=sha256_json(payload),
        raw_bbox=(10.0, 20.0, 110.0, 120.0),
        raw_text=text,
    )


def test_stage_one_extracts_only_explicit_metadata_as_unconfirmed_candidates() -> None:
    elements = (
        _raw("SCALE", "text", "축척 1:200"),
        _raw("DIM", "text", "도로폭 8.0m"),
        _raw("TABLE", "table", None),
    )

    candidates = extract_drawing_candidates(
        case_id="CASE-001",
        source_sha256=SOURCE_HASH,
        elements=elements,
        stage=1,
        quality=DrawingQualityAssessment(
            quality="PASS",
            physical_size_trust="PDF_MEDIABOX_VERIFIED",
            reason_codes=(),
        ),
    )

    assert [item.candidate_type for item in candidates] == [
        "SCALE_TEXT",
        "DIMENSION_TEXT",
        "AREA_TABLE",
    ]
    assert all(item.status == "UNCONFIRMED" for item in candidates)
    assert all(item.origin == "EXTRACTOR" for item in candidates)
    assert extract_drawing_candidates(
        case_id="CASE-001",
        source_sha256=SOURCE_HASH,
        elements=elements,
        stage=1,
        quality=DrawingQualityAssessment(
            quality="PASS",
            physical_size_trust="PDF_MEDIABOX_VERIFIED",
            reason_codes=(),
        ),
    ) == candidates


def test_stage_two_and_three_require_declared_geometry_semantics_and_quality_pass() -> None:
    line = _raw("LINE", "line", None)
    boundary = _raw(
        "BOUNDARY",
        "path",
        None,
        semantic_type="BUILDING_OUTLINE",
    )

    stage_two = extract_drawing_candidates(
        case_id="CASE-001",
        source_sha256=SOURCE_HASH,
        elements=(line,),
        stage=2,
        quality=DrawingQualityAssessment(
            quality="PASS",
            physical_size_trust="USER_CONFIRMED",
            reason_codes=(),
        ),
    )
    assert stage_two[0].candidate_type == "DIMENSION_LINE"

    stage_three = extract_drawing_candidates(
        case_id="CASE-001",
        source_sha256=SOURCE_HASH,
        elements=(boundary,),
        stage=3,
        quality=DrawingQualityAssessment(
            quality="PASS",
            physical_size_trust="USER_CONFIRMED",
            reason_codes=(),
        ),
    )
    assert stage_three[0].candidate_type == "BUILDING_OUTLINE"

    blocked = extract_drawing_candidates(
        case_id="CASE-001",
        source_sha256=SOURCE_HASH,
        elements=(boundary,),
        stage=3,
        quality=DrawingQualityAssessment(
            quality="REVIEW_REQUIRED",
            physical_size_trust="UNKNOWN",
            reason_codes=("UNKNOWN_PHYSICAL_SIZE",),
        ),
    )
    assert blocked == ()
