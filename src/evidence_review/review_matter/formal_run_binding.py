"""Append-only exact lineage from a Matter snapshot to a finalized Formal Run."""

from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass

from evidence_review.contracts.identifiers import validate_identifier
from evidence_review.contracts.validation import expect_sha256
from evidence_review.review_matter.snapshot import load_formalization_snapshot
from evidence_review.review_matter.store import MatterStore

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
    return FormalRunBinding(
        matter_id=checked_matter_id,
        matter_revision=snapshot.matter_revision,
        snapshot_id=checked_snapshot_id,
        run_id=checked_run_id,
        packet_sha256=checked_packet_sha256,
    )


def bind_formal_run(
    store: MatterStore,
    matter_id: str,
    snapshot_id: str,
    run_id: str,
    packet_sha256: str,
) -> FormalRunBinding:
    """Append one exact finalized-run lineage record without any replacement path."""
    binding = _binding(store, matter_id, snapshot_id, run_id, packet_sha256)
    with store.transaction():
        binding = _binding(
            store,
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


def list_formal_runs(store: MatterStore, matter_id: str) -> tuple[FormalRunBinding, ...]:
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
