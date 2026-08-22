from __future__ import annotations

import json
from pathlib import Path

import pytest
from PIL import Image
from pypdf import PdfWriter

from evidence_review.case_visual import prepare_case_visual_sources
from evidence_review.contracts.question_plan import (
    QuestionIssue,
    QuestionPlan,
    SearchRequest,
)
from evidence_review.drawing_review.visual_handoff import prepare_visual_analysis_handoff


def _plan() -> QuestionPlan:
    return QuestionPlan(
        original_question="첨부 이미지를 보고 주출입구를 확인해줘",
        facts=(),
        assumptions=(),
        issues=(
            QuestionIssue(
                id="ISSUE-1",
                question="주출입구 위치는 어디인가?",
                depends_on=(),
                required_evidence_roles=("supporting_fact",),
            ),
        ),
        legal_anchors=(),
        search_requests=(
            SearchRequest(
                id="SEARCH-1",
                issue_ids=("ISSUE-1",),
                text="주출입구 위치",
                kind="phrase",
                source="planner",
                role="supporting_fact",
            ),
        ),
    )


def test_visual_handoff_exposes_actual_raster_page_without_reference_parser(
    tmp_path: Path,
) -> None:
    source = tmp_path / "drawing.png"
    Image.new("RGB", (40, 30), "white").save(source)
    workspace = tmp_path / "workspace"
    attachments = prepare_case_visual_sources(workspace, case_drawings=[source])

    handoff = prepare_visual_analysis_handoff(workspace, _plan(), attachments)

    assert handoff.bundle_path.is_file()
    assert handoff.instructions_path.is_file()
    bundle = json.loads(handoff.bundle_path.read_text(encoding="utf-8"))
    assert bundle["visual_analysis_id"] == handoff.visual_analysis_id
    assert bundle["attachments"][0]["role"] == "CASE_DRAWING"
    assert bundle["pages"][0]["coordinate_system"] == "IMAGE_TOP_LEFT_PIXELS"
    asset = workspace / bundle["pages"][0]["asset_path"]
    assert asset.is_file()
    assert asset.suffix == ".png"
    assert "parser" not in bundle["attachments"][0]


def test_visual_handoff_rasterizes_case_pdf_without_reference_ingestion(
    tmp_path: Path,
) -> None:
    source = tmp_path / "drawing.pdf"
    writer = PdfWriter()
    writer.add_blank_page(width=200, height=100)
    with source.open("wb") as stream:
        writer.write(stream)
    workspace = tmp_path / "workspace"
    attachments = prepare_case_visual_sources(workspace, case_drawings=[source])

    handoff = prepare_visual_analysis_handoff(workspace, _plan(), attachments)
    bundle = json.loads(handoff.bundle_path.read_text(encoding="utf-8"))

    assert bundle["attachments"][0]["mime"] == "application/pdf"
    assert bundle["attachments"][0]["role"] == "CASE_DRAWING"
    assert len(bundle["pages"]) == 1
    assert bundle["pages"][0]["asset_path"].startswith("case-page-images/")
    assert (workspace / bundle["pages"][0]["asset_path"]).is_file()


def test_invalid_case_pdf_fails_as_visual_render_before_formal_review(
    tmp_path: Path,
) -> None:
    source = tmp_path / "broken.pdf"
    source.write_bytes(b"%PDF-1.7\nnot-a-valid-pdf")
    workspace = tmp_path / "workspace"
    attachments = prepare_case_visual_sources(workspace, case_drawings=[source])

    with pytest.raises(ValueError) as captured:
        prepare_visual_analysis_handoff(workspace, _plan(), attachments)

    message = str(captured.value)
    assert "PAGE_DIMENSIONS_UNAVAILABLE" in message or "PAGE_RENDER_FAILED" in message
    assert "PARSER_SOURCE_PDF_INVALID" not in message
    assert not (workspace / "runs").exists()


def test_visual_handoff_is_reusable_for_identical_source(tmp_path: Path) -> None:
    source = tmp_path / "drawing.png"
    Image.new("RGB", (20, 10), "white").save(source)
    workspace = tmp_path / "workspace"
    attachments = prepare_case_visual_sources(workspace, supporting_images=[source])

    first = prepare_visual_analysis_handoff(workspace, _plan(), attachments)
    second = prepare_visual_analysis_handoff(workspace, _plan(), attachments)

    assert second.visual_analysis_id == first.visual_analysis_id
    assert second.bundle_path.read_bytes() == first.bundle_path.read_bytes()
