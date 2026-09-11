"""Case-specific visual attachment intake and formal-review binding."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import cast

from evidence_review.canonical_json import sha256_json
from evidence_review.contracts.attachments import (
    AttachmentRole,
    ImmutableAttachment,
    decode_immutable_attachment,
    immutable_attachment_document,
)
from evidence_review.contracts.drawing import DrawingCandidate, drawing_candidate_document
from evidence_review.drawing_review.visual_pages import VisualPageAsset
from evidence_review.parsing.drawing_source import (
    DrawingIntakePolicy,
    ingest_drawing_source,
    sniff_drawing_mime,
    validate_source_path,
    verify_immutable_attachment,
)
from evidence_review.parsing.source_manifest import sha256_file

_VISUAL_ROLES: tuple[AttachmentRole, ...] = ("CASE_DRAWING", "SUPPORTING_IMAGE")
_EXTENSION_ALIASES: dict[str, tuple[str, ...]] = {
    "application/pdf": (".pdf",),
    "image/png": (".png",),
    "image/tiff": (".tif", ".tiff"),
    "image/jpeg": (".jpg", ".jpeg"),
}
_CANONICAL_EXTENSION: dict[str, str] = {
    "application/pdf": ".pdf",
    "image/png": ".png",
    "image/tiff": ".tif",
    "image/jpeg": ".jpg",
}


@dataclass(frozen=True, slots=True)
class VisualCase:
    """One exact drawing case; its identity remains separate from a Matter."""

    case_id: str
    attachments: tuple[ImmutableAttachment, ...]


def _mapping(value: object, field: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping) or not all(
        isinstance(key, str) for key in value
    ):
        raise ValueError(f"{field} must be an object")
    return cast(Mapping[str, object], value)


def _validate_visual_role(role: AttachmentRole) -> None:
    if role == "REFERENCE_DOCUMENT":
        raise ValueError("REFERENCE_DOCUMENT must use the reference ingestion pipeline")
    if role not in _VISUAL_ROLES:
        raise ValueError(f"unsupported case visual attachment role: {role}")


def _source_descriptor(path: Path, role: AttachmentRole) -> dict[str, object]:
    _validate_visual_role(role)
    validate_source_path(path)
    with path.open("rb") as stream:
        mime, canonical_extension = sniff_drawing_mime(stream.read(16))
    if path.suffix.lower() not in _EXTENSION_ALIASES[mime]:
        raise ValueError("source extension does not match MIME")
    return {
        "original_name": path.name,
        "sha256": sha256_file(path),
        "byte_size": path.stat().st_size,
        "mime": mime,
        "canonical_extension": canonical_extension,
        "role": role,
    }


def _attachment_id(descriptor: Mapping[str, object]) -> str:
    identity = {
        "original_name": descriptor["original_name"],
        "sha256": descriptor["sha256"],
        "byte_size": descriptor["byte_size"],
        "mime": descriptor["mime"],
        "role": descriptor["role"],
    }
    return f"ATT-{sha256_json(identity)[:20].upper()}"


def _case_id(descriptors: Sequence[Mapping[str, object]]) -> str:
    identities = [
        {
            "attachment_id": _attachment_id(item),
            "sha256": item["sha256"],
            "role": item["role"],
        }
        for item in descriptors
    ]
    identities.sort(key=lambda item: cast(str, item["attachment_id"]))
    return f"CASE-VIS-{sha256_json(identities)[:20].upper()}"


def _reconstructed_attachment(
    descriptor: Mapping[str, object], attachment_id: str, case_id: str
) -> ImmutableAttachment:
    mime = cast(str, descriptor["mime"])
    return ImmutableAttachment(
        attachment_id=attachment_id,
        original_name=cast(str, descriptor["original_name"]),
        stored_path=(
            f"cases/{case_id}/sources/drawings/"
            f"{attachment_id}{_CANONICAL_EXTENSION[mime]}"
        ),
        sha256=cast(str, descriptor["sha256"]),
        byte_size=cast(int, descriptor["byte_size"]),
        mime=mime,
        role=cast(AttachmentRole, descriptor["role"]),
        case_id=case_id,
    )


def visual_case_from_attachments(
    attachments: Sequence[ImmutableAttachment],
) -> VisualCase:
    """Build one exact visual case without resolving attachments by filename."""
    validated = tuple(
        decode_immutable_attachment(immutable_attachment_document(item))
        for item in attachments
    )
    if not validated:
        raise ValueError("visual case requires at least one attachment")
    case_ids = {item.case_id for item in validated}
    if len(case_ids) != 1 or None in case_ids:
        raise ValueError("visual case attachments must share one case_id")
    if len({item.attachment_id for item in validated}) != len(validated):
        raise ValueError("visual case attachment_id values must be unique")
    ordered = tuple(sorted(validated, key=lambda item: item.attachment_id))
    case_id = ordered[0].case_id
    if case_id is None:
        raise ValueError("visual case attachments must share one case_id")
    return VisualCase(case_id=case_id, attachments=ordered)


def prepare_case_visual_sources(
    workspace: Path,
    *,
    case_drawings: Sequence[Path] = (),
    supporting_images: Sequence[Path] = (),
    policy: DrawingIntakePolicy | None = None,
) -> tuple[ImmutableAttachment, ...]:
    """Copy user-selected case visuals into deterministic immutable case storage."""
    requested: list[tuple[Path, AttachmentRole]] = [
        (path, "CASE_DRAWING") for path in case_drawings
    ]
    requested.extend((path, "SUPPORTING_IMAGE") for path in supporting_images)
    if not requested:
        return ()

    descriptors = [
        (path, _source_descriptor(path, role)) for path, role in requested
    ]
    case_id = _case_id([descriptor for _, descriptor in descriptors])
    case_dir = workspace / "cases" / case_id
    case_dir.mkdir(parents=True, exist_ok=True)
    intake_policy = policy or DrawingIntakePolicy()

    attachments: list[ImmutableAttachment] = []
    for source_path, descriptor in descriptors:
        attachment_id = _attachment_id(descriptor)
        expected = _reconstructed_attachment(descriptor, attachment_id, case_id)
        canonical_extension = _CANONICAL_EXTENSION[expected.mime]
        physical = (
            case_dir
            / "sources"
            / "drawings"
            / f"{attachment_id}{canonical_extension}"
        )
        if physical.exists():
            errors = verify_immutable_attachment(case_dir, expected)
            if errors:
                joined = ",".join(errors)
                raise ValueError(
                    "existing case visual source failed integrity validation: "
                    f"{joined}"
                )
            attachment = expected
        else:
            attachment = ingest_drawing_source(
                source_path,
                case_dir,
                attachment_id,
                expected.role,
                intake_policy,
            )
            if attachment != expected:
                raise ValueError(
                    "drawing intake metadata does not match deterministic identity"
                )
        attachments.append(attachment)

    attachments.sort(key=lambda item: item.attachment_id)
    if len({item.attachment_id for item in attachments}) != len(attachments):
        raise ValueError("case visual attachments must be unique")
    return tuple(attachments)


def _visual_page_document(page: VisualPageAsset) -> dict[str, object]:
    return {
        "attachment_id": page.attachment_id,
        "source_sha256": page.source_sha256,
        "page": page.page,
        "width": page.width,
        "height": page.height,
        "coordinate_system": page.coordinate_system,
        "image_sha256": page.image_sha256,
    }


def bind_case_visual_context_to_review_request(
    request: dict[str, object],
    attachments: Sequence[ImmutableAttachment],
    drawing_candidates: Sequence[DrawingCandidate] = (),
    *,
    candidate_issue_ids: Mapping[str, Sequence[str]] | None = None,
    visual_page_assets: Sequence[VisualPageAsset] = (),
    visual_analysis_completed: bool = False,
) -> dict[str, object]:
    """Bind case visuals to immutable request inputs without changing legacy requests."""
    attachment_items = tuple(attachments)
    candidate_items = tuple(drawing_candidates)
    page_items = tuple(visual_page_assets)
    if (
        not attachment_items
        and not candidate_items
        and not page_items
        and not visual_analysis_completed
    ):
        return request
    if not attachment_items:
        raise ValueError("case visual context requires at least one attachment")
    if (candidate_items or page_items) and not visual_analysis_completed:
        raise ValueError("visual evidence requires completed visual analysis")

    attachment_ids: set[str] = set()
    source_hash_by_attachment: dict[str, str] = {}
    case_id_by_attachment: dict[str, str | None] = {}
    source_hashes: set[str] = set()
    for attachment in attachment_items:
        _validate_visual_role(attachment.role)
        if attachment.attachment_id in attachment_ids:
            raise ValueError("case visual attachment_id values must be unique")
        attachment_ids.add(attachment.attachment_id)
        source_hash_by_attachment[attachment.attachment_id] = attachment.sha256
        case_id_by_attachment[attachment.attachment_id] = attachment.case_id
        source_hashes.add(attachment.sha256)

    page_keys: set[tuple[str, int]] = set()
    for page in page_items:
        if page.attachment_id not in attachment_ids:
            raise ValueError(
                "visual page references an attachment outside this review request"
            )
        if page.source_sha256 != source_hash_by_attachment[page.attachment_id]:
            raise ValueError("visual page source hash does not match its attachment")
        if page.case_id != case_id_by_attachment[page.attachment_id]:
            raise ValueError("visual page case_id does not match its attachment")
        key = (page.attachment_id, page.page)
        if key in page_keys:
            raise ValueError("visual page identities must be unique")
        page_keys.add(key)

    candidate_ids: set[str] = set()
    for candidate in candidate_items:
        if candidate.candidate_id in candidate_ids:
            raise ValueError("drawing candidate IDs must be unique")
        candidate_ids.add(candidate.candidate_id)
        if candidate.case_id is None:
            raise ValueError("drawing candidate case is not bound to this review request")
        if candidate.source_sha256 not in source_hashes:
            raise ValueError(
                "drawing candidate source is not bound to this review request"
            )
        matching_attachment_ids = {
            attachment_id
            for attachment_id, source_hash in source_hash_by_attachment.items()
            if (
                source_hash == candidate.source_sha256
                and case_id_by_attachment[attachment_id] == candidate.case_id
            )
        }
        if not matching_attachment_ids:
            raise ValueError("drawing candidate case is not bound to this review request")
        if page_items and not any(
            (attachment_id, candidate.page) in page_keys
            for attachment_id in matching_attachment_ids
        ):
            raise ValueError(
                "drawing candidate page is not bound to a visual page asset"
            )

    if visual_analysis_completed and not page_items:
        raise ValueError("completed visual analysis requires visual page identities")

    lineage_source = {} if candidate_issue_ids is None else dict(candidate_issue_ids)
    if set(lineage_source) != candidate_ids:
        if candidate_ids or lineage_source:
            raise ValueError(
                "candidate issue lineage must match drawing candidate IDs exactly"
            )
    lineage: list[dict[str, object]] = []
    for candidate_id in sorted(lineage_source):
        issue_ids = tuple(sorted(set(lineage_source[candidate_id])))
        if not issue_ids:
            raise ValueError("candidate issue lineage must contain at least one issue")
        lineage.append({"candidate_id": candidate_id, "issue_ids": list(issue_ids)})

    inputs = dict(_mapping(request.get("inputs"), "inputs"))
    if "case_visual_context" in inputs:
        raise ValueError("case_visual_context is already bound")

    attachment_documents = [
        immutable_attachment_document(item)
        for item in sorted(attachment_items, key=lambda item: item.attachment_id)
    ]
    candidate_documents = [
        drawing_candidate_document(item)
        for item in sorted(candidate_items, key=lambda item: item.candidate_id)
    ]
    visual_status = (
        "VISUAL_ANALYSIS_VALIDATED"
        if visual_analysis_completed
        else "VISUAL_ANALYSIS_REQUIRED"
    )
    reason_codes = (
        [] if visual_analysis_completed else ["VISUAL_ANALYSIS_REQUIRED"]
    )
    visual_context: dict[str, object] = {
        "attachments": attachment_documents,
        "drawing_candidates": candidate_documents,
        "visual_status": visual_status,
        "reason_codes": reason_codes,
    }
    if visual_analysis_completed:
        visual_context["visual_pages"] = [
            _visual_page_document(item)
            for item in sorted(
                page_items,
                key=lambda item: (item.attachment_id, item.page),
            )
        ]
        visual_context["candidate_lineage"] = lineage
    inputs["case_visual_context"] = visual_context
    bound = dict(request)
    bound["inputs"] = inputs
    return bound


__all__ = [
    "VisualCase",
    "bind_case_visual_context_to_review_request",
    "prepare_case_visual_sources",
    "visual_case_from_attachments",
]
