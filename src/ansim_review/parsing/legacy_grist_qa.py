"""Strict contract for manual legacy Grist Desktop QA evidence."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Final, Literal, cast

from ansim_review.contracts.validation import (
    expect_int,
    expect_literal,
    expect_mapping,
    expect_sequence,
    expect_sha256,
    expect_string,
    expect_string_tuple,
    reject_unknown,
    require_fields,
)

GRIST_QA_FORMAT: Final = "evidence-review/grist-desktop-qa"
GRIST_QA_STATUS_FORMAT: Final = "evidence-review/grist-desktop-qa-status"
GRIST_QA_SCOPE: Final = "LEGACY_UI_QA"
GRIST_QA_IDENTITY_CLAIM: Final = "LEGACY_NON_CANONICAL"

REQUIRED_VIEW_IDS: Final[tuple[str, ...]] = (
    "ATTACHMENTS_FILE_LINK",
    "VISUALS_THUMBNAIL",
    "REFERENCE_LINK_PREVIEW",
    "PAGE_RENDER",
    "IMAGE_CONTEXT_CROP",
    "TABLE_CROP",
    "COMPOSITE_DIAGRAM",
    "MISSING_BROKEN_LINK_SCAN",
    "LEGACY_CANONICAL_SEPARATION",
)
REQUIRED_SAMPLE_KINDS: Final[tuple[str, ...]] = (
    "PAGE_RENDER",
    "IMAGE_CONTEXT_CROP",
    "TABLE_CROP",
    "COMPOSITE_DIAGRAM",
)
_REQUIRED_VIEW_SET = frozenset(REQUIRED_VIEW_IDS)
_REQUIRED_SAMPLE_SET = frozenset(REQUIRED_SAMPLE_KINDS)

ViewStatus = Literal["PASS", "FAIL", "NOT_RUN"]
SampleResult = Literal["PASS", "FAIL"]
FindingStatus = Literal["OPEN", "RESOLVED"]
GristQaStatus = Literal["PASS", "FAIL", "INCOMPLETE"]


@dataclass(frozen=True, slots=True)
class ReviewIdentity:
    reviewer_id: str
    reviewed_at: datetime


@dataclass(frozen=True, slots=True)
class GristEnvironment:
    grist_desktop_version: str
    os: str


@dataclass(frozen=True, slots=True)
class FileBinding:
    path: str
    sha256: str


@dataclass(frozen=True, slots=True)
class GristQaSources:
    grist_file: FileBinding
    visual_manifest: FileBinding
    inspection_report: FileBinding


@dataclass(frozen=True, slots=True)
class EvidenceFile:
    evidence_id: str
    path: str
    sha256: str


@dataclass(frozen=True, slots=True)
class GristQaView:
    view_id: str
    status: ViewStatus
    evidence_ids: tuple[str, ...]
    notes: str


@dataclass(frozen=True, slots=True)
class GristQaSample:
    sample_id: str
    content_kind: str
    row_id: str
    asset_path: str
    asset_sha256: str
    result: SampleResult
    evidence_ids: tuple[str, ...]
    notes: str


@dataclass(frozen=True, slots=True)
class GristQaFinding:
    finding_id: str
    view_id: str
    status: FindingStatus
    row_id: str | None
    file_path: str | None
    description: str
    evidence_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class GristQaArtifact:
    format: str
    version: Literal[1]
    scope: str
    identity_claim: str
    review: ReviewIdentity
    environment: GristEnvironment
    sources: GristQaSources
    evidence_files: tuple[EvidenceFile, ...]
    views: tuple[GristQaView, ...]
    samples: tuple[GristQaSample, ...]
    findings: tuple[GristQaFinding, ...]


def _nonblank(value: object, field: str) -> str:
    result = expect_string(value, field)
    if not result.strip():
        raise ValueError(f"{field} must not be blank")
    return result


def _optional_nonblank(value: object, field: str) -> str | None:
    if value is None:
        return None
    return _nonblank(value, field)


def _timestamp(value: object) -> datetime:
    text = expect_string(value, "review.reviewed_at")
    try:
        result = datetime.fromisoformat(text)
    except ValueError as error:
        raise ValueError("review.reviewed_at must be ISO-8601") from error
    if result.utcoffset() is None:
        raise ValueError("review.reviewed_at must include timezone")
    return result


def _decode_review(value: object) -> ReviewIdentity:
    payload = expect_mapping(value, "review")
    fields = {"reviewer_id", "reviewed_at"}
    require_fields(payload, fields, "review")
    reject_unknown(payload, fields, "review")
    return ReviewIdentity(
        reviewer_id=_nonblank(payload.get("reviewer_id"), "review.reviewer_id"),
        reviewed_at=_timestamp(payload.get("reviewed_at")),
    )


def _decode_environment(value: object) -> GristEnvironment:
    payload = expect_mapping(value, "environment")
    fields = {"grist_desktop_version", "os"}
    require_fields(payload, fields, "environment")
    reject_unknown(payload, fields, "environment")
    return GristEnvironment(
        grist_desktop_version=_nonblank(
            payload.get("grist_desktop_version"),
            "environment.grist_desktop_version",
        ),
        os=_nonblank(payload.get("os"), "environment.os"),
    )


def _decode_file_binding(value: object, field: str) -> FileBinding:
    payload = expect_mapping(value, field)
    fields = {"path", "sha256"}
    require_fields(payload, fields, field)
    reject_unknown(payload, fields, field)
    return FileBinding(
        path=_nonblank(payload.get("path"), f"{field}.path"),
        sha256=expect_sha256(payload.get("sha256"), f"{field}.sha256"),
    )


def _decode_sources(value: object) -> GristQaSources:
    payload = expect_mapping(value, "sources")
    fields = {"grist_file", "visual_manifest", "inspection_report"}
    require_fields(payload, fields, "sources")
    reject_unknown(payload, fields, "sources")
    return GristQaSources(
        grist_file=_decode_file_binding(
            payload.get("grist_file"),
            "sources.grist_file",
        ),
        visual_manifest=_decode_file_binding(
            payload.get("visual_manifest"),
            "sources.visual_manifest",
        ),
        inspection_report=_decode_file_binding(
            payload.get("inspection_report"),
            "sources.inspection_report",
        ),
    )


def _decode_evidence(value: object, index: int) -> EvidenceFile:
    field = f"evidence_files[{index}]"
    payload = expect_mapping(value, field)
    fields = {"evidence_id", "path", "sha256"}
    require_fields(payload, fields, field)
    reject_unknown(payload, fields, field)
    return EvidenceFile(
        evidence_id=_nonblank(payload.get("evidence_id"), f"{field}.evidence_id"),
        path=_nonblank(payload.get("path"), f"{field}.path"),
        sha256=expect_sha256(payload.get("sha256"), f"{field}.sha256"),
    )


def _decode_view(value: object, index: int) -> GristQaView:
    field = f"views[{index}]"
    payload = expect_mapping(value, field)
    fields = {"view_id", "status", "evidence_ids", "notes"}
    require_fields(payload, fields, field)
    reject_unknown(payload, fields, field)
    view_id = _nonblank(payload.get("view_id"), f"{field}.view_id")
    if view_id not in _REQUIRED_VIEW_SET:
        raise ValueError(f"UNKNOWN_GRIST_QA_VIEW:{view_id}")
    status = cast(
        ViewStatus,
        expect_literal(
            payload.get("status"),
            f"{field}.status",
            ("PASS", "FAIL", "NOT_RUN"),
        ),
    )
    return GristQaView(
        view_id=view_id,
        status=status,
        evidence_ids=expect_string_tuple(
            payload.get("evidence_ids"),
            f"{field}.evidence_ids",
        ),
        notes=_nonblank(payload.get("notes"), f"{field}.notes"),
    )


def _decode_sample(value: object, index: int) -> GristQaSample:
    field = f"samples[{index}]"
    payload = expect_mapping(value, field)
    fields = {
        "sample_id",
        "content_kind",
        "row_id",
        "asset_path",
        "asset_sha256",
        "result",
        "evidence_ids",
        "notes",
    }
    require_fields(payload, fields, field)
    reject_unknown(payload, fields, field)
    content_kind = _nonblank(payload.get("content_kind"), f"{field}.content_kind")
    if content_kind not in _REQUIRED_SAMPLE_SET:
        raise ValueError(f"UNKNOWN_GRIST_QA_SAMPLE_KIND:{content_kind}")
    result = cast(
        SampleResult,
        expect_literal(
            payload.get("result"),
            f"{field}.result",
            ("PASS", "FAIL"),
        ),
    )
    return GristQaSample(
        sample_id=_nonblank(payload.get("sample_id"), f"{field}.sample_id"),
        content_kind=content_kind,
        row_id=_nonblank(payload.get("row_id"), f"{field}.row_id"),
        asset_path=_nonblank(payload.get("asset_path"), f"{field}.asset_path"),
        asset_sha256=expect_sha256(
            payload.get("asset_sha256"),
            f"{field}.asset_sha256",
        ),
        result=result,
        evidence_ids=expect_string_tuple(
            payload.get("evidence_ids"),
            f"{field}.evidence_ids",
        ),
        notes=_nonblank(payload.get("notes"), f"{field}.notes"),
    )


def _decode_finding(value: object, index: int) -> GristQaFinding:
    field = f"findings[{index}]"
    payload = expect_mapping(value, field)
    fields = {
        "finding_id",
        "view_id",
        "status",
        "row_id",
        "file_path",
        "description",
        "evidence_ids",
    }
    require_fields(payload, fields, field)
    reject_unknown(payload, fields, field)
    finding_id = _nonblank(payload.get("finding_id"), f"{field}.finding_id")
    view_id = _nonblank(payload.get("view_id"), f"{field}.view_id")
    if view_id not in _REQUIRED_VIEW_SET:
        raise ValueError(f"UNKNOWN_GRIST_QA_VIEW:{view_id}")
    status = cast(
        FindingStatus,
        expect_literal(
            payload.get("status"),
            f"{field}.status",
            ("OPEN", "RESOLVED"),
        ),
    )
    row_id = _optional_nonblank(payload.get("row_id"), f"{field}.row_id")
    file_path = _optional_nonblank(payload.get("file_path"), f"{field}.file_path")
    if row_id is None and file_path is None:
        raise ValueError(f"FINDING_LOCATOR_REQUIRED:{finding_id}")
    return GristQaFinding(
        finding_id=finding_id,
        view_id=view_id,
        status=status,
        row_id=row_id,
        file_path=file_path,
        description=_nonblank(payload.get("description"), f"{field}.description"),
        evidence_ids=expect_string_tuple(
            payload.get("evidence_ids"),
            f"{field}.evidence_ids",
        ),
    )


def _unique_by_id(
    values: tuple[EvidenceFile, ...]
    | tuple[GristQaSample, ...]
    | tuple[GristQaFinding, ...],
    *,
    attribute: Literal["evidence_id", "sample_id", "finding_id"],
    error_code: str,
) -> None:
    seen: set[str] = set()
    for value in values:
        stable_id = cast(str, getattr(value, attribute))
        if stable_id in seen:
            raise ValueError(f"{error_code}:{stable_id}")
        seen.add(stable_id)


def _validate_evidence_references(
    evidence_files: tuple[EvidenceFile, ...],
    views: tuple[GristQaView, ...],
    samples: tuple[GristQaSample, ...],
    findings: tuple[GristQaFinding, ...],
) -> None:
    known = {item.evidence_id for item in evidence_files}
    references = (
        *(item.evidence_ids for item in views),
        *(item.evidence_ids for item in samples),
        *(item.evidence_ids for item in findings),
    )
    for group in references:
        for evidence_id in group:
            if evidence_id not in known:
                raise ValueError(f"EVIDENCE_ID_NOT_FOUND:{evidence_id}")


def decode_grist_qa(value: object) -> GristQaArtifact:
    """Decode the strict version 1 manual Grist Desktop QA artifact."""
    payload = expect_mapping(value, "grist_qa")
    fields = {
        "format",
        "version",
        "scope",
        "identity_claim",
        "review",
        "environment",
        "sources",
        "evidence_files",
        "views",
        "samples",
        "findings",
    }
    require_fields(payload, fields, "grist_qa")
    reject_unknown(payload, fields, "grist_qa")
    expect_literal(payload.get("format"), "format", (GRIST_QA_FORMAT,))
    version = expect_int(payload.get("version"), "version")
    if version != 1:
        raise ValueError(f"unsupported version: {version}")
    expect_literal(payload.get("scope"), "scope", (GRIST_QA_SCOPE,))
    expect_literal(
        payload.get("identity_claim"),
        "identity_claim",
        (GRIST_QA_IDENTITY_CLAIM,),
    )

    evidence_files = tuple(
        _decode_evidence(item, index)
        for index, item in enumerate(
            expect_sequence(payload.get("evidence_files"), "evidence_files")
        )
    )
    _unique_by_id(
        evidence_files,
        attribute="evidence_id",
        error_code="DUPLICATE_EVIDENCE_ID",
    )

    by_view: dict[str, GristQaView] = {}
    for index, item in enumerate(expect_sequence(payload.get("views"), "views")):
        view = _decode_view(item, index)
        if view.view_id in by_view:
            raise ValueError(f"DUPLICATE_GRIST_QA_VIEW:{view.view_id}")
        by_view[view.view_id] = view
    missing_views = [view_id for view_id in REQUIRED_VIEW_IDS if view_id not in by_view]
    if missing_views:
        raise ValueError(f"MISSING_GRIST_QA_VIEW:{missing_views[0]}")
    views = tuple(by_view[view_id] for view_id in REQUIRED_VIEW_IDS)

    samples = tuple(
        _decode_sample(item, index)
        for index, item in enumerate(expect_sequence(payload.get("samples"), "samples"))
    )
    _unique_by_id(
        samples,
        attribute="sample_id",
        error_code="DUPLICATE_SAMPLE_ID",
    )

    findings = tuple(
        _decode_finding(item, index)
        for index, item in enumerate(
            expect_sequence(payload.get("findings"), "findings")
        )
    )
    _unique_by_id(
        findings,
        attribute="finding_id",
        error_code="DUPLICATE_FINDING_ID",
    )

    _validate_evidence_references(evidence_files, views, samples, findings)
    open_finding_views = {
        finding.view_id for finding in findings if finding.status == "OPEN"
    }
    for view in views:
        if view.status == "FAIL" and view.view_id not in open_finding_views:
            raise ValueError(f"FAIL_VIEW_REQUIRES_OPEN_FINDING:{view.view_id}")

    return GristQaArtifact(
        format=GRIST_QA_FORMAT,
        version=1,
        scope=GRIST_QA_SCOPE,
        identity_claim=GRIST_QA_IDENTITY_CLAIM,
        review=_decode_review(payload.get("review")),
        environment=_decode_environment(payload.get("environment")),
        sources=_decode_sources(payload.get("sources")),
        evidence_files=tuple(sorted(evidence_files, key=lambda item: item.evidence_id)),
        views=views,
        samples=tuple(sorted(samples, key=lambda item: item.sample_id)),
        findings=tuple(sorted(findings, key=lambda item: item.finding_id)),
    )


def _binding_document(binding: FileBinding) -> dict[str, object]:
    return {"path": binding.path, "sha256": binding.sha256}


def grist_qa_document(artifact: GristQaArtifact) -> dict[str, object]:
    """Project a decoded artifact into deterministic canonical JSON data."""
    return {
        "format": GRIST_QA_FORMAT,
        "version": 1,
        "scope": GRIST_QA_SCOPE,
        "identity_claim": GRIST_QA_IDENTITY_CLAIM,
        "review": {
            "reviewer_id": artifact.review.reviewer_id,
            "reviewed_at": artifact.review.reviewed_at.isoformat(),
        },
        "environment": {
            "grist_desktop_version": artifact.environment.grist_desktop_version,
            "os": artifact.environment.os,
        },
        "sources": {
            "grist_file": _binding_document(artifact.sources.grist_file),
            "visual_manifest": _binding_document(artifact.sources.visual_manifest),
            "inspection_report": _binding_document(artifact.sources.inspection_report),
        },
        "evidence_files": [
            {
                "evidence_id": item.evidence_id,
                "path": item.path,
                "sha256": item.sha256,
            }
            for item in artifact.evidence_files
        ],
        "views": [
            {
                "view_id": item.view_id,
                "status": item.status,
                "evidence_ids": list(item.evidence_ids),
                "notes": item.notes,
            }
            for item in artifact.views
        ],
        "samples": [
            {
                "sample_id": item.sample_id,
                "content_kind": item.content_kind,
                "row_id": item.row_id,
                "asset_path": item.asset_path,
                "asset_sha256": item.asset_sha256,
                "result": item.result,
                "evidence_ids": list(item.evidence_ids),
                "notes": item.notes,
            }
            for item in artifact.samples
        ],
        "findings": [
            {
                "finding_id": item.finding_id,
                "view_id": item.view_id,
                "status": item.status,
                "row_id": item.row_id,
                "file_path": item.file_path,
                "description": item.description,
                "evidence_ids": list(item.evidence_ids),
            }
            for item in artifact.findings
        ],
    }


def derive_grist_qa_status(artifact: GristQaArtifact) -> GristQaStatus:
    """Derive fail-closed status from manual observations and findings."""
    if any(view.status == "FAIL" for view in artifact.views):
        return "FAIL"
    if any(sample.result == "FAIL" for sample in artifact.samples):
        return "FAIL"
    if any(finding.status == "OPEN" for finding in artifact.findings):
        return "FAIL"
    if any(view.status == "NOT_RUN" for view in artifact.views):
        return "INCOMPLETE"
    passed_kinds = {
        sample.content_kind
        for sample in artifact.samples
        if sample.result == "PASS"
    }
    if any(kind not in passed_kinds for kind in REQUIRED_SAMPLE_KINDS):
        return "INCOMPLETE"
    return "PASS"


def grist_qa_status_document(
    artifact: GristQaArtifact,
    artifact_sha256: str,
) -> dict[str, object]:
    """Return the deterministic validation status for one exact artifact."""
    digest = expect_sha256(artifact_sha256, "artifact_sha256")
    status = derive_grist_qa_status(artifact)
    view_counts = {
        view_status: sum(
            1 for view in artifact.views if view.status == view_status
        )
        for view_status in ("PASS", "FAIL", "NOT_RUN")
    }
    return {
        "format": GRIST_QA_STATUS_FORMAT,
        "version": 1,
        "status": status,
        "accepted": status == "PASS",
        "artifact_sha256": digest,
        "reviewer_id": artifact.review.reviewer_id,
        "reviewed_at": artifact.review.reviewed_at.isoformat(),
        "view_counts": view_counts,
        "open_finding_count": sum(
            1 for finding in artifact.findings if finding.status == "OPEN"
        ),
    }
