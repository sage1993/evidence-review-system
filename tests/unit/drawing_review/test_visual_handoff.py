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
from evidence_review.drawing_review import visual_handoff as visual_handoff_module
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


def test_visual_handoff_prewarms_tiles_for_large_page(tmp_path: Path) -> None:
    source = tmp_path / "large-drawing.png"
    Image.new("RGB", (4097, 3906), "white").save(source)
    workspace = tmp_path / "workspace"
    attachments = prepare_case_visual_sources(workspace, supporting_images=[source])

    handoff = prepare_visual_analysis_handoff(workspace, _plan(), attachments)

    assert len(handoff.pages) == 1
    page = handoff.pages[0]
    manifest = (
        workspace
        / "case-page-tiles-v1"
        / page.attachment_id
        / "page-0001"
        / "manifest.json"
    )
    assert manifest.is_file()


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
    page = bundle["pages"][0]
    assert page["asset_path"].startswith("case-page-images-hq-v1/")
    assert page["width"] == 800.0
    assert page["height"] == 400.0
    assert (workspace / page["asset_path"]).is_file()


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


def test_visual_handoff_id_changes_when_instruction_contract_changes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "drawing.png"
    Image.new("RGB", (20, 10), "white").save(source)
    workspace = tmp_path / "workspace"
    attachments = prepare_case_visual_sources(workspace, supporting_images=[source])

    monkeypatch.setattr(
        visual_handoff_module,
        "_instruction_template_bytes",
        lambda: b"# visual contract v1\n",
    )
    first = prepare_visual_analysis_handoff(workspace, _plan(), attachments)

    monkeypatch.setattr(
        visual_handoff_module,
        "_instruction_template_bytes",
        lambda: b"# visual contract v2\n",
    )
    second = prepare_visual_analysis_handoff(workspace, _plan(), attachments)

    assert second.visual_analysis_id != first.visual_analysis_id
    assert first.instructions_path.read_bytes() == b"# visual contract v1\n"
    assert second.instructions_path.read_bytes() == b"# visual contract v2\n"


def test_visual_handoff_requires_semantically_tight_geometry(tmp_path: Path) -> None:
    source = tmp_path / "drawing.png"
    Image.new("RGB", (40, 30), "white").save(source)
    workspace = tmp_path / "workspace"
    attachments = prepare_case_visual_sources(workspace, case_drawings=[source])

    handoff = prepare_visual_analysis_handoff(workspace, _plan(), attachments)
    instructions = handoff.instructions_path.read_text(encoding="utf-8")

    assert "Geometry is source evidence, not a navigation hint" in instructions
    assert "Every boundary of a BBOX or POLYGON must be justified" in instructions
    assert "Do not include large blank areas" in instructions
    assert "project title or project-identification text" in instructions
    assert "page-scale observation" in instructions
