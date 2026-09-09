"""One-way adapter from an immutable Matter snapshot to Formal Review."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from evidence_review.canonical_json import dump_bytes
from evidence_review.evidence.finalization import validate_finalized_evidence
from evidence_review.evidence.snapshot import finalized_evidence_provenance
from evidence_review.evidence.store import EvidenceStore
from evidence_review.review_matter.contracts import MatterSourceBinding
from evidence_review.review_matter.snapshot import (
    FormalizationSnapshot,
    _selected_evidence,
    formalization_snapshot_document,
)
from evidence_review.review_matter.store import MatterNotFound, MatterStore
from evidence_review.review_question import (
    PreparedReviewQuestion,
    _evidence_database,
    build_review_run_request,
    prepare_review_request_document,
)


def _citation(binding: MatterSourceBinding) -> dict[str, object]:
    return {
        "citation_id": f"CIT-{binding.evidence_id}",
        "document_id": binding.document_id,
        "revision_id": binding.revision_id,
        "page_number": binding.page_number,
        "evidence_id": binding.evidence_id,
        "bbox": list(binding.bbox),
        "source_hash": binding.source_hash,
    }


def _scope_document(snapshot: FormalizationSnapshot) -> dict[str, object]:
    from evidence_review.review_matter.scope import review_scope_document

    return review_scope_document(snapshot.review_scope)


def _persisted_snapshot(
    workspace: Path, snapshot: FormalizationSnapshot
) -> FormalizationSnapshot:
    matter_database = workspace / "matter.sqlite"
    if not matter_database.is_file():
        raise ValueError("FORMALIZATION_SNAPSHOT_STORE_NOT_FOUND")
    with MatterStore(matter_database) as store:
        try:
            loaded = store.load_formalization_snapshot(snapshot.snapshot_id)
        except MatterNotFound as error:
            raise ValueError(str(error)) from error
    if not isinstance(loaded, FormalizationSnapshot):
        raise ValueError("FORMALIZATION_SNAPSHOT_INVALID")
    if dump_bytes(formalization_snapshot_document(loaded)) != dump_bytes(
        formalization_snapshot_document(snapshot)
    ):
        raise ValueError("FORMALIZATION_SNAPSHOT_MISMATCH")
    return loaded


def formalize_snapshot(
    workspace: Path,
    snapshot: FormalizationSnapshot,
    *,
    calculations: Sequence[object] = (),
    rules: Sequence[object] = (),
    approved_rule_result_ids: Sequence[str] = (),
) -> PreparedReviewQuestion:
    """Create exactly one existing Formal Review RUN from a snapshot."""
    if not isinstance(snapshot, FormalizationSnapshot):
        raise ValueError("snapshot must be a FormalizationSnapshot")
    snapshot = _persisted_snapshot(workspace, snapshot)
    evidence_db = _evidence_database(workspace)
    with EvidenceStore(evidence_db, read_only=True) as store:
        validate_finalized_evidence(store)
        provenance = finalized_evidence_provenance(evidence_db)
    if (
        provenance.get("evidence_snapshot_hash") != snapshot.evidence_snapshot_hash
        or provenance.get("evidence_db_sha256") != snapshot.evidence_db_sha256
    ):
        raise ValueError("FORMALIZATION_SNAPSHOT_EVIDENCE_MISMATCH")
    selected = _selected_evidence(
        evidence_db,
        snapshot.source_bindings,
        evidence_snapshot_hash=snapshot.evidence_snapshot_hash,
        evidence_db_sha256=snapshot.evidence_db_sha256,
    )
    if selected != snapshot.selected_evidence:
        raise ValueError("FORMALIZATION_SNAPSHOT_EVIDENCE_MISMATCH")
    bundle: dict[str, object] = {
        "snapshot_hash": snapshot.evidence_snapshot_hash,
        "snapshot_provenance": provenance,
        "query": {
            "primary": snapshot.review_scope.question,
            "terms": [],
            "attempted_terms": [],
        },
        "hits": [
            {"citation": _citation(item.binding), "text": item.text}
            for item in snapshot.selected_evidence
        ],
    }
    request = build_review_run_request(
        bundle,
        calculations=calculations,
        rules=rules,
        approved_rule_result_ids=approved_rule_result_ids,
    )
    inputs_value = request.get("inputs")
    if not isinstance(inputs_value, dict):
        raise ValueError("formalization request inputs must be an object")
    inputs = dict(inputs_value)
    inputs.update(
        {
            "formalization_snapshot_id": snapshot.snapshot_id,
            "matter_id": snapshot.matter_id,
            "matter_revision": snapshot.matter_revision,
            "review_scope": _scope_document(snapshot),
        }
    )
    request["question"] = snapshot.review_scope.question
    request["inputs"] = inputs
    return prepare_review_request_document(
        workspace,
        request,
        additional_artifacts={
            "formalization-snapshot.json": formalization_snapshot_document(snapshot),
        },
    )


__all__ = ["formalize_snapshot"]
