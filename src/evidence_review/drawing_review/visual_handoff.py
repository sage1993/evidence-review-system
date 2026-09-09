"""Deterministic external-AI handoff for case visual analysis."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

from evidence_review.canonical_json import dump_bytes, sha256_json
from evidence_review.contracts.attachments import (
    ImmutableAttachment,
    immutable_attachment_document,
)
from evidence_review.contracts.question_plan import QuestionPlan, question_plan_document
from evidence_review.drawing_review.visual_pages import (
    VisualPageAsset,
    ensure_visual_page_tiles,
    prepare_visual_page_assets,
)
from evidence_review.review_matter.scope import ReviewScope
from evidence_review.review_matter.scope_adapters import (
    normalize_review_scope,
    question_plan_from_review_scope,
)


@dataclass(frozen=True, slots=True)
class VisualAnalysisHandoff:
    """Paths and verified pages for one immutable visual-analysis handoff."""

    visual_analysis_id: str
    analysis_directory: Path
    bundle_path: Path
    instructions_path: Path
    expected_output_path: Path
    pages: tuple[VisualPageAsset, ...]


def _write_or_identical(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with path.open("xb") as stream:
            stream.write(content)
    except FileExistsError:
        if path.read_bytes() != content:
            message = f"existing visual-analysis artifact differs: {path.name}"
            raise FileExistsError(message) from None


def _instruction_template_bytes() -> bytes:
    return (
        Path(__file__).parents[1]
        / "llm_layer"
        / "templates"
        / "visual-analysis.md"
    ).read_bytes()


def _page_identity(page: VisualPageAsset) -> dict[str, object]:
    return {
        "attachment_id": page.attachment_id,
        "source_sha256": page.source_sha256,
        "page": page.page,
        "width": page.width,
        "height": page.height,
        "coordinate_system": page.coordinate_system,
        "image_sha256": page.image_sha256,
    }


def _page_document(workspace: Path, page: VisualPageAsset) -> dict[str, object]:
    document = _page_identity(page)
    document["asset_path"] = page.image_path.relative_to(workspace).as_posix()
    return document


def prepare_visual_analysis_handoff(
    workspace: Path,
    question_plan: QuestionPlan | ReviewScope,
    attachments: tuple[ImmutableAttachment, ...],
) -> VisualAnalysisHandoff:
    """Prepare raster pages and a model-safe visual-analysis bundle."""
    if not attachments:
        raise ValueError("visual analysis requires at least one attachment")
    scope = normalize_review_scope(question_plan)
    canonical_plan = question_plan_from_review_scope(scope)
    pages = prepare_visual_page_assets(workspace, attachments)
    if not pages:
        raise ValueError("VISUAL_SOURCE_RENDER_FAILED")
    for page in pages:
        ensure_visual_page_tiles(workspace, page)
    template = _instruction_template_bytes()
    instruction_contract_sha256 = hashlib.sha256(template).hexdigest()
    identity = {
        "question_plan": question_plan_document(canonical_plan),
        "attachments": [
            immutable_attachment_document(item)
            for item in sorted(attachments, key=lambda item: item.attachment_id)
        ],
        "pages": [_page_identity(item) for item in pages],
        "instruction_contract_sha256": instruction_contract_sha256,
    }
    visual_analysis_id = f"VIS-{sha256_json(identity)[:20].upper()}"
    directory = workspace / "visual-analysis" / visual_analysis_id
    bundle_path = directory / "visual-analysis-bundle.json"
    instructions_path = directory / "VISUAL_ANALYSIS_INSTRUCTIONS.md"
    expected_output_path = directory / "visual-analysis-output.json"
    bundle = {
        "format": "evidence-review/visual-analysis-bundle",
        "version": 1,
        "visual_analysis_id": visual_analysis_id,
        "instruction_contract_sha256": instruction_contract_sha256,
        "question": canonical_plan.original_question,
        "issues": [
            {"id": item.id, "question": item.question}
            for item in canonical_plan.issues
        ],
        "attachments": [
            immutable_attachment_document(item)
            for item in sorted(attachments, key=lambda item: item.attachment_id)
        ],
        "pages": [_page_document(workspace, item) for item in pages],
    }
    _write_or_identical(bundle_path, dump_bytes(bundle))
    _write_or_identical(instructions_path, template)
    return VisualAnalysisHandoff(
        visual_analysis_id=visual_analysis_id,
        analysis_directory=directory,
        bundle_path=bundle_path,
        instructions_path=instructions_path,
        expected_output_path=expected_output_path,
        pages=pages,
    )


__all__ = ["VisualAnalysisHandoff", "prepare_visual_analysis_handoff"]
