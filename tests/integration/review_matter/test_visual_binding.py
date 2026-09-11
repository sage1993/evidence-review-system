from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
from PIL import Image

from evidence_review.case_visual import (
    bind_case_visual_context_to_review_request,
    prepare_case_visual_sources,
    visual_case_from_attachments,
)
from evidence_review.contracts.attachments import ImmutableAttachment
from evidence_review.contracts.drawing import Geometry
from evidence_review.contracts.question_plan import QuestionIssue, SearchRequest
from evidence_review.drawing_review.visual_handoff import prepare_visual_analysis_handoff
from evidence_review.drawing_review.visual_pages import (
    VisualPageAsset,
    prepare_visual_page_assets,
)
from evidence_review.drawing_review.visual_submission import validate_visual_analysis_output
from evidence_review.parsing.drawing_candidates import create_manual_candidate
from evidence_review.review_matter.contracts import MatterSourceBinding
from evidence_review.review_matter.scope_adapters import (
    question_plan_from_review_scope,
    review_scope_from_explicit_input,
)
from evidence_review.review_matter.store import MatterStore
from evidence_review.review_matter.visual_binding import bind_visual_case_to_matter


def _write_png(path: Path, color: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (20, 10), color).save(path, format="PNG")
    return path


def _scope():
    issue = QuestionIssue(
        id="ISSUE-001",
        question="Is the entrance visible?",
        depends_on=(),
        required_evidence_roles=("supporting_fact",),
    )
    return review_scope_from_explicit_input(
        question="Is the entrance visible?",
        issues=(issue,),
        search_requests=(
            SearchRequest(
                id="SEARCH-001",
                issue_ids=(issue.id,),
                text="entrance",
                kind="phrase",
                source="user",
                role="supporting_fact",
            ),
        ),
    )


def _candidate(case_id: str, source_sha256: str, annotation_id: str):
    return create_manual_candidate(
        case_id=case_id,
        source_sha256=source_sha256,
        page=1,
        annotation_id=annotation_id,
        candidate_type="ENTRANCE",
        geometry=Geometry(
            type="BBOX",
            coordinate_system="IMAGE_TOP_LEFT_PIXELS",
            coordinates=(1.0, 1.0, 5.0, 5.0),
        ),
        raw_value="entrance",
        normalized_candidate=None,
    )


def _matter_source_binding(binding_id: str, source_hash: str) -> MatterSourceBinding:
    return MatterSourceBinding(
        binding_id=binding_id,
        document_id="DOC-001",
        revision_id="REV-001",
        page_number=1,
        evidence_id=f"EVID-{binding_id}",
        bbox=(1.0, 1.0, 2.0, 2.0),
        source_hash=source_hash,
        evidence_snapshot_hash="c" * 64,
        evidence_db_sha256="d" * 64,
    )


def _store_for_visual_case(
    tmp_path: Path,
    visual_case,
    *,
    matter_id: str = "MATTER-001",
) -> tuple[MatterStore, dict[str, str]]:
    source_binding_ids: dict[str, str] = {}
    source_bindings: list[MatterSourceBinding] = []
    for index, attachment in enumerate(visual_case.attachments, start=1):
        binding_id = f"BINDING-{index:03d}"
        source_binding_ids[attachment.attachment_id] = binding_id
        source_bindings.append(_matter_source_binding(binding_id, attachment.sha256))
    store = MatterStore(tmp_path / "review-matters.sqlite")
    store.create(
        matter_id=matter_id,
        title="Visual review",
        source_bindings=tuple(source_bindings),
    )
    return store, source_binding_ids


