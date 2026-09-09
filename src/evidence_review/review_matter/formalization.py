"""Adapt immutable ReviewMatter snapshots into strict Formal Review requests."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from evidence_review.canonical_json import dump_bytes
from evidence_review.confidence.policy import FACTOR_WEIGHTS
from evidence_review.contracts.run_context import compute_run_id_from_request
from evidence_review.evidence.snapshot import finalized_evidence_provenance
from evidence_review.filesystem_trust import verified_regular_file_below
from evidence_review.llm_layer.track_a import (
    build_track_a_bundle,
    track_a_bundle_document,
)
from evidence_review.review_matter.scope import (
    decode_review_scope,
    review_scope_document,
)
from evidence_review.review_matter.snapshot import (
    FormalizationSnapshot,
    _database_selection,
    formalization_snapshot_document,
    load_formalization_snapshot,
)
from evidence_review.review_matter.store import MatterStore
from evidence_review.review_question import _prepare_from_document
from evidence_review.review_run import (
    PreparedReviewRun,
    _decode_confidence_input,
    _decode_request,
)


@dataclass(frozen=True, slots=True)
class FormalizedReviewRun:
    """One strict Formal Review run prepared from a formalization snapshot."""

    run_id: str
    status: str
    prepared: PreparedReviewRun | None


def _mapping_documents(values: Sequence[object], field: str) -> list[dict[str, object]]:
    documents: list[dict[str, object]] = []
    for index, value in enumerate(values):
        if not isinstance(value, Mapping) or not all(isinstance(key, str) for key in value):
            raise ValueError(f"{field}[{index}] must be an object")
        documents.append(dict(value))
    return documents


def _strict_approved_rule_result_ids(values: Sequence[str]) -> list[str]:
    """Apply the review-run decoder's validation and canonical sort order."""
    approved: list[str] = []
    for index, value in enumerate(values):
        if not isinstance(value, str) or not value:
            raise ValueError(
                f"approved_rule_result_ids[{index}] must be a non-empty string"
            )
        approved.append(value)
    if len(approved) != len(set(approved)):
        raise ValueError("approved_rule_result_ids must be unique")
    return sorted(approved)


def _matter_store(workspace: Path) -> MatterStore:
    path = verified_regular_file_below(
        workspace,
        ("matter.sqlite",),
        field="Matter store",
    )
    return MatterStore(path)


def _evidence_database(workspace: Path) -> Path:
    return verified_regular_file_below(
        workspace,
        ("evidence", "evidence.sqlite"),
        field="evidence database",
    )


def _validated_evidence_provenance(
    evidence_db: Path, snapshot: FormalizationSnapshot
) -> dict[str, object]:
    provenance = finalized_evidence_provenance(evidence_db)
    if (
        provenance.get("evidence_snapshot_hash"),
        provenance.get("evidence_db_sha256"),
        provenance.get("schema_version"),
    ) != (
        snapshot.evidence_snapshot_hash,
        snapshot.evidence_db_sha256,
        snapshot.evidence_schema_version,
    ):
        raise ValueError("FORMALIZATION_EVIDENCE_PROVENANCE_MISMATCH")
    return provenance


def _validated_scope_payload(value: object) -> dict[str, object]:
    try:
        decoded_scope = decode_review_scope(value)
        canonical_scope = review_scope_document(decoded_scope)
    except (AttributeError, KeyError, TypeError, ValueError) as error:
        raise ValueError("FORMALIZATION_REVIEW_SCOPE_INVALID") from error
    if dump_bytes(canonical_scope) != dump_bytes(value):
        raise ValueError("FORMALIZATION_REVIEW_SCOPE_CANONICAL_MISMATCH")
    return canonical_scope


def _validated_scope_document(snapshot: FormalizationSnapshot) -> dict[str, object]:
    try:
        snapshot_scope = review_scope_document(snapshot.review_scope)
    except (AttributeError, KeyError, TypeError, ValueError) as error:
        raise ValueError("FORMALIZATION_REVIEW_SCOPE_INVALID") from error
    return _validated_scope_payload(snapshot_scope)


def _validate_persisted_snapshot(
    store: MatterStore, workspace: Path, snapshot: FormalizationSnapshot
) -> tuple[FormalizationSnapshot, Path, dict[str, object], dict[str, object]]:
    supplied_scope = _validated_scope_document(snapshot)
    persisted = load_formalization_snapshot(store, snapshot.snapshot_id)
    persisted_scope = _validated_scope_document(persisted)
    if dump_bytes(persisted_scope) != dump_bytes(supplied_scope):
        raise ValueError("FORMALIZATION_REVIEW_SCOPE_CANONICAL_MISMATCH")
    if dump_bytes(formalization_snapshot_document(persisted)) != dump_bytes(
        formalization_snapshot_document(snapshot)
    ):
        raise ValueError("FORMALIZATION_SNAPSHOT_PERSISTED_BYTES_MISMATCH")

    matter = store.load(persisted.matter_id)
    if matter.revision != persisted.matter_revision:
        raise ValueError("MATTER_CHANGED_DURING_FORMALIZATION")

    evidence_db = _evidence_database(workspace)
    _validated_evidence_provenance(evidence_db, persisted)

    bindings = {binding.binding_id: binding for binding in matter.source_bindings}
    for selected in persisted.selected_evidence:
        binding = bindings.get(selected.binding_id)
        if binding is None or _database_selection(evidence_db, binding) != selected:
            raise ValueError("FORMALIZATION_SELECTED_EVIDENCE_IDENTITY_MISMATCH")
    provenance = _validated_evidence_provenance(evidence_db, persisted)
    return persisted, evidence_db, provenance, persisted_scope


