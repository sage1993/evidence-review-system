"""Verified case-visual projection for the default Review Workspace."""
from __future__ import annotations

import base64
import hashlib
import json
import math
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import cast

from evidence_review.contracts.attachments import (
    ImmutableAttachment,
    decode_immutable_attachment,
)
from evidence_review.contracts.drawing import (
    decode_drawing_candidate,
    drawing_candidate_document,
)
from evidence_review.contracts.identifiers import validate_identifier
from evidence_review.drawing_review.visual_pages import (
    VisualPageAsset,
    load_visual_page_tiles,
    visual_cache_identity,
)
from evidence_review.filesystem_trust import verified_regular_file_below
from evidence_review.review_packet.reference_pages import build_reference_projection
from evidence_review.review_packet.related_reference_routing import (
    bind_related_retrieval_references,
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
    attachment: ImmutableAttachment,
    page_number: int,
    expected_sha256: str,
) -> Path:
    """Resolve an exact regular raster below one of the trusted CASE cache roots."""
    filename = f"page-{page_number:04d}.png"
    found_regular = False
    if attachment.case_id is None:
        if not attachment.stored_path.startswith("inputs/original/"):
            raise ValueError("legacy case visual attachment storage is invalid")
        cache_identity = attachment.attachment_id
    else:
        cache_identity = visual_cache_identity(
            attachment.case_id,
            attachment.attachment_id,
            attachment.sha256,
        )
    for cache_name in (_CASE_PDF_CACHE_DIR, _CASE_IMAGE_CACHE_DIR):
        cache_root = workspace_root / cache_name
        try:
            path = verified_regular_file_below(
                cache_root,
                (cache_identity, filename),
                field="case visual raster",
            )
        except FileNotFoundError:
            continue
        found_regular = True
        if hashlib.sha256(path.read_bytes()).hexdigest() == expected_sha256:
            return path
    if found_regular:
        raise ValueError("case visual raster hash mismatch")
    raise FileNotFoundError(
        workspace_root
        / _CASE_PDF_CACHE_DIR
        / cache_identity
        / filename
    )


def _page_tile_documents(
    workspace_root: Path,
    asset: VisualPageAsset,
) -> list[dict[str, object]]:
    """Project already-verified tile metadata without rereading raster payloads."""
    return [
        {
            "x": tile.x,
            "y": tile.y,
            "width": tile.width,
            "height": tile.height,
            "image_sha256": tile.image_sha256,
        }
        for tile in load_visual_page_tiles(workspace_root, asset)
    ]


def _reference_citation_index(
    view_model: Mapping[str, object],
) -> dict[str, Mapping[str, object]]:
    if "reference_citations" not in view_model:
        return {}

    citations: dict[str, Mapping[str, object]] = {}
    for index, item in enumerate(
        _sequence(view_model.get("reference_citations"), "reference_citations")
    ):
        citation = _mapping(item, f"reference_citations[{index}]")
        citation_id = _string(
            citation.get("citation_id"),
            f"reference_citations[{index}].citation_id",
        )
        prior = citations.get(citation_id)
        if prior is not None and dict(prior) != dict(citation):
            raise ValueError("conflicting reference citation payload")
        citations.setdefault(citation_id, citation)
    return citations


def _direct_citation_ids(
    view_model: Mapping[str, object],
    direct_claim_ids: object,
) -> tuple[str, ...]:
    target_claim_ids = {
        _string(item, "finding.direct_claim_ids")
        for item in _sequence(direct_claim_ids, "finding.direct_claim_ids")
    }
    citation_ids: set[str] = set()
    for index, item in enumerate(_sequence(view_model.get("claims", []), "claims")):
        claim = _mapping(item, f"claims[{index}]")
        claim_id = _string(claim.get("claim_id"), f"claims[{index}].claim_id")
        if claim_id not in target_claim_ids:
            continue
        for citation_index, raw_citation in enumerate(
            _sequence(claim.get("citations", []), f"claims[{index}].citations")
        ):
            citation = _mapping(
                raw_citation,
                f"claims[{index}].citations[{citation_index}]",
            )
            citation_ids.add(
                _string(
                    citation.get("citation_id"),
                    f"claims[{index}].citations[{citation_index}].citation_id",
                )
            )
    return tuple(sorted(citation_ids))


def _related_citation_ids(
    finding: Mapping[str, object],
    related_references: Mapping[str, Mapping[str, object]],
) -> tuple[str, ...]:
    citation_ids: set[str] = set()
    for index, raw_evidence_id in enumerate(
        _sequence(finding.get("related_evidence_ids", []), "finding.related_evidence_ids")
    ):
        evidence_id = _string(
            raw_evidence_id,
            f"finding.related_evidence_ids[{index}]",
        )
        reference = related_references.get(evidence_id)
        if reference is None:
            raise ValueError("selected related reference is missing")
        citation = _mapping(reference.get("citation"), "related_reference.citation")
        citation_ids.add(
            _string(citation.get("citation_id"), "related_reference.citation_id")
        )
    return tuple(sorted(citation_ids))


