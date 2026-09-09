"""Immutable exact-revision boundary from Matter work to Formal Review."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from evidence_review.canonical_json import sha256_json
from evidence_review.contracts.question_plan import (
    QuestionIssue,
    SearchRequest,
)
from evidence_review.contracts.validation import (
    expect_int,
    expect_mapping,
    expect_sha256,
    expect_string,
    reject_unknown,
    require_fields,
)
from evidence_review.evidence.finalization import validate_finalized_evidence
from evidence_review.evidence.snapshot import finalized_evidence_provenance
from evidence_review.evidence.store import EvidenceStore
from evidence_review.review_matter.contracts import (
    FORMALIZATION_SNAPSHOT_FORMAT,
    FORMALIZATION_SNAPSHOT_VERSION,
    MatterSourceBinding,
    ReviewMatter,
    decode_matter_source_binding,
    matter_source_binding_document,
)
from evidence_review.review_matter.scope import (
    ReviewScope,
    build_explicit_review_scope,
    decode_review_scope,
    review_scope_document,
)
from evidence_review.review_matter.store import MatterStore


@dataclass(frozen=True, slots=True)
class FormalizedEvidence:
    binding: MatterSourceBinding
    text: str


@dataclass(frozen=True, slots=True)
class FormalizationSnapshot:
    snapshot_id: str
    matter_id: str
    matter_revision: int
    review_scope: ReviewScope
    evidence_snapshot_hash: str
    evidence_db_sha256: str
    evidence_schema_version: int
    selected_evidence: tuple[FormalizedEvidence, ...]

    @property
    def selected_evidence_text(self) -> str:
        return "\n".join(item.text for item in self.selected_evidence)

    @property
    def source_bindings(self) -> tuple[MatterSourceBinding, ...]:
        return tuple(item.binding for item in self.selected_evidence)


def _identity_document(document: Mapping[str, object]) -> dict[str, object]:
    return {key: value for key, value in document.items() if key != "snapshot_id"}


def _snapshot_id(document: Mapping[str, object]) -> str:
    return f"SNAP-{sha256_json(_identity_document(document))[:20].upper()}"


def formalization_snapshot_document(snapshot: FormalizationSnapshot) -> dict[str, object]:
    """Return the canonical immutable snapshot document."""
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
            {"binding": matter_source_binding_document(item.binding), "text": item.text}
            for item in snapshot.selected_evidence
        ],
    }
    expected = _snapshot_id(document)
    if expected != snapshot.snapshot_id:
        raise ValueError("FORMALIZATION_SNAPSHOT_ID_MISMATCH")
    return document


def decode_formalization_snapshot(value: object) -> FormalizationSnapshot:
    """Decode and verify an immutable snapshot document."""
    payload = expect_mapping(value, "formalization_snapshot")
    required = {
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
    require_fields(payload, required, "formalization_snapshot")
    reject_unknown(payload, required, "formalization_snapshot")
    if payload["format"] != FORMALIZATION_SNAPSHOT_FORMAT:
        raise ValueError("unsupported formalization snapshot format")
    if payload["version"] != FORMALIZATION_SNAPSHOT_VERSION:
        raise ValueError("unsupported formalization snapshot version")
    snapshot_id = expect_string(payload["snapshot_id"], "snapshot_id")
    matter_id = expect_string(payload["matter_id"], "matter_id")
    matter_revision = expect_int(payload["matter_revision"], "matter_revision")
    if matter_revision < 1:
        raise ValueError("matter_revision must be positive")
    scope = decode_review_scope(payload["review_scope"])
    evidence_snapshot_hash = expect_sha256(
        payload["evidence_snapshot_hash"], "evidence_snapshot_hash"
    )
    evidence_db_sha256 = expect_sha256(payload["evidence_db_sha256"], "evidence_db_sha256")
    evidence_schema_version = expect_int(
        payload["evidence_schema_version"], "evidence_schema_version"
    )
    if evidence_schema_version < 1:
        raise ValueError("evidence_schema_version must be positive")
    raw_selected = payload["selected_evidence"]
    if not isinstance(raw_selected, list):
        raise ValueError("selected_evidence must be an array")
    selected: list[FormalizedEvidence] = []
    seen: set[str] = set()
    for index, raw_item in enumerate(raw_selected):
        item = expect_mapping(raw_item, f"selected_evidence[{index}]")
        require_fields(item, {"binding", "text"}, f"selected_evidence[{index}]")
        reject_unknown(item, {"binding", "text"}, f"selected_evidence[{index}]")
        binding = decode_matter_source_binding(item["binding"])
        if (
            binding.evidence_snapshot_hash != evidence_snapshot_hash
            or binding.evidence_db_sha256 != evidence_db_sha256
        ):
            raise ValueError(
                f"selected_evidence[{index}] binding evidence identity mismatch"
            )
        if binding.binding_id in seen:
            raise ValueError("selected_evidence contains duplicate binding")
        seen.add(binding.binding_id)
        selected.append(
            FormalizedEvidence(binding=binding, text=expect_string(item["text"], "text"))
        )
    snapshot = FormalizationSnapshot(
        snapshot_id=snapshot_id,
        matter_id=matter_id,
        matter_revision=matter_revision,
        review_scope=scope,
        evidence_snapshot_hash=evidence_snapshot_hash,
        evidence_db_sha256=evidence_db_sha256,
        evidence_schema_version=evidence_schema_version,
        selected_evidence=tuple(selected),
    )
    if _snapshot_id(formalization_snapshot_document(snapshot)) != snapshot_id:
        raise ValueError("FORMALIZATION_SNAPSHOT_ID_MISMATCH")
    return snapshot


def _scope_for_matter(matter: ReviewMatter) -> ReviewScope:
    issues = matter.issues
    if not issues:
        raise ValueError("FORMALIZATION_SCOPE_EMPTY")
    question_issues = tuple(
        QuestionIssue(
            id=issue.issue_id,
            question=issue.question,
            depends_on=issue.depends_on,
            required_evidence_roles=("rule",),
        )
        for issue in issues
    )
    search_requests = tuple(
        SearchRequest(
            id=f"SEARCH-{issue.issue_id}",
            issue_ids=(issue.issue_id,),
            text=issue.question,
            kind="phrase",
            source="user",
            role="rule",
        )
        for issue in issues
    )
    return build_explicit_review_scope(
        question=matter.title,
        issues=question_issues,
        search_requests=search_requests,
    )


def _selected_evidence(
    evidence_db: Path,
    bindings: tuple[MatterSourceBinding, ...],
    *,
    evidence_snapshot_hash: str,
    evidence_db_sha256: str,
) -> tuple[FormalizedEvidence, ...]:
    with EvidenceStore(evidence_db, read_only=True) as store:
        validate_finalized_evidence(store)
        connection = store.require_connection()
        result: list[FormalizedEvidence] = []
        for binding in bindings:
            if (
                binding.evidence_snapshot_hash != evidence_snapshot_hash
                or binding.evidence_db_sha256 != evidence_db_sha256
            ):
                raise ValueError("FORMALIZATION_SELECTED_EVIDENCE_IDENTITY_MISMATCH")
            row = connection.execute(
                """
                SELECT document_id, revision_id, page_number, bbox_json,
                       source_hash, normalized_text, raw_text
                FROM retrieval_records
                WHERE evidence_id = ?
                """,
                (binding.evidence_id,),
            ).fetchone()
            if row is None:
                raise ValueError("FORMALIZATION_SELECTED_EVIDENCE_NOT_FOUND")
            try:
                raw_bbox = json.loads(str(row["bbox_json"]))
            except (TypeError, json.JSONDecodeError) as error:
                raise ValueError("FORMALIZATION_SELECTED_EVIDENCE_BBOX_INVALID") from error
            if (
                not isinstance(raw_bbox, list)
                or len(raw_bbox) != 4
                or any(
                    isinstance(item, bool) or not isinstance(item, (int, float))
                    for item in raw_bbox
                )
                or tuple(float(item) for item in raw_bbox) != binding.bbox
            ):
                raise ValueError("FORMALIZATION_SELECTED_EVIDENCE_IDENTITY_MISMATCH")
            if (
                row["document_id"] != binding.document_id
                or row["revision_id"] != binding.revision_id
                or row["page_number"] != binding.page_number
                or row["source_hash"] != binding.source_hash
            ):
                raise ValueError("FORMALIZATION_SELECTED_EVIDENCE_IDENTITY_MISMATCH")
            text = row["normalized_text"] or row["raw_text"]
            if not isinstance(text, str) or not text:
                raise ValueError("FORMALIZATION_SELECTED_EVIDENCE_TEXT_INVALID")
            result.append(FormalizedEvidence(binding=binding, text=text))
    return tuple(result)


def create_formalization_snapshot(
    store: MatterStore,
    matter_id: str,
    expected_revision: int,
    evidence_db: Path,
) -> FormalizationSnapshot:
    """Freeze one exact Matter revision and finalized evidence identity."""
    database = Path(evidence_db)
    try:
        with EvidenceStore(database, read_only=True) as evidence_store:
            state = validate_finalized_evidence(evidence_store)
            provenance = finalized_evidence_provenance(database)
        snapshot_hash = provenance["evidence_snapshot_hash"]
        database_sha = provenance["evidence_db_sha256"]
        if (
            state.snapshot_hash != snapshot_hash
            or state.schema_version != provenance["schema_version"]
        ):
            raise ValueError("FORMALIZATION_EVIDENCE_PROVENANCE_MISMATCH")
        if not isinstance(snapshot_hash, str) or not isinstance(database_sha, str):
            raise ValueError("FORMALIZATION_EVIDENCE_PROVENANCE_INVALID")
    except Exception as error:
        raise ValueError("FORMALIZATION_EVIDENCE_INVALID") from error

    with store.transaction():
        matter = store.load(matter_id)
        if matter.revision != expected_revision:
            raise ValueError("MATTER_CHANGED_DURING_FORMALIZATION")
        evidence_binding = store.get_evidence_binding(matter_id)
        if evidence_binding is None:
            raise ValueError("FORMALIZATION_EVIDENCE_NOT_BOUND")
        if (
            evidence_binding["evidence_snapshot_hash"] != snapshot_hash
            or evidence_binding["evidence_db_sha256"] != database_sha
        ):
            raise ValueError("FORMALIZATION_EVIDENCE_BINDING_MISMATCH")
        blocked = {
            issue.issue_id
            for issue in matter.issues
            if issue.work_state != "READY_TO_FORMALIZE"
        }
        if blocked:
            raise ValueError("FORMALIZATION_REQUIRED_ISSUE_NOT_READY")
        schema_version = expect_int(
            evidence_binding["schema_version"], "evidence_binding.schema_version"
        )
        scope = _scope_for_matter(matter)
        selected_bindings = store.selected_evidence_bindings(matter_id)
        if not selected_bindings:
            raise ValueError("FORMALIZATION_SELECTED_EVIDENCE_EMPTY")
        selected = _selected_evidence(
            database,
            selected_bindings,
            evidence_snapshot_hash=snapshot_hash,
            evidence_db_sha256=database_sha,
        )
        payload: dict[str, object] = {
            "format": FORMALIZATION_SNAPSHOT_FORMAT,
            "version": FORMALIZATION_SNAPSHOT_VERSION,
            "snapshot_id": "",
            "matter_id": matter.matter_id,
            "matter_revision": matter.revision,
            "review_scope": review_scope_document(scope),
            "evidence_snapshot_hash": snapshot_hash,
            "evidence_db_sha256": database_sha,
            "evidence_schema_version": schema_version,
            "selected_evidence": [
                {"binding": matter_source_binding_document(item.binding), "text": item.text}
                for item in selected
            ],
        }
        snapshot = FormalizationSnapshot(
            snapshot_id=_snapshot_id(payload),
            matter_id=matter.matter_id,
            matter_revision=matter.revision,
            review_scope=scope,
            evidence_snapshot_hash=snapshot_hash,
            evidence_db_sha256=database_sha,
            evidence_schema_version=schema_version,
            selected_evidence=selected,
        )
        # Persist create-only. The snapshot document is immutable even when
        # the call is retried.
        store.apply_formalization_snapshot(snapshot)
        return snapshot
