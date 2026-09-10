"""Append-only exact lineage from a Matter snapshot to a finalized Formal Run."""

from __future__ import annotations

import hashlib
import re
import sqlite3
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from evidence_review.abstention.finalizer import review_packet_document, verify_finalized_run
from evidence_review.canonical_json import dump_bytes
from evidence_review.contracts.identifiers import validate_identifier
from evidence_review.contracts.review import ReviewPacket
from evidence_review.contracts.run_context import compute_run_id_from_request
from evidence_review.contracts.validation import expect_int, expect_mapping, expect_sha256
from evidence_review.filesystem_trust import (
    verified_regular_directory,
    verified_regular_file_below,
)
from evidence_review.llm_layer.track_a import build_track_a_bundle, track_a_bundle_document
from evidence_review.review_matter.formalization import (
    _request_document,
    _validated_evidence_provenance,
)
from evidence_review.review_matter.scope import review_scope_document
from evidence_review.review_matter.snapshot import (
    FormalizationSnapshot,
    load_formalization_snapshot,
)
from evidence_review.review_matter.store import MatterStore, MatterStoreError
from evidence_review.review_run import _decode_request

_RUN_ID = re.compile(r"^RUN-[0-9A-F]{20}$")


@dataclass(frozen=True, slots=True)
class FormalRunBinding:
    """One immutable Matter revision, snapshot, RUN, and packet-hash association."""

    matter_id: str
    matter_revision: int
    snapshot_id: str
    run_id: str
    packet_sha256: str


def _binding(
    store: MatterStore,
    workspace_root: Path,
    matter_id: object,
    snapshot_id: object,
    run_id: object,
    packet_sha256: object,
) -> FormalRunBinding:
    checked_matter_id = validate_identifier(matter_id, "matter_id")
    checked_snapshot_id = validate_identifier(snapshot_id, "snapshot_id")
    checked_run_id = validate_identifier(run_id, "run_id")
    if not _RUN_ID.fullmatch(checked_run_id):
        raise ValueError("run_id must be a Formal Run identifier")
    checked_packet_sha256 = expect_sha256(packet_sha256, "packet_sha256")
    store.load(checked_matter_id)
    snapshot = load_formalization_snapshot(store, checked_snapshot_id)
    if snapshot.matter_id != checked_matter_id:
        raise ValueError("FORMAL_RUN_BINDING_MATTER_MISMATCH")
    _verify_formal_run(
        workspace_root,
        run_id=checked_run_id,
        packet_sha256=checked_packet_sha256,
        snapshot=snapshot,
    )
    return FormalRunBinding(
        matter_id=checked_matter_id,
        matter_revision=snapshot.matter_revision,
        snapshot_id=checked_snapshot_id,
        run_id=checked_run_id,
        packet_sha256=checked_packet_sha256,
    )


def _verify_formal_run(
    workspace_root: Path,
    *,
    run_id: str,
    packet_sha256: str,
    snapshot: FormalizationSnapshot,
) -> None:
    """Authenticate one finalized Formal Run and its exact Matter request lineage."""
    try:
        verify_formal_run_authority(
            workspace_root,
            run_id=run_id,
            packet_sha256=packet_sha256,
            expected_snapshot=snapshot,
        )
    except ValueError as error:
        raise ValueError("FORMAL_RUN_BINDING_RUN_INVALID") from error


def _request_snapshot(
    workspace: Path,
    normalized_request: Mapping[str, object],
    *,
    run_id: str,
    packet_sha256: str,
    require_matter_lineage: bool,
    require_persisted_binding: bool,
) -> FormalizationSnapshot | None:
    inputs = expect_mapping(normalized_request.get("inputs"), "review request inputs")
    lineage_fields = {
        "formalization_snapshot_id",
        "matter_id",
        "matter_revision",
    }
    present_fields = lineage_fields.intersection(inputs)
    if not present_fields:
        if require_matter_lineage:
            raise ValueError("FORMAL_RUN_MATTER_LINEAGE_MISSING")
        return None
    if present_fields != lineage_fields:
        raise ValueError("FORMAL_RUN_MATTER_LINEAGE_INCOMPLETE")

    matter_id = validate_identifier(inputs["matter_id"], "matter_id")
    snapshot_id = validate_identifier(
        inputs["formalization_snapshot_id"], "formalization_snapshot_id"
    )
    matter_revision = expect_int(inputs["matter_revision"], "matter_revision")
    if matter_revision < 1:
        raise ValueError("FORMAL_RUN_MATTER_REVISION_INVALID")
    matter_path = verified_regular_file_below(
        workspace,
        ("matter.sqlite",),
        field="formal run Matter store",
    )
    with MatterStore(matter_path) as store:
        matter = store.load(matter_id)
        snapshot = load_formalization_snapshot(store, snapshot_id)
        if require_persisted_binding:
            binding = store.connection.execute(
                """
                SELECT matter_id, matter_revision, snapshot_id, run_id, packet_sha256
                FROM formal_run_bindings
                WHERE matter_id = ? AND snapshot_id = ? AND run_id = ?
                      AND packet_sha256 = ?
                """,
                (matter_id, snapshot_id, run_id, packet_sha256),
            ).fetchone()
            if binding is None or (
                str(binding["matter_id"]),
                int(binding["matter_revision"]),
                str(binding["snapshot_id"]),
                str(binding["run_id"]),
                str(binding["packet_sha256"]),
            ) != (
                matter_id,
                matter_revision,
                snapshot_id,
                run_id,
                packet_sha256,
            ):
                raise ValueError("FORMAL_RUN_MATTER_BINDING_MISSING")
    if (
        matter.matter_id,
        snapshot.matter_id,
        snapshot.matter_revision,
    ) != (matter_id, matter_id, matter_revision) or matter.revision < matter_revision:
        raise ValueError("FORMAL_RUN_MATTER_LINEAGE_MISMATCH")
    return snapshot


