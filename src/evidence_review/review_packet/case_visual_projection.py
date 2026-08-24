"""Verified case-visual projection for the default Review Workspace."""
from __future__ import annotations

import base64
import hashlib
import json
import math
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import cast

from evidence_review.contracts.attachments import ImmutableAttachment, decode_immutable_attachment
from evidence_review.contracts.drawing import decode_drawing_candidate, drawing_candidate_document
from evidence_review.contracts.identifiers import validate_identifier
from evidence_review.drawing_review.visual_pages import (
    VisualPageAsset,
    ensure_visual_page_tiles,
)
from evidence_review.review_packet.visual_findings import build_semantic_visual_findings


_CASE_PDF_CACHE_DIR = "case-page-images-hq-v1"
_CASE_IMAGE_CACHE_DIR = "case-page-images"


def _mapping(value: object, field: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping) or not all(isinstance(key, str) for key in value):
        raise ValueError(f"{field} must be an object")
    return cast(Mapping[str, object], value)


def _sequence(value: object, field: str) -> Sequence[object]:
    if isinstance(value, (str, bytes, bytearray)) or not isinstance(value, Sequence):
        raise ValueError(f"{field} must be an array")
    return cast(Sequence[object], value)


def _string(value: object, field: str, *, allow_empty: bool = False) -> str:
    if not isinstance(value, str) or (not allow_empty and not value):
        raise ValueError(f"{field} must be a string")
    return value