def _request_document(
    snapshot: FormalizationSnapshot,
    provenance: Mapping[str, object],
    scope_document: Mapping[str, object],
    *,
    calculations: Sequence[object],
    rules: Sequence[object],
    approved_rule_result_ids: Sequence[str],
) -> dict[str, object]:
    return {
        "format": "evidence-review/review-run-request",
        "version": 1,
        "question": scope_document["question"],
        "inputs": {
            "snapshot_hash": snapshot.evidence_snapshot_hash,
            "evidence_snapshot_provenance": dict(provenance),
            "formalization_snapshot_id": snapshot.snapshot_id,
            "matter_id": snapshot.matter_id,
            "matter_revision": snapshot.matter_revision,
            "review_scope": dict(scope_document),
        },
        "evidence": [
            {
                "citation": {
                    "citation_id": selected.citation.citation_id,
                    "document_id": selected.citation.document_id,
                    "revision_id": selected.citation.revision_id,
                    "page_number": selected.citation.page_number,
                    "evidence_id": selected.citation.evidence_id,
                    "bbox": [
                        selected.citation.bbox.left,
                        selected.citation.bbox.bottom,
                        selected.citation.bbox.right,
                        selected.citation.bbox.top,
                    ],
                    "source_hash": selected.citation.source_hash,
                },
                "text": selected.text,
            }
            for selected in snapshot.selected_evidence
        ],
        "calculations": _mapping_documents(calculations, "calculations"),
        "rules": _mapping_documents(rules, "rules"),
        "approved_rule_result_ids": _strict_approved_rule_result_ids(
            approved_rule_result_ids
        ),
        "confidence_input": {
            "factors": {
                name: {"value": "1.0", "source": "formalization:snapshot"}
                for name in FACTOR_WEIGHTS
            }
        },
    }


def _validate_prepared_bundle_scope(
    bundle_path: Path, expected_scope: Mapping[str, object]
) -> None:
    try:
        payload = json.loads(bundle_path.read_text(encoding="utf-8"))
        if not isinstance(payload, Mapping):
            raise ValueError("track-a-bundle must be an object")
        inputs = payload["inputs"]
        if not isinstance(inputs, Mapping):
            raise ValueError("track-a-bundle inputs must be an object")
        scope = _validated_scope_payload(inputs["review_scope"])
    except (KeyError, OSError, UnicodeError, json.JSONDecodeError, TypeError, ValueError) as error:
        raise ValueError("FORMALIZATION_REVIEW_SCOPE_INVALID") from error
    if dump_bytes(scope) != dump_bytes(expected_scope):
        raise ValueError("FORMALIZATION_REVIEW_SCOPE_MISMATCH")


def _validate_prepared_artifacts(
    request_path: Path,
    bundle_path: Path,
    confidence_path: Path,
    expected_document: Mapping[str, object],
    expected_scope: Mapping[str, object],
) -> None:
    try:
        (
            question,
            inputs,
            evidence,
            calculations,
            rules,
            approved,
            _request_confidence,
            normalized_request,
        ) = _decode_request(request_path)
    except (OSError, TypeError, ValueError) as error:
        raise ValueError("FORMALIZATION_PREPARED_REQUEST_INVALID") from error

    try:
        request_bytes = request_path.read_bytes()
        normalized_request_bytes = dump_bytes(normalized_request)
        expected_request_bytes = dump_bytes(expected_document)
    except (OSError, TypeError, ValueError) as error:
        raise ValueError("FORMALIZATION_PREPARED_REQUEST_INVALID") from error
    if (
        request_bytes != normalized_request_bytes
        or normalized_request_bytes != expected_request_bytes
    ):
        raise ValueError("FORMALIZATION_PREPARED_REQUEST_MISMATCH")

    try:
        confidence_payload = json.loads(confidence_path.read_text(encoding="utf-8"))
        normalized_confidence = _decode_confidence_input(confidence_payload)
        confidence_bytes = confidence_path.read_bytes()
        expected_confidence = expected_document["confidence_input"]
        normalized_confidence_bytes = dump_bytes(normalized_confidence)
        expected_confidence_bytes = dump_bytes(expected_confidence)
    except (KeyError, OSError, TypeError, ValueError, json.JSONDecodeError) as error:
        raise ValueError("FORMALIZATION_PREPARED_CONFIDENCE_INVALID") from error
    if (
        confidence_bytes != normalized_confidence_bytes
        or normalized_confidence_bytes != expected_confidence_bytes
    ):
        raise ValueError("FORMALIZATION_PREPARED_CONFIDENCE_MISMATCH")

    _validate_prepared_bundle_scope(bundle_path, expected_scope)

    try:
        rebuilt_bundle = build_track_a_bundle(
            run_id=compute_run_id_from_request(normalized_request),
            question=question,
            inputs=inputs,
            evidence=evidence,
            rules=rules,
            calculations=calculations,
            approved_rule_result_ids=approved,
        )
        bundle_bytes = bundle_path.read_bytes()
        rebuilt_bundle_bytes = dump_bytes(track_a_bundle_document(rebuilt_bundle))
    except (OSError, TypeError, ValueError) as error:
        raise ValueError("FORMALIZATION_PREPARED_TRACK_A_INVALID") from error
    if bundle_bytes != rebuilt_bundle_bytes:
        raise ValueError("FORMALIZATION_PREPARED_TRACK_A_MISMATCH")


