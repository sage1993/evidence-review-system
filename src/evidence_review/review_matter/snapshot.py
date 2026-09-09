"""Immutable formalization snapshots for one exact ReviewMatter revision."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from evidence_review.canonical_json import dump_bytes, sha256_json
from evidence_review.contracts.common import BBox, Citation
from evidence_review.contracts.formats import FORMALIZATION_SNAPSHOT_FORMAT
from evidence_review.contracts.identifiers import validate_identifier
from evidence_review.contracts.question_plan import QuestionIssue, SearchRequest
from evidence_review.contracts.validation import (
    expect_int,
    expect_mapping,
    expect_sequence,
    expect_sha256,
    expect_string,
    reject_unknown,
    require_fields,
)
from evidence_review.evidence.snapshot import finalized_evidence_provenance
from evidence_review.evidence.store import EvidenceStore
from evidence_review.review_matter.contracts import MatterSourceBinding, ReviewMatter
from evidence_review.review_matter.scope import (
    ReviewScope,
    decode_review_scope,
    review_scope_document,
)
from evidence_review.review_matter.scope_adapters import review_scope_from_explicit_input
from evidence_review.review_matter.store import MatterAlreadyExists, MatterStore

FORMALIZATION_SNAPSHOT_VERSION = 1
_SNAPSHOT_FIELDS = {
    "format",
    "version",
    "snapshot_id",
    "matter_id",
    "matter_revision",
    "review_scope",
    "evidence_snapshot_hash",
    "evidence_db_sha256",
    "evidence_schema_version",
    "selected_evidence",
}
_SELECTION_FIELDS = {"binding_id", "citation", "text"}
_CITATION_FIELDS = {
    "citation_id",
    "document_id",
    "revision_id",
    "page_number",
    "evidence_id",
    "bbox",
    "source_hash",
}


@dataclass(frozen=True, slots=True)
class FormalizationEvidence:
    """One exact textual evidence record selected for formalization."""

    binding_id: str
    citation: Citation
    text: str


@dataclass(frozen=True, slots=True)
class FormalizationSnapshot:
    """One immutable, evidence-bound control input for Formal Review."""

    snapshot_id: str
    matter_id: str
    matter_revision: int
    review_scope: ReviewScope
    evidence_snapshot_hash: str
    evidence_db_sha256: str
    evidence_schema_version: int
    selected_evidence: tuple[FormalizationEvidence, ...]


def _bbox(value: object, field: str) -> BBox:
    values = expect_sequence(value, field)
    if len(values) != 4:
        raise ValueError(f"{field} must contain four numbers")
    numbers: list[float] = []
    for index, item in enumerate(values):
        if isinstance(item, bool) or not isinstance(item, (int, float)):
            raise ValueError(f"{field}[{index}] must be a number")
        numbers.append(float(item))
    return BBox(*numbers)


def _citation_document(citation: Citation) -> dict[str, object]:
    return {
        "citation_id": citation.citation_id,
        "document_id": citation.document_id,
        "revision_id": citation.revision_id,
        "page_number": citation.page_number,
        "evidence_id": citation.evidence_id,
        "bbox": [
            citation.bbox.left,
            citation.bbox.bottom,
            citation.bbox.right,
            citation.bbox.top,
        ],
        "source_hash": citation.source_hash,
    }


def _decode_citation(value: object, field: str) -> Citation:
    payload = expect_mapping(value, field)
    require_fields(payload, _CITATION_FIELDS, field)
    reject_unknown(payload, _CITATION_FIELDS, field)
    evidence_id = validate_identifier(payload.get("evidence_id"), f"{field}.evidence_id")
    citation = Citation(
        citation_id=expect_string(payload.get("citation_id"), f"{field}.citation_id"),
        document_id=validate_identifier(payload.get("document_id"), f"{field}.document_id"),
        revision_id=validate_identifier(payload.get("revision_id"), f"{field}.revision_id"),
        page_number=expect_int(payload.get("page_number"), f"{field}.page_number"),
        evidence_id=evidence_id,
        bbox=_bbox(payload.get("bbox"), f"{field}.bbox"),
        source_hash=expect_sha256(payload.get("source_hash"), f"{field}.source_hash"),
    )
    if citation.page_number < 1:
        raise ValueError(f"{field}.page_number must be positive")
    if citation.citation_id != f"CIT-{citation.evidence_id}":
        raise ValueError(f"{field}.citation_id does not match evidence identity")
    return citation


def _selection_document(selection: FormalizationEvidence) -> dict[str, object]:
    return {
        "binding_id": selection.binding_id,
        "citation": _citation_document(selection.citation),
        "text": selection.text,
    }


def _decode_selection(value: object, index: int) -> FormalizationEvidence:
    field = f"selected_evidence[{index}]"
    payload = expect_mapping(value, field)
    require_fields(payload, _SELECTION_FIELDS, field)
    reject_unknown(payload, _SELECTION_FIELDS, field)
    return FormalizationEvidence(
        binding_id=validate_identifier(payload.get("binding_id"), f"{field}.binding_id"),
        citation=_decode_citation(payload.get("citation"), f"{field}.citation"),
        text=expect_string(payload.get("text"), f"{field}.text"),
    )


def _identity_document(document: dict[str, object]) -> dict[str, object]:
    return {key: value for key, value in document.items() if key != "snapshot_id"}


def _snapshot_id(document: dict[str, object]) -> str:
    return "SNAP-" + sha256_json(_identity_document(document))


def formalization_snapshot_document(snapshot: FormalizationSnapshot) -> dict[str, object]:
    """Encode one snapshot as a strict deterministic JSON-compatible document."""
    document: dict[str, object] = {
        "format": FORMALIZATION_SNAPSHOT_FORMAT,
        "version": FORMALIZATION_SNAPSHOT_VERSION,
        "snapshot_id": snapshot.snapshot_id,
        "matter_id": snapshot.matter_id,
        "matter_revision": snapshot.matter_revision,
        "review_scope": review_scope_document(snapshot.review_scope),
        "evidence_snapshot_hash": snapshot.evidence_snapshot_hash,
        "evidence_db_sha256": snapshot.evidence_db_sha256,
        "evidence_schema_version": snapshot.evidence_schema_version,
        "selected_evidence": [
            _selection_document(selection) for selection in snapshot.selected_evidence
        ],
    }
    if _snapshot_id(document) != snapshot.snapshot_id:
        raise ValueError("FORMALIZATION_SNAPSHOT_ID_MISMATCH")
    return document


def decode_formalization_snapshot(value: object) -> FormalizationSnapshot:
    """Strictly decode and revalidate an immutable snapshot document."""
    payload = expect_mapping(value, "formalization_snapshot")
    require_fields(payload, _SNAPSHOT_FIELDS, "formalization_snapshot")
    reject_unknown(payload, _SNAPSHOT_FIELDS, "formalization_snapshot")
    if payload.get("format") != FORMALIZATION_SNAPSHOT_FORMAT:
        raise ValueError("unsupported formalization snapshot format")
    if payload.get("version") != FORMALIZATION_SNAPSHOT_VERSION:
        raise ValueError("unsupported formalization snapshot version")
    revision = expect_int(payload.get("matter_revision"), "matter_revision")
    schema_version = expect_int(
        payload.get("evidence_schema_version"), "evidence_schema_version"
    )
    if revision < 1 or schema_version < 1:
        raise ValueError("formalization snapshot versions must be positive")
    selections = tuple(
        _decode_selection(item, index)
        for index, item in enumerate(
            expect_sequence(payload.get("selected_evidence"), "selected_evidence")
        )
    )
    if not selections:
        raise ValueError("selected_evidence must not be empty")
    binding_ids = [selection.binding_id for selection in selections]
    evidence_ids = [selection.citation.evidence_id for selection in selections]
    if len(binding_ids) != len(set(binding_ids)) or len(evidence_ids) != len(set(evidence_ids)):
        raise ValueError("selected_evidence identities must be unique")
    snapshot = FormalizationSnapshot(
        snapshot_id=validate_identifier(payload.get("snapshot_id"), "snapshot_id"),
        matter_id=validate_identifier(payload.get("matter_id"), "matter_id"),
        matter_revision=revision,
        review_scope=decode_review_scope(payload.get("review_scope")),
        evidence_snapshot_hash=expect_sha256(
            payload.get("evidence_snapshot_hash"), "evidence_snapshot_hash"
        ),
        evidence_db_sha256=expect_sha256(
            payload.get("evidence_db_sha256"), "evidence_db_sha256"
        ),
        evidence_schema_version=schema_version,
        selected_evidence=selections,
    )
    document = formalization_snapshot_document_unchecked(snapshot)
    if _snapshot_id(document) != snapshot.snapshot_id:
        raise ValueError("FORMALIZATION_SNAPSHOT_ID_MISMATCH")
    return snapshot


def formalization_snapshot_document_unchecked(snapshot: FormalizationSnapshot) -> dict[str, object]:
    """Encode a decoded snapshot before verifying its deterministic identifier."""
    return {
        "format": FORMALIZATION_SNAPSHOT_FORMAT,
        "version": FORMALIZATION_SNAPSHOT_VERSION,
        "snapshot_id": snapshot.snapshot_id,
        "matter_id": snapshot.matter_id,
        "matter_revision": snapshot.matter_revision,
        "review_scope": review_scope_document(snapshot.review_scope),
        "evidence_snapshot_hash": snapshot.evidence_snapshot_hash,
        "evidence_db_sha256": snapshot.evidence_db_sha256,
        "evidence_schema_version": snapshot.evidence_schema_version,
        "selected_evidence": [
            _selection_document(selection) for selection in snapshot.selected_evidence
        ],
    }


def _ready_matter(matter: ReviewMatter) -> None:
    if not matter.issues:
        raise ValueError("FORMALIZATION_NO_REQUIRED_ISSUES")
    blocked = [
        issue.work_state
        for issue in matter.issues
        if issue.work_state != "READY_TO_FORMALIZE"
    ]
    if blocked:
        raise ValueError(f"FORMALIZATION_MATTER_NOT_READY: {blocked[0]}")
    if not matter.source_bindings:
        raise ValueError("FORMALIZATION_SELECTED_EVIDENCE_REQUIRED")


def _scope_for_matter(matter: ReviewMatter) -> ReviewScope:
    issues = tuple(
        QuestionIssue(
            id=issue.issue_id,
            question=issue.question,
            depends_on=issue.depends_on,
            required_evidence_roles=("supporting_fact",),
        )
        for issue in matter.issues
    )
    return review_scope_from_explicit_input(
        question=matter.title,
        issues=issues,
        search_requests=(
            SearchRequest(
                id="FORMALIZATION-SCOPE-1",
                issue_ids=tuple(issue.issue_id for issue in matter.issues),
                text=matter.title,
                kind="phrase",
                source="user",
                role="supporting_fact",
            ),
        ),
    )


def _provenance(evidence_db: Path) -> tuple[str, str, int]:
    try:
        provenance = finalized_evidence_provenance(evidence_db)
        snapshot_hash = expect_sha256(
            provenance.get("evidence_snapshot_hash"), "evidence_snapshot_hash"
        )
        database_sha = expect_sha256(
            provenance.get("evidence_db_sha256"), "evidence_db_sha256"
        )
        schema_version = expect_int(provenance.get("schema_version"), "schema_version")
        if schema_version < 1:
            raise ValueError("schema_version must be positive")
        return snapshot_hash, database_sha, schema_version
    except Exception as error:
        raise ValueError("FORMALIZATION_EVIDENCE_INVALID") from error


def _validate_binding_provenance(
    store: MatterStore,
    matter: ReviewMatter,
    provenance: tuple[str, str, int],
) -> None:
    bound = store.get_evidence_binding(matter.matter_id)
    if bound is None:
        raise ValueError("FORMALIZATION_EVIDENCE_BINDING_MISSING")
    snapshot_hash, database_sha, schema_version = provenance
    if (
        bound.get("evidence_snapshot_hash"),
        bound.get("evidence_db_sha256"),
        bound.get("schema_version"),
    ) != provenance:
        raise ValueError("FORMALIZATION_EVIDENCE_BINDING_MISMATCH")
    for binding in matter.source_bindings:
        if (
            binding.evidence_snapshot_hash,
            binding.evidence_db_sha256,
        ) != (snapshot_hash, database_sha):
            raise ValueError("FORMALIZATION_SELECTED_EVIDENCE_PROVENANCE_MISMATCH")


def _database_selection(
    evidence_db: Path, binding: MatterSourceBinding
) -> FormalizationEvidence:
    try:
        with EvidenceStore(evidence_db, read_only=True) as store:
            row = store.require_connection().execute(
                """
                SELECT r.evidence_id, r.document_id, r.revision_id, r.page_number,
                       r.bbox_json, r.source_hash, r.raw_text,
                       e.bbox_json AS element_bbox_json, e.raw_text AS element_raw_text,
                       p.revision_id AS page_revision_id, p.page_number AS page_page_number,
                       rev.document_id AS revision_document_id,
                       rev.source_hash AS revision_source_hash
                FROM retrieval_records AS r
                JOIN elements AS e ON e.id = r.evidence_id
                JOIN pages AS p ON p.id = e.page_id
                JOIN revisions AS rev ON rev.id = p.revision_id
                WHERE r.evidence_id = ?
                """,
                (binding.evidence_id,),
            ).fetchone()
    except Exception as error:
        raise ValueError("FORMALIZATION_SELECTED_EVIDENCE_INVALID") from error
    if row is None:
        raise ValueError("FORMALIZATION_SELECTED_EVIDENCE_NOT_FOUND")
    try:
        retrieval_bbox = _bbox(json.loads(str(row["bbox_json"])), "retrieval bbox")
        element_bbox = _bbox(json.loads(str(row["element_bbox_json"])), "element bbox")
        citation = Citation(
            citation_id=f"CIT-{row['evidence_id']}",
            document_id=str(row["document_id"]),
            revision_id=str(row["revision_id"]),
            page_number=int(row["page_number"]),
            evidence_id=str(row["evidence_id"]),
            bbox=retrieval_bbox,
            source_hash=str(row["source_hash"]),
        )
        text = expect_string(row["raw_text"], "selected evidence text")
    except (TypeError, ValueError, json.JSONDecodeError) as error:
        raise ValueError("FORMALIZATION_SELECTED_EVIDENCE_INVALID") from error
    if (
        citation.document_id,
        citation.revision_id,
        citation.page_number,
        citation.evidence_id,
        citation.bbox,
        citation.source_hash,
    ) != (
        binding.document_id,
        binding.revision_id,
        binding.page_number,
        binding.evidence_id,
        BBox(*binding.bbox),
        binding.source_hash,
    ):
        raise ValueError("FORMALIZATION_SELECTED_EVIDENCE_IDENTITY_MISMATCH")
    if (
        element_bbox != citation.bbox
        or row["element_raw_text"] != text
        or row["page_revision_id"] != citation.revision_id
        or row["page_page_number"] != citation.page_number
        or row["revision_document_id"] != citation.document_id
        or row["revision_source_hash"] != citation.source_hash
    ):
        raise ValueError("FORMALIZATION_SELECTED_EVIDENCE_IDENTITY_MISMATCH")
    return FormalizationEvidence(binding.binding_id, citation, text)


def _selected_evidence(
    evidence_db: Path, matter: ReviewMatter
) -> tuple[FormalizationEvidence, ...]:
    selections = tuple(
        _database_selection(evidence_db, binding)
        for binding in sorted(matter.source_bindings, key=lambda item: item.binding_id)
    )
    if len({item.citation.evidence_id for item in selections}) != len(selections):
        raise ValueError("FORMALIZATION_SELECTED_EVIDENCE_DUPLICATE")
    return selections


def _snapshot_from_values(
    matter: ReviewMatter,
    provenance: tuple[str, str, int],
    selected_evidence: tuple[FormalizationEvidence, ...],
) -> FormalizationSnapshot:
    snapshot_hash, database_sha, schema_version = provenance
    scope = _scope_for_matter(matter)
    provisional = FormalizationSnapshot(
        snapshot_id="SNAP-" + "0" * 64,
        matter_id=matter.matter_id,
        matter_revision=matter.revision,
        review_scope=scope,
        evidence_snapshot_hash=snapshot_hash,
        evidence_db_sha256=database_sha,
        evidence_schema_version=schema_version,
        selected_evidence=selected_evidence,
    )
    document = formalization_snapshot_document_unchecked(provisional)
    snapshot_id = _snapshot_id(document)
    return FormalizationSnapshot(
        snapshot_id=snapshot_id,
        matter_id=provisional.matter_id,
        matter_revision=provisional.matter_revision,
        review_scope=provisional.review_scope,
        evidence_snapshot_hash=provisional.evidence_snapshot_hash,
        evidence_db_sha256=provisional.evidence_db_sha256,
        evidence_schema_version=provisional.evidence_schema_version,
        selected_evidence=provisional.selected_evidence,
    )


def _decode_persisted(
    record: tuple[str, str, int, bytes]
) -> FormalizationSnapshot:
    row_snapshot_id, row_matter_id, row_matter_revision, document = record
    try:
        decoded = json.loads(document.decode("utf-8"))
        snapshot = decode_formalization_snapshot(decoded)
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as error:
        raise ValueError("FORMALIZATION_SNAPSHOT_PERSISTED_DOCUMENT_INVALID") from error
    if dump_bytes(formalization_snapshot_document(snapshot)) != document:
        raise ValueError("FORMALIZATION_SNAPSHOT_PERSISTED_BYTES_MISMATCH")
    if (
        snapshot.snapshot_id,
        snapshot.matter_id,
        snapshot.matter_revision,
    ) != (row_snapshot_id, row_matter_id, row_matter_revision):
        raise ValueError("FORMALIZATION_SNAPSHOT_METADATA_MISMATCH")
    return snapshot


def create_formalization_snapshot(
    store: MatterStore,
    matter_id: str,
    expected_revision: int,
    evidence_db: Path,
) -> FormalizationSnapshot:
    """Freeze one ready Matter revision with exact finalized evidence provenance."""
    if isinstance(expected_revision, bool) or not isinstance(expected_revision, int):
        raise ValueError("MATTER_CHANGED_DURING_FORMALIZATION")
    current = store.load(matter_id)
    if current.revision != expected_revision:
        raise ValueError("MATTER_CHANGED_DURING_FORMALIZATION")
    _ready_matter(current)
    database = Path(evidence_db)
    provenance = _provenance(database)
    _validate_binding_provenance(store, current, provenance)
    selections = _selected_evidence(database, current)
    snapshot = _snapshot_from_values(current, provenance, selections)
    canonical_document = dump_bytes(formalization_snapshot_document(snapshot))

    with store.transaction():
        latest = store.load(matter_id)
        if latest != current or latest.revision != expected_revision:
            raise ValueError("MATTER_CHANGED_DURING_FORMALIZATION")
        _ready_matter(latest)
        if _provenance(database) != provenance:
            raise ValueError("EVIDENCE_CHANGED_DURING_FORMALIZATION")
        _validate_binding_provenance(store, latest, provenance)
        try:
            store.persist_formalization_snapshot(
                snapshot_id=snapshot.snapshot_id,
                matter_id=snapshot.matter_id,
                matter_revision=snapshot.matter_revision,
                canonical_document=canonical_document,
            )
        except MatterAlreadyExists as error:
            raise ValueError(str(error)) from error
    record = store.load_formalization_snapshot_record(snapshot.snapshot_id)
    if record is None:
        raise ValueError("FORMALIZATION_SNAPSHOT_NOT_FOUND")
    return _decode_persisted(record)


def load_formalization_snapshot(
    store: MatterStore, snapshot_id: str
) -> FormalizationSnapshot:
    """Load one immutable snapshot or fail closed when its ID is absent."""
    record = store.load_formalization_snapshot_record(snapshot_id)
    if record is None:
        raise ValueError("FORMALIZATION_SNAPSHOT_NOT_FOUND")
    return _decode_persisted(record)


def list_formalization_snapshots(store: MatterStore) -> tuple[FormalizationSnapshot, ...]:
    """Load every persisted snapshot and reject malformed immutable artifacts."""
    return tuple(
        _decode_persisted(record)
        for record in store.list_formalization_snapshot_records()
    )


__all__ = [
    "FORMALIZATION_SNAPSHOT_VERSION",
    "FormalizationEvidence",
    "FormalizationSnapshot",
    "create_formalization_snapshot",
    "decode_formalization_snapshot",
    "formalization_snapshot_document",
    "load_formalization_snapshot",
    "list_formalization_snapshots",
]
