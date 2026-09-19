"""Deterministic report projections for an exact historical cutoff."""
from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path

from evidence_review.filesystem_trust import (
    verified_regular_directory,
    verified_regular_file_below,
)
from evidence_review.review_packet.decision_record import (
    load_latest_valid_human_decision,
)

_SHA256 = re.compile(r"^[0-9a-f]{64}$")


def _cutoff(value: datetime | str) -> datetime:
    parsed = value if isinstance(value, datetime) else datetime.fromisoformat(value)
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("as_of must include a timezone")
    return parsed.astimezone(UTC)


def build_report_as_of(
    run_directory: Path,
    *,
    as_of: datetime | str,
    expected_packet_sha256: str | None = None,
) -> dict[str, object]:
    """Build a packet-bound machine + human decision projection.

    The packet bytes are read and hashed on every call.  Human decisions are
    loaded through the append-only decision-record trust boundary with the
    same cutoff, so a later decision cannot retroactively change an older
    report.  No source artifact or decision record is modified.
    """
    trusted_run = verified_regular_directory(run_directory, field="report run")
    packet_path = verified_regular_file_below(
        trusted_run,
        ("final-review-packet.json",),
        field="report final packet",
    )
    packet_bytes = packet_path.read_bytes()
    packet_sha256 = hashlib.sha256(packet_bytes).hexdigest()
    if expected_packet_sha256 is not None:
        if not _SHA256.fullmatch(expected_packet_sha256):
            raise ValueError("expected_packet_sha256 must be a lowercase SHA-256 digest")
        if packet_sha256 != expected_packet_sha256:
            raise ValueError("final packet hash does not match expected_packet_sha256")
    try:
        packet = json.loads(packet_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("final review packet is not valid JSON") from error
    if not isinstance(packet, Mapping):
        raise ValueError("final review packet must be an object")
    packet_run_id = packet.get("run_id")
    if packet_run_id != trusted_run.name:
        raise ValueError("final review packet run_id does not match run directory")
    machine_status = packet.get("status")
    if not isinstance(machine_status, str) or not machine_status:
        raise ValueError("final review packet status is missing")

    cutoff = _cutoff(as_of)
    decision = load_latest_valid_human_decision(
        trusted_run,
        packet_sha256,
        as_of=cutoff,
    )
    decision_document: dict[str, str] | None = None
    if decision is not None:
        decision_document = {
            "reviewer_id": decision.reviewer_id,
            "reviewed_at": decision.reviewed_at,
            "packet_sha256": decision.packet_hash,
            "decision": decision.decision,
            "notes": decision.notes,
        }
    return {
        "format": "evidence-review/report-as-of",
        "version": 1,
        "as_of": cutoff.isoformat(),
        "run_id": trusted_run.name,
        "packet_sha256": packet_sha256,
        "machine_status": machine_status,
        "human_decision": decision_document,
        "decision_source": "append-only-human-decision-record",
    }


__all__ = ["build_report_as_of"]