def _prepare_or_resume(
    workspace: Path,
    document: dict[str, object],
    *,
    store: MatterStore,
    snapshot: FormalizationSnapshot,
    evidence_db: Path,
    scope_document: Mapping[str, object],
) -> FormalizedReviewRun:
    run_id = compute_run_id_from_request(document)
    try:
        run_directory = verified_regular_file_below(
            workspace,
            ("runs", run_id, "review-request.json"),
            field="prepared review request",
        )
    except FileNotFoundError:
        current = store.load(snapshot.matter_id)
        if current.revision != snapshot.matter_revision:
            raise ValueError("MATTER_CHANGED_DURING_FORMALIZATION") from None
        provenance = _validated_evidence_provenance(evidence_db, snapshot)
        inputs = document.get("inputs")
        if not isinstance(inputs, Mapping) or inputs.get(
            "evidence_snapshot_provenance"
        ) is None:
            raise ValueError("FORMALIZATION_EVIDENCE_PROVENANCE_MISMATCH") from None
        if dump_bytes(dict(inputs["evidence_snapshot_provenance"])) != dump_bytes(
            provenance
        ):
            raise ValueError("FORMALIZATION_EVIDENCE_PROVENANCE_MISMATCH") from None
        prepared = _prepare_from_document(workspace, document)
        return FormalizedReviewRun(
            run_id=prepared.run_id,
            status="WAITING_TRACK_A",
            prepared=prepared,
        )
    bundle_path: Path | None = None
    confidence_path: Path | None = None
    for name in ("track-a-bundle.json", "confidence-input.json"):
        artifact = verified_regular_file_below(
            workspace,
            ("runs", run_id, name),
            field=f"prepared review artifact {name}",
        )
        if name == "track-a-bundle.json":
            bundle_path = artifact
        else:
            confidence_path = artifact
    if bundle_path is None or confidence_path is None:
        raise ValueError("FORMALIZATION_PREPARED_ARTIFACT_INVALID")
    _validate_prepared_artifacts(
        run_directory,
        bundle_path,
        confidence_path,
        document,
        scope_document,
    )
    current = store.load(snapshot.matter_id)
    if current.revision != snapshot.matter_revision:
        raise ValueError("MATTER_CHANGED_DURING_FORMALIZATION")
    _validated_evidence_provenance(evidence_db, snapshot)
    return FormalizedReviewRun(run_id=run_id, status="WAITING_TRACK_A", prepared=None)


def formalize_snapshot(
    workspace: Path,
    snapshot: FormalizationSnapshot,
    *,
    calculations: Sequence[object] = (),
    rules: Sequence[object] = (),
    approved_rule_result_ids: Sequence[str] = (),
) -> FormalizedReviewRun:
    """Prepare one immutable Formal Review run from a persisted snapshot only."""
    if not isinstance(snapshot, FormalizationSnapshot):
        raise ValueError("FORMALIZATION_SNAPSHOT_REQUIRED")
    workspace_root = Path(workspace)
    with _matter_store(workspace_root) as store:
        persisted, evidence_db, provenance, scope_document = _validate_persisted_snapshot(
            store, workspace_root, snapshot
        )
        document = _request_document(
            persisted,
            provenance,
            scope_document,
            calculations=calculations,
            rules=rules,
            approved_rule_result_ids=approved_rule_result_ids,
        )
        with store.transaction():
            current = store.load(persisted.matter_id)
            if current.revision != persisted.matter_revision:
                raise ValueError("MATTER_CHANGED_DURING_FORMALIZATION")
            return _prepare_or_resume(
                workspace_root,
                document,
                store=store,
                snapshot=persisted,
                evidence_db=evidence_db,
                scope_document=scope_document,
            )


__all__ = ["FormalizedReviewRun", "formalize_snapshot"]
