"""Hash-reverified binding of confirmed drawing inputs to deterministic engines."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from ansim_review.contracts.attachments import ImmutableAttachment
from ansim_review.contracts.drawing import (
    ConfirmedInput,
    confirmed_input_document,
    decode_confirmed_input,
    decode_drawing_confirmation,
    geometry_document,
)
from ansim_review.parsing.drawing_case import case_artifact_path
from ansim_review.parsing.drawing_source import verify_immutable_attachment


@dataclass(frozen=True, slots=True)
class EngineInputValue:
    """One provenance-checked value ready for deterministic engine decoding."""

    value: str
    unit: str
    input_id: str


def _verify_confirmation(case_dir: Path, confirmed: ConfirmedInput) -> None:
    path = case_artifact_path(case_dir, confirmed.confirmation_record)
    payload_bytes = path.read_bytes()
    actual_hash = hashlib.sha256(payload_bytes).hexdigest()
    if actual_hash != confirmed.confirmation_sha256:
        raise ValueError("confirmation hash mismatch")
    try:
        payload = json.loads(payload_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("confirmation document is invalid JSON") from error
    confirmation = decode_drawing_confirmation(payload)
    if confirmation.candidate_id != confirmed.evidence_id:
        raise ValueError("confirmation candidate does not match confirmed evidence")
    if confirmation.source_sha256 != confirmed.source_sha256:
        raise ValueError("confirmation source does not match confirmed input")
    if confirmation.action != confirmed.candidate_status:
        raise ValueError("confirmation action does not match confirmed candidate status")
    if confirmation.confirmed_value is not None:
        if confirmation.confirmed_value != confirmed.value:
            raise ValueError("confirmation value does not match confirmed input")
        if confirmation.unit != confirmed.unit:
            raise ValueError("confirmation unit does not match confirmed input")
    if confirmation.geometry is not None:
        if geometry_document(confirmation.geometry) != geometry_document(
            confirmed.geometry
        ):
            raise ValueError("confirmation geometry does not match confirmed input")


def bind_confirmed_inputs(
    case_dir: Path,
    inputs: Sequence[ConfirmedInput],
    source_attachments: Mapping[str, ImmutableAttachment],
) -> dict[str, EngineInputValue]:
    """Reverify all provenance and return a stable field-keyed engine mapping."""
    bound: dict[str, EngineInputValue] = {}
    ordered = sorted(inputs, key=lambda item: (item.field, item.input_id))
    for item in ordered:
        confirmed = decode_confirmed_input(confirmed_input_document(item))
        attachment = source_attachments.get(confirmed.source_sha256)
        if attachment is None:
            raise ValueError("source attachment is not registered")
        if attachment.sha256 != confirmed.source_sha256:
            raise ValueError("source attachment hash identity mismatch")
        errors = verify_immutable_attachment(case_dir, attachment)
        if errors:
            raise ValueError(
                "immutable source verification failed: " + ",".join(errors)
            )
        _verify_confirmation(case_dir, confirmed)
        if confirmed.field in bound:
            raise ValueError(f"duplicate confirmed input field: {confirmed.field}")
        bound[confirmed.field] = EngineInputValue(
            value=confirmed.value,
            unit=confirmed.unit,
            input_id=confirmed.input_id,
        )
    return bound
