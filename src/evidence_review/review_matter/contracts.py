"""Strict canonical contracts for mutable ReviewMatter work state."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final, Literal

from evidence_review.contracts.common import BBox
from evidence_review.contracts.formats import (
    MATTER_SOURCE_BINDING_FORMAT as _MATTER_SOURCE_BINDING_FORMAT,
)
from evidence_review.contracts.formats import REVIEW_MATTER_FORMAT
from evidence_review.contracts.identifiers import validate_identifier
from evidence_review.contracts.validation import (
    expect_int,
    expect_literal,
    expect_mapping,
    expect_sequence,
    expect_sha256,
    expect_string,
    reject_unknown,
    require_fields,
)

MatterFormat = Literal["evidence-review/review-matter"]
MatterSourceBindingFormat = Literal["evidence-review/matter-source-binding"]
MatterIssueState = Literal[
    "DRAFT",
    "OPEN",
    "IN_PROGRESS",
    "NEEDS_EVIDENCE",
    "READY_TO_FORMALIZE",
    "STALE",
    "BLOCKED",
]

MATTER_FORMAT: Final[MatterFormat] = REVIEW_MATTER_FORMAT
MATTER_SOURCE_BINDING_FORMAT: Final[MatterSourceBindingFormat] = (
    _MATTER_SOURCE_BINDING_FORMAT
)
MATTER_VERSION: Final[Literal[1]] = 1
MATTER_SOURCE_BINDING_VERSION: Final[Literal[1]] = 1
FORMALIZATION_SNAPSHOT_FORMAT: Final[Literal["evidence-review/formalization-snapshot"]] = (
    "evidence-review/formalization-snapshot"
)
FORMALIZATION_SNAPSHOT_VERSION: Final[Literal[1]] = 1

_MATTER_STATES: tuple[MatterIssueState, ...] = (
    "DRAFT",
    "OPEN",
    "IN_PROGRESS",
    "NEEDS_EVIDENCE",
    "READY_TO_FORMALIZE",
    "STALE",
    "BLOCKED",
)
_FORMAL_ISSUE_STATUSES = frozenset(
    {
        "RESOLVED",
        "CONDITIONAL",
        "CONFLICT",
        "SOURCE_MISSING",
        "UNRESOLVED",
    }
)


def _identifier(value: object, field: str) -> str:
    identifier = validate_identifier(value, field)
    if field == "matter_id" and identifier.startswith("CASE-"):
        raise ValueError("matter_id must not use a drawing case identity")
    return identifier


def _unique_identifiers(value: object, field: str) -> tuple[str, ...]:
    items = tuple(
        _identifier(item, f"{field}[{index}]")
        for index, item in enumerate(expect_sequence(value, field))
    )
    if len(items) != len(set(items)):
        raise ValueError(f"{field} contains duplicate identifiers")
    return items


def _bbox_document(bbox: tuple[float, float, float, float]) -> list[float]:
    return list(bbox)


def _bbox_number(value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("bbox must contain four numbers")
    return float(value)


def _bbox_tuple(value: object) -> tuple[float, float, float, float]:
    items = expect_sequence(value, "bbox")
    if len(items) != 4:
        raise ValueError("bbox must contain four numbers")
    bbox = BBox(
        left=_bbox_number(items[0]),
        bottom=_bbox_number(items[1]),
        right=_bbox_number(items[2]),
        top=_bbox_number(items[3]),
    )
    return (bbox.left, bbox.bottom, bbox.right, bbox.top)


@dataclass(frozen=True, slots=True)
class MatterIssue:
    """One mutable work issue, intentionally separate from Formal IssueStatus."""

    issue_id: str
    question: str
    work_state: MatterIssueState
    depends_on: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class MatterSourceBinding:
    """One exact reference to finalized evidence used by Matter work."""

    binding_id: str
    document_id: str
    revision_id: str
    page_number: int
    evidence_id: str
    bbox: tuple[float, float, float, float]
    source_hash: str
    evidence_snapshot_hash: str
    evidence_db_sha256: str

    @property
    def format(self) -> MatterSourceBindingFormat:
        return MATTER_SOURCE_BINDING_FORMAT

    @property
    def version(self) -> Literal[1]:
        return MATTER_SOURCE_BINDING_VERSION


@dataclass(frozen=True, slots=True)
class ReviewMatter:
    """Mutable reviewer work state; never a Formal Review authority."""

    matter_id: str
    title: str
    revision: int
    issues: tuple[MatterIssue, ...]
    source_bindings: tuple[MatterSourceBinding, ...]

    @property
    def format(self) -> MatterFormat:
        return REVIEW_MATTER_FORMAT

    @property
    def version(self) -> Literal[1]:
        return MATTER_VERSION


def decode_matter_issue_state(value: object, field: str) -> MatterIssueState:
    """Decode one allowed mutable Matter issue state."""
    return expect_literal(value, field, _MATTER_STATES)


def _decode_issue(value: object, index: int) -> MatterIssue:
    field = f"issues[{index}]"
    payload = expect_mapping(value, field)
    required = {"issue_id", "question", "work_state", "depends_on"}
    require_fields(payload, required, field)
    reject_unknown(payload, required, field)
    state = expect_string(payload.get("work_state"), f"{field}.work_state")
    if state in _FORMAL_ISSUE_STATUSES:
        raise ValueError(f"{field}.work_state uses formal issue status vocabulary")
    return MatterIssue(
        issue_id=_identifier(payload.get("issue_id"), f"{field}.issue_id"),
        question=expect_string(payload.get("question"), f"{field}.question"),
        work_state=decode_matter_issue_state(payload.get("work_state"), f"{field}.work_state"),
        depends_on=_unique_identifiers(payload.get("depends_on"), f"{field}.depends_on"),
    )


def decode_matter_source_binding(value: object) -> MatterSourceBinding:
    """Decode one source binding with exact evidence and file identities."""
    payload = expect_mapping(value, "matter_source_binding")
    required = {
        "format",
        "version",
        "binding_id",
        "document_id",
        "revision_id",
        "page_number",
        "evidence_id",
        "bbox",
        "source_hash",
        "evidence_snapshot_hash",
        "evidence_db_sha256",
    }
    require_fields(payload, required, "matter_source_binding")
    reject_unknown(payload, required, "matter_source_binding")
    if payload.get("format") != MATTER_SOURCE_BINDING_FORMAT:
        raise ValueError("unsupported matter_source_binding format")
    if payload.get("version") != MATTER_SOURCE_BINDING_VERSION:
        raise ValueError("unsupported matter_source_binding version")
    page_number = expect_int(payload.get("page_number"), "page_number")
    if page_number < 1:
        raise ValueError("page_number must be positive")
    return MatterSourceBinding(
        binding_id=_identifier(payload.get("binding_id"), "binding_id"),
        document_id=_identifier(payload.get("document_id"), "document_id"),
        revision_id=_identifier(payload.get("revision_id"), "revision_id"),
        page_number=page_number,
        evidence_id=_identifier(payload.get("evidence_id"), "evidence_id"),
        bbox=_bbox_tuple(payload.get("bbox")),
        source_hash=expect_sha256(payload.get("source_hash"), "source_hash"),
        evidence_snapshot_hash=expect_sha256(
            payload.get("evidence_snapshot_hash"), "evidence_snapshot_hash"
        ),
        evidence_db_sha256=expect_sha256(
            payload.get("evidence_db_sha256"), "evidence_db_sha256"
        ),
    )


def matter_source_binding_document(binding: MatterSourceBinding) -> dict[str, object]:
    """Return the canonical source-binding document."""
    return {
        "format": MATTER_SOURCE_BINDING_FORMAT,
        "version": MATTER_SOURCE_BINDING_VERSION,
        "binding_id": binding.binding_id,
        "document_id": binding.document_id,
        "revision_id": binding.revision_id,
        "page_number": binding.page_number,
        "evidence_id": binding.evidence_id,
        "bbox": _bbox_document(binding.bbox),
        "source_hash": binding.source_hash,
        "evidence_snapshot_hash": binding.evidence_snapshot_hash,
        "evidence_db_sha256": binding.evidence_db_sha256,
    }


def decode_review_matter(value: object) -> ReviewMatter:
    """Decode a strict v1 ReviewMatter document."""
    payload = expect_mapping(value, "review_matter")
    required = {
        "format",
        "version",
        "matter_id",
        "title",
        "revision",
        "issues",
        "source_bindings",
    }
    require_fields(payload, required, "review_matter")
    reject_unknown(payload, required, "review_matter")
    if payload.get("format") != REVIEW_MATTER_FORMAT:
        raise ValueError("unsupported review_matter format")
    if payload.get("version") != MATTER_VERSION:
        raise ValueError("unsupported review_matter version")
    revision = expect_int(payload.get("revision"), "revision")
    if revision < 1:
        raise ValueError("revision must be positive")
    issues = tuple(
        _decode_issue(item, index)
        for index, item in enumerate(expect_sequence(payload.get("issues"), "issues"))
    )
    issue_ids = tuple(issue.issue_id for issue in issues)
    if len(issue_ids) != len(set(issue_ids)):
        raise ValueError("duplicate issue identifier")
    issue_id_set = set(issue_ids)
    for issue in issues:
        unknown_dependencies = sorted(set(issue.depends_on) - issue_id_set)
        if unknown_dependencies:
            raise ValueError(
                f"issue {issue.issue_id} references unknown dependency "
                f"{unknown_dependencies[0]}"
            )
    bindings = tuple(
        decode_matter_source_binding(item)
        for item in expect_sequence(payload.get("source_bindings"), "source_bindings")
    )
    binding_ids = tuple(binding.binding_id for binding in bindings)
    if len(binding_ids) != len(set(binding_ids)):
        raise ValueError("duplicate source binding identifier")
    return ReviewMatter(
        matter_id=_identifier(payload.get("matter_id"), "matter_id"),
        title=expect_string(payload.get("title"), "title"),
        revision=revision,
        issues=issues,
        source_bindings=bindings,
    )


def review_matter_document(matter: ReviewMatter) -> dict[str, object]:
    """Return the explicit canonical v1 ReviewMatter document."""
    return {
        "format": REVIEW_MATTER_FORMAT,
        "version": MATTER_VERSION,
        "matter_id": matter.matter_id,
        "title": matter.title,
        "revision": matter.revision,
        "issues": [
            {
                "issue_id": issue.issue_id,
                "question": issue.question,
                "work_state": issue.work_state,
                "depends_on": list(issue.depends_on),
            }
            for issue in matter.issues
        ],
        "source_bindings": [
            matter_source_binding_document(binding) for binding in matter.source_bindings
        ],
    }
