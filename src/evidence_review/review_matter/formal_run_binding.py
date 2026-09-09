"""Append-only exact lineage from a Matter snapshot to a finalized Formal Run."""

from __future__ import annotations

import hashlib
import re
import sqlite3
from dataclasses import dataclass
from pathlib import Path

from evidence_review.abstention.finalizer import review_packet_document, verify_finalized_run
from evidence_review.canonical_json import dump_bytes
from evidence_review.contracts.identifiers import validate_identifier
from evidence_review.contracts.run_context import compute_run_id_from_request
from evidence_review.contracts.validation import expect_sha256
from evidence_review.filesystem_trust import (
    verified_regular_directory,
    verified_regular_file_below,
)
from evidence_review.llm_layer.track_a import build_track_a_bundle, track_a_bundle_document
from evidence_review.review_matter.snapshot import load_formalization_snapshot
from evidence_review.review_matter.store import MatterStore
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
        matter_id=checked_matter_id,
        snapshot_id=checked_snapshot_id,
        matter_revision=snapshot.matter_revision,
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
    matter_id: str,
    snapshot_id: str,
    matter_revision: int,
) -> None:
    """Authenticate one finalized Formal Run and its exact Matter request lineage."""
    try:
        workspace = verified_regular_directory(workspace_root, field="formal run workspace")
        runs = verified_regular_directory(workspace / "runs", field="formal run runs")
        run_directory = verified_regular_directory(
            runs / run_id,
            field="formal run directory",
        )
        packet_path = verified_regular_file_below(
            run_directory,
            ("final-review-packet.json",),
            field="formal run packet",
        )
        request_path = verified_regular_file_below(
            run_directory,
            ("review-request.json",),
            field="formal run request",
        )
        bundle_path = verified_regular_file_below(
            run_directory,
            ("track-a-bundle.json",),
            field="formal run Track A bundle",
        )
        before = tuple(path.read_bytes() for path in (packet_path, request_path, bundle_path))
        packet = verify_finalized_run(run_directory)
        after = tuple(path.read_bytes() for path in (packet_path, request_path, bundle_path))
        if before != after:
            raise ValueError("formal run artifacts changed during verification")
        (
            question,
            inputs,
            evidence,
            calculations,
            rules,
            approved,
            _confidence,
            normalized_request,
        ) = _decode_request(request_path)
        expected_bundle = track_a_bundle_document(
            build_track_a_bundle(
                run_id=run_id,
                question=question,
                inputs=inputs,
                evidence=evidence,
                rules=rules,
                calculations=calculations,
                approved_rule_result_ids=approved,
            )
        )
        if (
            before[0] != dump_bytes(review_packet_document(packet))
            or before[1] != dump_bytes(normalized_request)
            or before[2] != dump_bytes(expected_bundle)
            or compute_run_id_from_request(normalized_request) != run_id
            or packet.run_id != run_id
            or packet_path.read_bytes() != before[0]
            or hashlib.sha256(before[0]).hexdigest() != packet_sha256
        ):
            raise ValueError("formal run identity does not match finalized artifacts")
        if (
            inputs.get("formalization_snapshot_id") != snapshot_id
            or inputs.get("matter_id") != matter_id
            or inputs.get("matter_revision") != matter_revision
        ):
            raise ValueError("formal run request does not match Matter snapshot")
    except (FileNotFoundError, OSError, TypeError, ValueError) as error:
        raise ValueError("FORMAL_RUN_BINDING_RUN_INVALID") from error


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


__all__ = ["FormalRunBinding", "bind_formal_run", "list_formal_runs"]