def verify_formal_run_authority(
    workspace_root: Path,
    *,
    run_id: str,
    packet_sha256: str,
    expected_snapshot: FormalizationSnapshot | None = None,
    require_matter_lineage: bool = False,
    require_persisted_binding: bool = False,
) -> tuple[Path, ReviewPacket, dict[str, object]]:
    """Verify final artifacts and any persisted Matter lineage they declare.

    Direct finalized runs without Matter identity remain valid for the lower-level
    current-review selector. If a request declares Matter lineage, every field is
    loaded from the workspace Matter store and the complete request is rebuilt from
    that persisted snapshot; copied request fields are never used as authority.
    """
    try:
        checked_run_id = validate_identifier(run_id, "run_id")
        if not _RUN_ID.fullmatch(checked_run_id):
            raise ValueError("run_id must be a Formal Run identifier")
        checked_packet_sha256 = expect_sha256(packet_sha256, "packet_sha256")
        workspace = verified_regular_directory(workspace_root, field="formal run workspace")
        runs = verified_regular_directory(workspace / "runs", field="formal run runs")
        run_directory = verified_regular_directory(
            runs / checked_run_id,
            field="formal run directory",
        )
        packet_path = verified_regular_file_below(
            run_directory,
            ("final-review-packet.json",),
            field="formal run packet",
        )
        packet, normalized_request = verify_finalized_run_artifacts(run_directory)
        snapshot = expected_snapshot or _request_snapshot(
            workspace,
            normalized_request,
            run_id=checked_run_id,
            packet_sha256=checked_packet_sha256,
            require_matter_lineage=require_matter_lineage,
            require_persisted_binding=require_persisted_binding,
        )
        expected_request = (
            None if snapshot is None else _expected_formal_request(workspace, snapshot)
        )
        packet_bytes = packet_path.read_bytes()
        if (
            compute_run_id_from_request(normalized_request) != checked_run_id
            or packet.run_id != checked_run_id
            or packet_bytes != dump_bytes(review_packet_document(packet))
            or hashlib.sha256(packet_bytes).hexdigest() != checked_packet_sha256
            or (
                expected_request is not None
                and dump_bytes(normalized_request) != dump_bytes(expected_request)
            )
        ):
            raise ValueError("formal run identity does not match finalized artifacts")
        return run_directory, packet, normalized_request
    except (
        FileNotFoundError,
        OSError,
        TypeError,
        ValueError,
        MatterStoreError,
        sqlite3.Error,
    ) as error:
        raise ValueError("FORMAL_RUN_AUTHORITY_INVALID") from error


