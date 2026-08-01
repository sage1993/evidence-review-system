from __future__ import annotations

import pytest

from ansim_review.parsing.parser_models import (
    NormalizedParserContribution,
    PageDimensions,
    ParsedElement,
    ParsedTable,
    ParsedVisual,
)


def _element(page_number: int = 1) -> ParsedElement:
    return ParsedElement(
        element_key="element-1",
        page_number=page_number,
        parser_order=0,
        element_type="text",
        raw_payload={"type": "text", "content": "hello"},
        raw_payload_hash="b" * 64,
        raw_text="hello",
        bbox=(0.0, 0.0, 10.0, 10.0),
    )


def test_contribution_accepts_page_relative_records() -> None:
    contribution = NormalizedParserContribution(
        page_dimensions=(PageDimensions(1, 100.0, 200.0),),
        elements=(_element(),),
        tables=(
            ParsedTable(
                table_key="table-1",
                page_number=1,
                raw_payload={"cells": []},
                raw_payload_hash="c" * 64,
                bbox=(1.0, 2.0, 20.0, 30.0),
            ),
        ),
        visuals=(
            ParsedVisual(
                visual_key="visual-1",
                page_number=1,
                kind="figure",
                relative_path="visuals/page-1.png",
                sha256="d" * 64,
                bbox=None,
            ),
        ),
        parser_artifact_sha256="a" * 64,
    )

    assert contribution.page_count == 1
    assert contribution.elements[0].page_number == 1


@pytest.mark.parametrize(
    ("dimensions", "match"),
    [
        ((PageDimensions(2, 100.0, 200.0),), "PARSER_PAGE_SEQUENCE"),
        ((PageDimensions(1, 0.0, 200.0),), "page dimensions must be positive"),
    ],
)
def test_page_dimensions_are_contiguous_and_positive(
    dimensions: tuple[PageDimensions, ...], match: str
) -> None:
    with pytest.raises(ValueError, match=match):
        NormalizedParserContribution(
            page_dimensions=dimensions,
            elements=(),
            tables=(),
            visuals=(),
            parser_artifact_sha256="a" * 64,
        )


def test_contribution_rejects_record_for_unknown_page() -> None:
    with pytest.raises(ValueError, match="PARSER_PAGE_NOT_FOUND"):
        NormalizedParserContribution(
            page_dimensions=(PageDimensions(1, 100.0, 200.0),),
            elements=(_element(page_number=2),),
            tables=(),
            visuals=(),
            parser_artifact_sha256="a" * 64,
        )


def test_contribution_rejects_bbox_outside_page() -> None:
    with pytest.raises(ValueError, match="BBOX_OUT_OF_PAGE"):
        NormalizedParserContribution(
            page_dimensions=(PageDimensions(1, 100.0, 200.0),),
            elements=(
                ParsedElement(
                    element_key="element-1",
                    page_number=1,
                    parser_order=0,
                    element_type="text",
                    raw_payload={},
                    raw_payload_hash="b" * 64,
                    raw_text=None,
                    bbox=(0.0, 0.0, 101.0, 10.0),
                ),
            ),
            tables=(),
            visuals=(),
            parser_artifact_sha256="a" * 64,
        )


def test_contribution_rejects_invalid_parser_artifact_hash() -> None:
    with pytest.raises(ValueError, match="parser_artifact_sha256"):
        NormalizedParserContribution(
            page_dimensions=(PageDimensions(1, 100.0, 200.0),),
            elements=(),
            tables=(),
            visuals=(),
            parser_artifact_sha256="A" * 64,
        )