def _project_reference_anchors(
    view_model: Mapping[str, object],
    findings: Sequence[Mapping[str, object]],
    related_references: Sequence[Mapping[str, object]],
    *,
    page_root: Path,
) -> tuple[list[dict[str, object]], list[dict[str, object]], list[dict[str, object]]]:
    if "reference_citations" not in view_model:
        return (
            [],
            [],
            [
                {
                    **dict(finding),
                    "direct_reference_anchors": [],
                    "related_reference_anchors": [],
                }
                for finding in findings
            ],
        )

    citation_index = _reference_citation_index(view_model)
    related_by_evidence: dict[str, Mapping[str, object]] = {}
    for index, raw_reference in enumerate(related_references):
        reference = _mapping(raw_reference, f"related_references[{index}]")
        evidence_id = _string(
            reference.get("evidence_id"),
            f"related_references[{index}].evidence_id",
        )
        citation = _mapping(
            reference.get("citation"),
            f"related_references[{index}].citation",
        )
        _string(
            citation.get("citation_id"),
            f"related_references[{index}].citation.citation_id",
        )
        prior = related_by_evidence.get(evidence_id)
        if prior is not None and dict(prior) != dict(reference):
            raise ValueError("conflicting selected related reference")
        related_by_evidence.setdefault(evidence_id, reference)

    direct_ids_by_finding: list[tuple[str, ...]] = []
    related_ids_by_finding: list[tuple[str, ...]] = []
    selected_ids: set[str] = set()
    for finding in findings:
        direct_ids = _direct_citation_ids(
            view_model,
            finding.get("direct_claim_ids", []),
        )
        related_ids = _related_citation_ids(finding, related_by_evidence)
        direct_ids_by_finding.append(direct_ids)
        related_ids_by_finding.append(related_ids)
        selected_ids.update(direct_ids)
        selected_ids.update(related_ids)

    missing_ids = sorted(
        citation_id
        for citation_id in selected_ids
        if citation_id not in citation_index
    )
    if missing_ids:
        raise ValueError("reference citation projection missing selected citation")

    selected_citations = [
        citation_index[citation_id] for citation_id in sorted(selected_ids)
    ]
    documents, pages, anchors = build_reference_projection(
        selected_citations,
        page_root=page_root,
    )

    projected_findings: list[dict[str, object]] = []
    for finding, direct_ids, related_ids in zip(
        findings,
        direct_ids_by_finding,
        related_ids_by_finding,
        strict=True,
    ):
        projected_findings.append(
            {
                **dict(finding),
                "direct_reference_anchors": [
                    {
                        **anchors[citation_id],
                        "reference_role": "direct",
                    }
                    for citation_id in direct_ids
                ],
                "related_reference_anchors": [
                    {
                        **anchors[citation_id],
                        "reference_role": "related",
                    }
                    for citation_id in related_ids
                ],
            }
        )
    return documents, pages, projected_findings


def build_case_visual_projection(
    view_model: Mapping[str, object],
    *,
    workspace_root: Path,
) -> dict[str, object] | None:
    """Project immutable visual evidence into a self-contained reviewer model."""
    run_id = validate_identifier(view_model.get("run_id"), "view_model.run_id")
    run_directory = workspace_root / "runs" / run_id
    try:
        bundle_path = verified_regular_file_below(
            run_directory,
            ("track-a-bundle.json",),
            field="case visual Track A bundle",
        )
    except FileNotFoundError:
        return None
    bundle = _json(bundle_path)
    inputs = _mapping(bundle.get("inputs"), "track_a_bundle.inputs")
    raw_context = inputs.get("case_visual_context")
    if raw_context is None:
        return None
    context = _mapping(raw_context, "inputs.case_visual_context")
    if context.get("visual_status") != "VISUAL_ANALYSIS_VALIDATED":
        raise ValueError("case visual context is not validated")
    try:
        track_a_path = verified_regular_file_below(
            run_directory,
            ("track-a-output.json",),
            field="case visual Track A output",
        )
    except FileNotFoundError as error:
        raise ValueError(
            "validated case visual review requires track-a-output.json"
        ) from error
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
        if key in page_records:
            raise ValueError("case visual page identity is ambiguous")
        image_path = _resolve_visual_raster_path(
            workspace_root,
            page_attachment,
            page_number,
            image_sha256,
        )
        asset = VisualPageAsset(
            case_id=page_attachment.case_id,
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
            "case_id": page_attachment.case_id,
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
            image_bytes = image_path.read_bytes()
            page_record["data_uri"] = "data:image/png;base64," + base64.b64encode(
                image_bytes
            ).decode("ascii")
        page_records[key] = page_record

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
        if candidate.attachment_id is None:
            raise ValueError("case visual candidate attachment is not bound")
        candidate_attachment = attachment_by_id.get(candidate.attachment_id)
        if (
            candidate_attachment is None
            or candidate_attachment.sha256 != candidate.source_sha256
            or candidate_attachment.case_id != candidate.case_id
        ):
            raise ValueError("case visual candidate attachment is not bound")
        page_key = (candidate.attachment_id, candidate.page)
        candidate_page = page_records.get(page_key)
        if candidate_page is None:
            raise ValueError("case visual candidate has no verified raster page")
        canonical = drawing_candidate_document(candidate)
        _verify_geometry_bounds(
            canonical,
            cast(float, candidate_page["width"]),
            cast(float, candidate_page["height"]),
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
        cast(list[object], candidate_page["candidates"]).append(projected)

    if set(lineage) != seen_candidates:
        raise ValueError("case visual lineage does not match drawing candidates")

    pages = [page_records[key] for key in sorted(page_records)]
    findings = build_semantic_visual_findings(pages)
    findings, related_references = bind_related_retrieval_references(
        bundle,
        inputs,
        findings,
    )
    reference_documents, reference_pages, findings = _project_reference_anchors(
        view_model,
        findings,
        related_references,
        page_root=workspace_root / "page-images",
    )
    return {
        "status": "VISUAL_ANALYSIS_VALIDATED",
        "attachment_count": len(attachments),
        "candidate_count": len(seen_candidates),
        "finding_count": len(findings),
        "pages": pages,
        "findings": findings,
        "related_references": related_references,
        "reference_documents": reference_documents,
        "reference_pages": reference_pages,
    }


__all__ = ["build_case_visual_projection"]