def _positive_int(value: object, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValueError(f"{field} must be a positive integer")
    return value


def _finite_number(value: object, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{field} must be a finite number")
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"{field} must be a finite number")
    return result


def _positive_number(value: object, field: str) -> float:
    result = _finite_number(value, field)
    if result <= 0:
        raise ValueError(f"{field} must be a positive number")
    return result


def _json(path: Path) -> Mapping[str, object]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ValueError(f"invalid case visual artifact: {path.name}") from error
    return _mapping(value, path.name)


def _issue_questions(inputs: Mapping[str, object]) -> dict[str, str]:
    value = inputs.get("question_plan")
    if value is None:
        return {}
    plan = _mapping(value, "inputs.question_plan")
    questions: dict[str, str] = {}
    issues = _sequence(plan.get("issues", []), "inputs.question_plan.issues")
    for index, item in enumerate(issues):
        issue = _mapping(item, f"inputs.question_plan.issues[{index}]")
        issue_id = _string(issue.get("id"), f"inputs.question_plan.issues[{index}].id")
        question = _string(
            issue.get("question"),
            f"inputs.question_plan.issues[{index}].question",
            allow_empty=True,
        )
        if issue_id in questions:
            raise ValueError("duplicate question-plan issue id")
        questions[issue_id] = question
    return questions


def _claim_links(track_a: Mapping[str, object]) -> dict[str, list[dict[str, object]]]:
    links: dict[str, list[dict[str, object]]] = {}
    claims = _sequence(track_a.get("claims", []), "track_a.claims")
    for index, item in enumerate(claims):
        claim = _mapping(item, f"track_a.claims[{index}]")
        claim_id = _string(claim.get("claim_id"), f"track_a.claims[{index}].claim_id")
        claim_text = _string(
            claim.get("text"), f"track_a.claims[{index}].text", allow_empty=True
        )
        issue_values = _sequence(
            claim.get("issue_ids", []), f"track_a.claims[{index}].issue_ids"
        )
        issue_ids = tuple(
            _string(value, f"track_a.claims[{index}].issue_ids")
            for value in issue_values
        )
        citation_values = _sequence(
            claim.get("citation_ids", []), f"track_a.claims[{index}].citation_ids"
        )
        citation_ids = tuple(
            _string(value, f"track_a.claims[{index}].citation_ids")
            for value in citation_values
        )
        candidate_values = _sequence(
            claim.get("drawing_candidate_ids", []),
            f"track_a.claims[{index}].drawing_candidate_ids",
        )
        candidate_ids = tuple(
            _string(value, f"track_a.claims[{index}].drawing_candidate_ids")
            for value in candidate_values
        )
        for candidate_id in candidate_ids:
            links.setdefault(candidate_id, []).append(
                {
                    "claim_id": claim_id,
                    "text": claim_text,
                    "issue_ids": list(issue_ids),
                    "citation_ids": list(citation_ids),
                }
            )
    return links


def _review_statuses(view_model: Mapping[str, object]) -> dict[str, str]:
    """Return statuses only when a claim is actually connected to deterministic rules."""
    result: dict[str, str] = {}
    items = _sequence(view_model.get("review_items", []), "review_items")
    for index, item in enumerate(items):
        review_item = _mapping(item, f"review_items[{index}]")
        claim_id = review_item.get("claim_id")
        status = review_item.get("status")
        rule_ids = _sequence(
            review_item.get("rule_ids", []),
            f"review_items[{index}].rule_ids",
        )
        if (
            rule_ids
            and isinstance(claim_id, str)
            and claim_id
            and isinstance(status, str)
            and status
        ):
            result[claim_id] = status
    return result


def _tone(statuses: Sequence[str]) -> str:
    normalized = {item.upper() for item in statuses}
    if normalized & {"NOT_SATISFIED", "FAILED", "FAIL", "REJECTED"}:
        return "issue"
    if normalized & {
        "INDETERMINATE",
        "REVIEW_REQUIRED",
        "PARTIALLY_RESOLVED",
        "ABSTAIN",
        "CONDITIONAL",
    }:
        return "review"
    if normalized & {"SATISFIED", "PASS", "PASSED"}:
        return "compliant"
    return "observation"


def _verify_geometry_bounds(
    candidate: Mapping[str, object], width: float, height: float
) -> None:
    geometry = _mapping(candidate.get("geometry"), "drawing_candidate.geometry")
    if geometry.get("coordinate_system") != "IMAGE_TOP_LEFT_PIXELS":
        raise ValueError("case visual candidate must use IMAGE_TOP_LEFT_PIXELS")
    geometry_type = _string(geometry.get("type"), "drawing_candidate.geometry.type")
    coordinates = _sequence(
        geometry.get("coordinates"), "drawing_candidate.geometry.coordinates"
    )

    points: list[tuple[float, float]] = []
    if geometry_type == "POINT":
        if len(coordinates) != 2:
            raise ValueError("visual POINT coordinates are invalid")
        points = [
            (
                _finite_number(coordinates[0], "drawing_candidate.geometry.x"),
                _finite_number(coordinates[1], "drawing_candidate.geometry.y"),
            )
        ]
    elif geometry_type == "BBOX":
        if len(coordinates) != 4:
            raise ValueError("visual BBOX coordinates are invalid")
        left, top, right, bottom = (
            _finite_number(value, "drawing_candidate.geometry.coordinate")
            for value in coordinates
        )
        points = [(left, top), (right, bottom)]
    else:
        for point in coordinates:
            values = _sequence(point, "drawing_candidate.geometry.point")
            if len(values) != 2:
                raise ValueError("visual path coordinates are invalid")
            points.append(
                (
                    _finite_number(values[0], "drawing_candidate.geometry.point.x"),
                    _finite_number(values[1], "drawing_candidate.geometry.point.y"),
                )
            )
    for x, y in points:
        if x < 0 or y < 0 or x > width or y > height:
            raise ValueError("visual geometry is outside the verified raster page")


def _resolve_visual_raster_path(
    workspace_root: Path,
    attachment_id: str,
    page_number: int,
    expected_sha256: str,
) -> Path:
    """Resolve the exact verified raster, preferring the 4x PDF cache."""
    candidates = (
        workspace_root
        / _CASE_PDF_CACHE_DIR
        / attachment_id
        / f"page-{page_number:04d}.png",
        workspace_root
        / _CASE_IMAGE_CACHE_DIR
        / attachment_id
        / f"page-{page_number:04d}.png",
    )
    existing = [path for path in candidates if path.is_file()]
    for path in existing:
        if hashlib.sha256(path.read_bytes()).hexdigest() == expected_sha256:
            return path
    if existing:
        raise ValueError("case visual raster hash mismatch")
    raise FileNotFoundError(candidates[0])


def _page_tile_documents(
    workspace_root: Path,
    asset: VisualPageAsset,
) -> list[dict[str, object]]:
    tiles = ensure_visual_page_tiles(workspace_root, asset)
    documents: list[dict[str, object]] = []
    for tile in tiles:
        data = tile.path.read_bytes()
        if hashlib.sha256(data).hexdigest() != tile.image_sha256:
            raise ValueError("case visual tile hash mismatch")
        documents.append(
            {
                "x": tile.x,
                "y": tile.y,
                "width": tile.width,
                "height": tile.height,
                "image_sha256": tile.image_sha256,
                "data_uri": "data:image/png;base64," + base64.b64encode(data).decode("ascii"),
            }
        )
    return documents


def build_case_visual_projection(
    view_model: Mapping[str, object],
    *,
    workspace_root: Path,
) -> dict[str, object] | None:
    """Project immutable visual evidence into a self-contained reviewer model."""
    run_id = validate_identifier(view_model.get("run_id"), "view_model.run_id")
    run_directory = workspace_root / "runs" / run_id
    bundle_path = run_directory / "track-a-bundle.json"
    track_a_path = run_directory / "track-a-output.json"
    if not bundle_path.is_file():
        return None
    bundle = _json(bundle_path)
    inputs = _mapping(bundle.get("inputs"), "track_a_bundle.inputs")
    raw_context = inputs.get("case_visual_context")
    if raw_context is None:
        return None
    context = _mapping(raw_context, "inputs.case_visual_context")
    if context.get("visual_status") != "VISUAL_ANALYSIS_VALIDATED":
        raise ValueError("case visual context is not validated")
    if not track_a_path.is_file():
        raise ValueError("validated case visual review requires track-a-output.json")

    attachments = [
        decode_immutable_attachment(item)
        for item in _sequence(
            context.get("attachments", []), "case_visual_context.attachments"
        )
    ]
    attachment_by_id: dict[str, ImmutableAttachment] = {}
    for attachment in attachments:
        attachment_id = validate_identifier(attachment.attachment_id, "attachment_id")
        if attachment_id in attachment_by_id:
            raise ValueError("duplicate case visual attachment id")
        attachment_by_id[attachment_id] = attachment

    page_records: dict[tuple[str, int], dict[str, object]] = {}
    page_by_source: dict[tuple[str, int], tuple[str, int]] = {}
    visual_pages = _sequence(
        context.get("visual_pages", []), "case_visual_context.visual_pages"
    )
    for index, item in enumerate(visual_pages):
        page = _mapping(item, f"case_visual_context.visual_pages[{index}]")
        attachment_id = validate_identifier(
            page.get("attachment_id"), "visual_page.attachment_id"
        )
        source_sha256 = _string(page.get("source_sha256"), "visual_page.source_sha256")
        page_number = _positive_int(page.get("page"), "visual_page.page")
        width = _positive_number(page.get("width"), "visual_page.width")
        height = _positive_number(page.get("height"), "visual_page.height")
        coordinate_system = _string(
            page.get("coordinate_system"), "visual_page.coordinate_system"
        )
        image_sha256 = _string(page.get("image_sha256"), "visual_page.image_sha256")
        page_attachment = attachment_by_id.get(attachment_id)
        if page_attachment is None or page_attachment.sha256 != source_sha256:
            raise ValueError("visual page attachment/source binding mismatch")
        if coordinate_system != "IMAGE_TOP_LEFT_PIXELS":
            raise ValueError("visual page coordinate system is unsupported")
        key = (attachment_id, page_number)
        source_key = (source_sha256, page_number)
        if key in page_records or source_key in page_by_source:
            raise ValueError("case visual page identity is ambiguous")
        image_path = _resolve_visual_raster_path(
            workspace_root,
            attachment_id,
            page_number,
            image_sha256,
        )
        image_bytes = image_path.read_bytes()
        asset = VisualPageAsset(
            attachment_id=attachment_id,
            source_sha256=source_sha256,
            page=page_number,
            width=width,
            height=height,
            coordinate_system="IMAGE_TOP_LEFT_PIXELS",
            image_path=image_path,
            image_sha256=image_sha256,
        )
        tile_documents = _page_tile_documents(workspace_root, asset)
        page_record: dict[str, object] = {
            "asset_key": f"{attachment_id}-p{page_number}",
            "attachment_id": attachment_id,
            "document_name": page_attachment.original_name,
            "source_sha256": source_sha256,
            "page": page_number,
            "width": width,
            "height": height,
            "coordinate_system": coordinate_system,
            "image_sha256": image_sha256,
            "candidates": [],
        }
        if tile_documents:
            page_record["tiles"] = tile_documents
        else:
            page_record["data_uri"] = "data:image/png;base64," + base64.b64encode(
                image_bytes
            ).decode("ascii")
        page_records[key] = page_record
        page_by_source[source_key] = key

    lineage: dict[str, tuple[str, ...]] = {}
    lineage_values = _sequence(
        context.get("candidate_lineage", []), "case_visual_context.candidate_lineage"
    )
    for index, item in enumerate(lineage_values):
        entry = _mapping(item, f"case_visual_context.candidate_lineage[{index}]")
        candidate_id = _string(entry.get("candidate_id"), "candidate_lineage.candidate_id")
        issue_values = _sequence(entry.get("issue_ids", []), "candidate_lineage.issue_ids")
        lineage_issue_ids = tuple(
            _string(value, "candidate_lineage.issue_ids") for value in issue_values
        )
        if not lineage_issue_ids or candidate_id in lineage:
            raise ValueError("case visual candidate lineage is invalid")
        lineage[candidate_id] = lineage_issue_ids

    track_a = _json(track_a_path)
    claim_links = _claim_links(track_a)
    statuses = _review_statuses(view_model)
    issue_questions = _issue_questions(inputs)
    seen_candidates: set[str] = set()

    candidate_values = _sequence(
        context.get("drawing_candidates", []), "case_visual_context.drawing_candidates"
    )
    for raw_candidate in candidate_values:
        candidate = decode_drawing_candidate(raw_candidate)
        if candidate.candidate_id in seen_candidates:
            raise ValueError("duplicate case visual candidate id")
        seen_candidates.add(candidate.candidate_id)
        page_key = page_by_source.get((candidate.source_sha256, candidate.page))
        if page_key is None:
            raise ValueError("case visual candidate has no verified raster page")
        page = page_records[page_key]
        canonical = drawing_candidate_document(candidate)
        _verify_geometry_bounds(
            canonical,
            cast(float, page["width"]),
            cast(float, page["height"]),
        )
        candidate_issue_ids = lineage.get(candidate.candidate_id)
        if candidate_issue_ids is None:
            raise ValueError("case visual candidate has no issue lineage")
        links: list[dict[str, object]] = []
        linked_statuses: set[str] = set()
        for raw_link in claim_links.get(candidate.candidate_id, []):
            link = dict(raw_link)
            claim_id = cast(str, link["claim_id"])
            relation = "direct" if claim_id in statuses else "related"
            link["relation"] = relation
            links.append(link)
            if relation == "direct":
                linked_statuses.add(statuses[claim_id])
        sorted_statuses = sorted(linked_statuses)
        projected = dict(canonical)
        projected.update(
            {
                "issue_ids": list(candidate_issue_ids),
                "issue_questions": [
                    issue_questions.get(issue_id, "")
                    for issue_id in candidate_issue_ids
                ],
                "claims": links,
                "review_statuses": sorted_statuses,
                "tone": _tone(sorted_statuses),
                "display_value": (
                    candidate.normalized_candidate
                    if candidate.normalized_candidate not in (None, "")
                    else candidate.raw_value
                    if candidate.raw_value not in (None, "")
                    else candidate.candidate_type
                ),
            }
        )
        cast(list[object], page["candidates"]).append(projected)

    if set(lineage) != seen_candidates:
        raise ValueError("case visual lineage does not match drawing candidates")

    pages = [page_records[key] for key in sorted(page_records)]
    findings = build_semantic_visual_findings(pages)
    return {
        "status": "VISUAL_ANALYSIS_VALIDATED",
        "attachment_count": len(attachments),
        "candidate_count": len(seen_candidates),
        "finding_count": len(findings),
        "pages": pages,
        "findings": findings,
    }


__all__ = ["build_case_visual_projection"]