def verify_finalized_run_artifacts(
    run_directory: Path,
) -> tuple[ReviewPacket, dict[str, object]]:
    """Verify the canonical request-derived cross-artifact run authority."""
    try:
        trusted_run = verified_regular_directory(
            run_directory, field="finalized run directory"
        )
        paths = tuple(
            verified_regular_file_below(
                trusted_run,
                (name,),
                field=f"finalized run {name}",
            )
            for name in (
                "run-manifest.json",
                "review-request.json",
                "track-a-bundle.json",
                "track-a-output.json",
                "track-b-output.json",
                "confidence-input.json",
                "final-review-packet.json",
            )
        )
        before = tuple(path.read_bytes() for path in paths)
        packet = verify_finalized_run(trusted_run)
        normalized_request = verify_finalized_run_request(trusted_run)
        (
            question,
            inputs,
            evidence,
            calculations,
            rules,
            approved,
            confidence,
            _request,
        ) = _decode_request(paths[1])
        expected_bundle = track_a_bundle_document(
            build_track_a_bundle(
                run_id=trusted_run.name,
                question=question,
                inputs=inputs,
                evidence=evidence,
                rules=rules,
                calculations=calculations,
                approved_rule_result_ids=approved,
            )
        )
        after = tuple(path.read_bytes() for path in paths)
        if (
            before != after
            or paths[1].read_bytes() != dump_bytes(normalized_request)
            or paths[2].read_bytes() != dump_bytes(expected_bundle)
            or paths[5].read_bytes() != dump_bytes(confidence)
            or paths[6].read_bytes() != dump_bytes(review_packet_document(packet))
            or compute_run_id_from_request(normalized_request) != trusted_run.name
            or packet.run_id != trusted_run.name
        ):
            raise ValueError("finalized run cross-artifact identity changed")
        return packet, normalized_request
    except (FileNotFoundError, OSError, TypeError, ValueError) as error:
        raise ValueError("FINALIZED_RUN_CROSS_ARTIFACT_INVALID") from error


def _expected_formal_request(
    workspace: Path, snapshot: FormalizationSnapshot
) -> dict[str, object]:
    evidence_db = verified_regular_file_below(
        workspace,
        ("evidence", "evidence.sqlite"),
        field="formal run evidence database",
    )
    provenance = _validated_evidence_provenance(evidence_db, snapshot)
    return _request_document(
        snapshot,
        provenance,
        review_scope_document(snapshot.review_scope),
    )


def verify_finalized_run_request(run_directory: Path) -> dict[str, object]:
    """Verify one run-local request's canonical bytes and derived RUN identity."""
    try:
        trusted_run = verified_regular_directory(
            run_directory, field="finalized run directory"
        )
        request_path = verified_regular_file_below(
            trusted_run,
            ("review-request.json",),
            field="finalized run request",
        )
        before = request_path.read_bytes()
        normalized_request = _decode_request(request_path)[-1]
        after = request_path.read_bytes()
        if (
            before != after
            or before != dump_bytes(normalized_request)
            or compute_run_id_from_request(normalized_request) != trusted_run.name
        ):
            raise ValueError("finalized run request identity changed")
        return normalized_request
    except (FileNotFoundError, OSError, TypeError, ValueError) as error:
        raise ValueError("FINALIZED_RUN_REQUEST_INVALID") from error


def bind_formal_run(
    store: MatterStore,
    matter_id: str,
    snapshot_id: str,
    run_id: str,
    packet_sha256: str,
    *,
    workspace_root: Path,
) -> FormalRunBinding:
    """Append one exact finalized-run lineage record without any replacement path."""
    binding = _binding(
        store, workspace_root, matter_id, snapshot_id, run_id, packet_sha256
    )
    with store.transaction():
        binding = _binding(
            store,
            workspace_root,
            binding.matter_id,
            binding.snapshot_id,
            binding.run_id,
            binding.packet_sha256,
        )
        try:
            store.connection.execute(
                """
                INSERT INTO formal_run_bindings(
                    matter_id, matter_revision, snapshot_id, run_id, packet_sha256
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (
                    binding.matter_id,
                    binding.matter_revision,
                    binding.snapshot_id,
                    binding.run_id,
                    binding.packet_sha256,
                ),
            )
        except sqlite3.IntegrityError as error:
            raise ValueError("FORMAL_RUN_BINDING_ALREADY_EXISTS") from error
    return binding


def list_formal_runs(
    store: MatterStore,
    matter_id: str,
    *,
    workspace_root: Path,
) -> tuple[FormalRunBinding, ...]:
    """Return exact validated lineage in deterministic Matter-revision order."""
    checked_matter_id = validate_identifier(matter_id, "matter_id")
    store.load(checked_matter_id)
    rows = store.connection.execute(
        """
        SELECT matter_id, matter_revision, snapshot_id, run_id, packet_sha256
        FROM formal_run_bindings
        WHERE matter_id = ?
        ORDER BY matter_revision, snapshot_id, run_id
        """,
        (checked_matter_id,),
    ).fetchall()
    bindings = tuple(
        _binding(
            store,
            workspace_root,
            row["matter_id"],
            row["snapshot_id"],
            row["run_id"],
            row["packet_sha256"],
        )
        for row in rows
    )
    for row, binding in zip(rows, bindings, strict=True):
        if int(row["matter_revision"]) != binding.matter_revision:
            raise ValueError("FORMAL_RUN_BINDING_REVISION_MISMATCH")
    return bindings


__all__ = [
    "FormalRunBinding",
    "bind_formal_run",
    "list_formal_runs",
    "verify_formal_run_authority",
    "verify_finalized_run_artifacts",
    "verify_finalized_run_request",
]
