"""Read-only references for finalized Formal Runs that predate Review Matters."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from evidence_review.abstention.finalizer import review_packet_document
from evidence_review.canonical_json import dump_bytes
from evidence_review.filesystem_trust import (
    verified_regular_directory,
    verified_regular_file_below,
)
from evidence_review.review_matter.formal_run_binding import verify_formal_run_authority
from evidence_review.review_packet.decision_record import validate_human_decision_envelope

_DECISION_FIELDS = frozenset(
    {"run_id", "reviewer_id", "reviewed_at", "packet_hash", "decision", "notes"}
)
_MATTER_LINEAGE_FIELDS = frozenset(
    {"matter_id", "matter_revision", "formalization_snapshot_id"}
)


@dataclass(frozen=True, slots=True)
class LegacyHumanDecisionReference:
    """Immutable identity of one canonical legacy human decision artifact."""

    filename: str
    sha256: str


@dataclass(frozen=True, slots=True)
class LegacyFormalReviewReference:
    """Verified legacy RUN identities without inferred Review Matter history."""

    run_id: str
    packet_sha256: str
    human_decisions: tuple[LegacyHumanDecisionReference, ...]
    matter_revision: None
    matter_issue_ids: tuple[()]
    source_impact_history: tuple[()]
    compatibility_status: str


def _decision_references(
    run_directory: Path,
    *,
    run_id: str,
    packet_sha256: str,
) -> tuple[LegacyHumanDecisionReference, ...]:
    directory = run_directory / "human-decisions"
    try:
        directory = verified_regular_directory(directory, field="legacy human decisions")
    except FileNotFoundError:
        return ()

    references: list[LegacyHumanDecisionReference] = []
    for candidate in sorted(directory.iterdir(), key=lambda path: path.name):
        if candidate.suffix != ".json":
            raise ValueError("legacy human decision filename is invalid")
        decision_path = verified_regular_file_below(
            directory,
            (candidate.name,),
            field="legacy human decision",
        )
        raw = decision_path.read_bytes()
        document = json.loads(raw.decode("utf-8"))
        if not isinstance(document, Mapping) or set(document) != _DECISION_FIELDS:
            raise ValueError("legacy human decision document is invalid")
        if raw != dump_bytes(document):
            raise ValueError("legacy human decision is not canonical")
        envelope = validate_human_decision_envelope(
            {field: document[field] for field in _DECISION_FIELDS - {"run_id"}}
        )
        if document != {"run_id": run_id, **envelope}:
            raise ValueError("legacy human decision identity is invalid")
        if envelope["packet_hash"] != packet_sha256:
            raise ValueError("legacy human decision packet hash is invalid")
        references.append(
            LegacyHumanDecisionReference(
                filename=decision_path.name,
                sha256=hashlib.sha256(raw).hexdigest(),
            )
        )
    return tuple(references)


def legacy_reference_from_run(run_directory: Path) -> LegacyFormalReviewReference:
    """Return a strict immutable reference to one verified pre-Matter Formal Run."""
    try:
        trusted_run = verified_regular_directory(
            run_directory,
            field="legacy formal run directory",
        )
        packet_path = verified_regular_file_below(
            trusted_run,
            ("final-review-packet.json",),
            field="legacy formal review packet",
        )
        packet_bytes = packet_path.read_bytes()
        packet_sha256 = hashlib.sha256(packet_bytes).hexdigest()
        workspace_root = trusted_run.parents[1]
        verified_run, packet, normalized_request = verify_formal_run_authority(
            workspace_root,
            run_id=trusted_run.name,
            packet_sha256=packet_sha256,
        )
        if verified_run != trusted_run:
            raise ValueError("legacy formal run directory is not canonical")
        inputs = normalized_request.get("inputs")
        if not isinstance(inputs, Mapping) or _MATTER_LINEAGE_FIELDS.intersection(inputs):
            raise ValueError("legacy formal review declares Matter lineage")
        if packet_bytes != dump_bytes(review_packet_document(packet)):
            raise ValueError("legacy formal review packet is not canonical")
        decisions = _decision_references(
            verified_run,
            run_id=verified_run.name,
            packet_sha256=packet_sha256,
        )
    except (
        FileNotFoundError,
        OSError,
        UnicodeError,
        json.JSONDecodeError,
        TypeError,
        ValueError,
        IndexError,
    ) as error:
        raise ValueError("LEGACY_FORMAL_RUN_INVALID") from error
    return LegacyFormalReviewReference(
        run_id=trusted_run.name,
        packet_sha256=packet_sha256,
        human_decisions=decisions,
        matter_revision=None,
        matter_issue_ids=(),
        source_impact_history=(),
        compatibility_status="LEGACY_FORMAL_RUN",
    )


__all__ = [
    "LegacyFormalReviewReference",
    "LegacyHumanDecisionReference",
    "legacy_reference_from_run",
]