def test_visual_candidate_from_other_source_cannot_bind_to_matter(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    first = _write_png(tmp_path / "a" / "plan.png", "white")
    second = _write_png(tmp_path / "b" / "plan.png", "black")
    visual_case = visual_case_from_attachments(
        prepare_case_visual_sources(workspace, case_drawings=[first])
    )
    other_case = visual_case_from_attachments(
        prepare_case_visual_sources(workspace, case_drawings=[second])
    )
    store, source_binding_ids = _store_for_visual_case(tmp_path, visual_case)

    with pytest.raises(ValueError, match="VISUAL_SOURCE_BINDING_MISMATCH"):
        bind_visual_case_to_matter(
            store,
            matter_id="MATTER-001",
            expected_revision=1,
            visual_case=visual_case,
            expected_source_binding_ids=source_binding_ids,
            candidates=(
                _candidate(
                    other_case.case_id,
                    other_case.attachments[0].sha256,
                    "ANN-OTHER",
                ),
            ),
        )

    assert store.load("MATTER-001").revision == 1


def test_visual_binding_retains_attachment_ids_for_same_basename(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    first = _write_png(tmp_path / "first" / "plan.png", "white")
    second = _write_png(tmp_path / "second" / "plan.png", "black")
    visual_case = visual_case_from_attachments(
        prepare_case_visual_sources(workspace, case_drawings=[first, second])
    )
    store, source_binding_ids = _store_for_visual_case(tmp_path, visual_case)

    binding = bind_visual_case_to_matter(
        store,
        matter_id="MATTER-001",
        expected_revision=1,
        visual_case=visual_case,
        expected_source_binding_ids=source_binding_ids,
    )

    assert binding.matter_id == "MATTER-001"
    assert binding.visual_case.case_id == visual_case.case_id
    assert [(item.attachment_id, item.source_sha256) for item in binding.attachments] == [
        (item.attachment_id, item.sha256) for item in visual_case.attachments
    ]
    assert len({item.attachment_id for item in binding.attachments}) == 2


def test_visual_handoff_preserves_validated_review_scope_context(tmp_path: Path) -> None:
    source = _write_png(tmp_path / "plan.png", "white")
    workspace = tmp_path / "workspace"
    attachments = prepare_case_visual_sources(workspace, case_drawings=[source])
    scope = _scope()

    handoff = prepare_visual_analysis_handoff(workspace, scope, attachments)

    bundle = json.loads(handoff.bundle_path.read_text(encoding="utf-8"))
    assert bundle["review_scope"]["origin"] == "EXPLICIT_USER"
    assert bundle["review_scope"]["question_plan_sha256"] is None
    assert bundle["issues"] == [{"id": "ISSUE-001", "question": "Is the entrance visible?"}]


def test_visual_candidate_from_other_case_with_same_source_cannot_bind(tmp_path: Path) -> None:
    source = _write_png(tmp_path / "plan.png", "white")
    source_sha256 = hashlib.sha256(source.read_bytes()).hexdigest()
    common = {
        "attachment_id": "ATT-SHARED",
        "original_name": "plan.png",
        "sha256": source_sha256,
        "byte_size": source.stat().st_size,
        "mime": "image/png",
        "role": "CASE_DRAWING",
    }
    case_a = ImmutableAttachment(
        **common,
        case_id="CASE-VIS-A",
        stored_path="cases/CASE-VIS-A/sources/drawings/ATT-SHARED.png",
    )
    visual_case = visual_case_from_attachments((case_a,))
    store, source_binding_ids = _store_for_visual_case(tmp_path, visual_case)

    with pytest.raises(ValueError, match="VISUAL_SOURCE_BINDING_MISMATCH"):
        bind_visual_case_to_matter(
            store,
            matter_id="MATTER-001",
            expected_revision=1,
            visual_case=visual_case,
            expected_source_binding_ids=source_binding_ids,
            candidates=(
                _candidate("CASE-VIS-B", source_sha256, "ANN-OTHER-CASE"),
            ),
        )


def test_visual_case_cannot_bind_to_matter_with_other_source_binding(
    tmp_path: Path,
) -> None:
    source = _write_png(tmp_path / "plan.png", "white")
    source_sha256 = hashlib.sha256(source.read_bytes()).hexdigest()
    attachment = ImmutableAttachment(
        attachment_id="ATT-VISUAL-001",
        original_name="plan.png",
        stored_path="cases/CASE-VIS-A/sources/drawings/ATT-VISUAL-001.png",
        sha256=source_sha256,
        byte_size=source.stat().st_size,
        mime="image/png",
        role="CASE_DRAWING",
        case_id="CASE-VIS-A",
    )
    visual_case = visual_case_from_attachments((attachment,))
    store = MatterStore(tmp_path / "review-matters.sqlite")
    store.create(
        matter_id="MATTER-OTHER",
        title="Other visual review",
        source_bindings=(_matter_source_binding("BINDING-OTHER", "e" * 64),),
    )

    with pytest.raises(ValueError, match="MATTER_VISUAL_SOURCE_BINDING_MISMATCH"):
        bind_visual_case_to_matter(
            store,
            matter_id="MATTER-OTHER",
            expected_revision=1,
            visual_case=visual_case,
            expected_source_binding_ids={"ATT-VISUAL-001": "BINDING-OTHER"},
        )


def test_active_request_binding_rejects_candidate_from_other_case_with_same_source(
    tmp_path: Path,
) -> None:
    source = _write_png(tmp_path / "plan.png", "white")
    source_sha256 = hashlib.sha256(source.read_bytes()).hexdigest()
    attachment = ImmutableAttachment(
        attachment_id="ATT-VISUAL-001",
        original_name="plan.png",
        stored_path="cases/CASE-VIS-A/sources/drawings/ATT-VISUAL-001.png",
        sha256=source_sha256,
        byte_size=source.stat().st_size,
        mime="image/png",
        role="CASE_DRAWING",
        case_id="CASE-VIS-A",
    )
    candidate = _candidate("CASE-VIS-B", source_sha256, "ANN-OTHER-CASE")
    page = VisualPageAsset(
        case_id="CASE-VIS-A",
        attachment_id=attachment.attachment_id,
        source_sha256=source_sha256,
        page=1,
        width=20.0,
        height=10.0,
        coordinate_system="IMAGE_TOP_LEFT_PIXELS",
        image_path=tmp_path / "page.png",
        image_sha256="f" * 64,
    )

    with pytest.raises(ValueError, match="drawing candidate case is not bound"):
        bind_case_visual_context_to_review_request(
            {"inputs": {}},
            (attachment,),
            (candidate,),
            candidate_issue_ids={candidate.candidate_id: ("ISSUE-001",)},
            visual_page_assets=(page,),
            visual_analysis_completed=True,
        )


def test_visual_submission_binds_same_basename_by_case_and_attachment_identity(
    tmp_path: Path,
) -> None:
    first = ImmutableAttachment(
        attachment_id="ATT-VISUAL-A",
        original_name="plan.png",
        stored_path="cases/CASE-VIS-A/sources/drawings/ATT-VISUAL-A.png",
        sha256="a" * 64,
        byte_size=100,
        mime="image/png",
        role="CASE_DRAWING",
        case_id="CASE-VIS-A",
    )
    second = ImmutableAttachment(
        attachment_id="ATT-VISUAL-B",
        original_name="plan.png",
        stored_path="cases/CASE-VIS-B/sources/drawings/ATT-VISUAL-B.png",
        sha256="b" * 64,
        byte_size=100,
        mime="image/png",
        role="CASE_DRAWING",
        case_id="CASE-VIS-B",
    )
    first_page = VisualPageAsset(
        case_id=first.case_id,
        attachment_id=first.attachment_id,
        source_sha256=first.sha256,
        page=1,
        width=20.0,
        height=10.0,
        coordinate_system="IMAGE_TOP_LEFT_PIXELS",
        image_path=tmp_path / "first-page.png",
        image_sha256="c" * 64,
    )
    second_page = VisualPageAsset(
        case_id=second.case_id,
        attachment_id=second.attachment_id,
        source_sha256=second.sha256,
        page=1,
        width=20.0,
        height=10.0,
        coordinate_system="IMAGE_TOP_LEFT_PIXELS",
        image_path=tmp_path / "second-page.png",
        image_sha256="d" * 64,
    )
    question_plan = question_plan_from_review_scope(_scope())
    result = validate_visual_analysis_output(
        {
            "format": "evidence-review/visual-analysis-output",
            "version": 1,
            "visual_analysis_id": "VIS-TEST",
            "observations": [
                {
                    "attachment_id": first.attachment_id,
                    "source_sha256": first.sha256,
                    "page": 1,
                    "issue_ids": ["ISSUE-001"],
                    "candidate_type": "ENTRANCE",
                    "geometry": {
                        "type": "BBOX",
                        "coordinate_system": "IMAGE_TOP_LEFT_PIXELS",
                        "coordinates": [1.0, 1.0, 5.0, 5.0],
                    },
                    "raw_value": "entrance",
                    "normalized_candidate": None,
                }
            ],
        },
        expected_visual_analysis_id="VIS-TEST",
        question_plan=question_plan,
        attachments=(first, second),
        pages=(first_page, second_page),
    )
    candidate = result.candidates[0]

    bound = bind_case_visual_context_to_review_request(
        {"inputs": {}},
        (first, second),
        (candidate,),
        candidate_issue_ids=result.candidate_issue_ids,
        visual_page_assets=(first_page, second_page),
        visual_analysis_completed=True,
    )

    candidate_document = bound["inputs"]["case_visual_context"]["drawing_candidates"][0]
    assert candidate_document["case_id"] == "CASE-VIS-A"
    assert candidate_document["source_sha256"] == "a" * 64


def test_visual_page_rejects_mime_mismatch_before_decoder(tmp_path: Path) -> None:
    source = _write_png(tmp_path / "plan.png", "white")
    workspace = tmp_path / "workspace"
    attachment = prepare_case_visual_sources(workspace, case_drawings=[source])[0]
    wrong_mime = attachment.__class__(
        attachment_id=attachment.attachment_id,
        original_name=attachment.original_name,
        stored_path=attachment.stored_path,
        sha256=attachment.sha256,
        byte_size=attachment.byte_size,
        mime="image/jpeg",
        role=attachment.role,
        case_id=attachment.case_id,
    )

    with pytest.raises(ValueError, match="MIME/content binding mismatch"):
        prepare_visual_page_assets(workspace, (wrong_mime,))


def test_visual_binding_does_not_promote_candidate_to_confirmed_input(tmp_path: Path) -> None:
    source = _write_png(tmp_path / "plan.png", "white")
    workspace = tmp_path / "workspace"
    visual_case = visual_case_from_attachments(
        prepare_case_visual_sources(workspace, case_drawings=[source])
    )
    store, source_binding_ids = _store_for_visual_case(tmp_path, visual_case)
    candidate = _candidate(
        visual_case.case_id,
        visual_case.attachments[0].sha256,
        "ANN-001",
    )

    binding = bind_visual_case_to_matter(
        store,
        matter_id="MATTER-001",
        expected_revision=1,
        visual_case=visual_case,
        expected_source_binding_ids=source_binding_ids,
        candidates=(candidate,),
    )

    assert binding.candidates == (candidate,)
    assert candidate.status == "CREATED"
    assert hashlib.sha256(source.read_bytes()).hexdigest() == candidate.source_sha256
