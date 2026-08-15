"""Pure source-readiness evaluation for generic input lanes."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from evidence_review.contracts.attachments import AttachmentRole


class SourceState(StrEnum):
    RECEIVED = "RECEIVED"
    CLASSIFYING_INPUTS = "CLASSIFYING_INPUTS"
    PENDING_PARSER_OUTPUT = "PENDING_PARSER_OUTPUT"
    PENDING_REFERENCE_INGESTION = "PENDING_REFERENCE_INGESTION"
    PENDING_DRAWING_INGESTION = "PENDING_DRAWING_INGESTION"
    INPUT_CONFIRMATION_REQUIRED = "INPUT_CONFIRMATION_REQUIRED"
    READY_TO_EVALUATE = "READY_TO_EVALUATE"
    BLOCKED = "BLOCKED"
    FAILED = "FAILED"


@dataclass(frozen=True, slots=True)
class SourceReadiness:
    state: SourceState
    reason_codes: tuple[str, ...]
    can_ingest_reference: bool
    can_evaluate: bool


def evaluate_source_readiness(
    *,
    role: AttachmentRole,
    parser_declared: bool,
    parser_artifact_available: bool,
    parser_supported: bool,
    ingested: bool = False,
    input_confirmation_required: bool = False,
    configuration_valid: bool = True,
) -> SourceReadiness:
    """Return one deterministic readiness projection without side effects."""
    if not configuration_valid:
        return SourceReadiness(
            SourceState.FAILED,
            ("SOURCE_CONFIGURATION_INVALID",),
            False,
            False,
        )
    if role == "CASE_DRAWING":
        if input_confirmation_required:
            return SourceReadiness(
                SourceState.INPUT_CONFIRMATION_REQUIRED,
                ("DRAWING_INPUT_CONFIRMATION_REQUIRED",),
                False,
                False,
            )
        return SourceReadiness(
            SourceState.PENDING_DRAWING_INGESTION,
            ("DRAWING_BACKEND_REQUIRED",),
            False,
            False,
        )
    if role == "SUPPORTING_IMAGE":
        return SourceReadiness(
            SourceState.BLOCKED,
            ("SUPPORTING_EVIDENCE_ONLY",),
            False,
            False,
        )
    if not parser_declared or not parser_artifact_available:
        return SourceReadiness(
            SourceState.PENDING_PARSER_OUTPUT,
            ("PARSER_OUTPUT_REQUIRED",),
            False,
            False,
        )
    if not parser_supported:
        return SourceReadiness(
            SourceState.BLOCKED,
            ("UNSUPPORTED_PARSER_KIND",),
            False,
            False,
        )
    if ingested:
        return SourceReadiness(
            SourceState.READY_TO_EVALUATE,
            (),
            False,
            True,
        )
    return SourceReadiness(
        SourceState.PENDING_REFERENCE_INGESTION,
        ("REFERENCE_INGESTION_REQUIRED",),
        True,
        False,
    )


_ALLOWED_TRANSITIONS: dict[SourceState, frozenset[SourceState]] = {
    SourceState.RECEIVED: frozenset(
        {SourceState.CLASSIFYING_INPUTS, SourceState.FAILED}
    ),
    SourceState.CLASSIFYING_INPUTS: frozenset(
        {
            SourceState.PENDING_PARSER_OUTPUT,
            SourceState.PENDING_REFERENCE_INGESTION,
            SourceState.PENDING_DRAWING_INGESTION,
            SourceState.INPUT_CONFIRMATION_REQUIRED,
            SourceState.BLOCKED,
            SourceState.FAILED,
        }
    ),
    SourceState.PENDING_PARSER_OUTPUT: frozenset(
        {SourceState.PENDING_REFERENCE_INGESTION, SourceState.BLOCKED, SourceState.FAILED}
    ),
    SourceState.PENDING_REFERENCE_INGESTION: frozenset(
        {SourceState.READY_TO_EVALUATE, SourceState.BLOCKED, SourceState.FAILED}
    ),
    SourceState.PENDING_DRAWING_INGESTION: frozenset(
        {SourceState.INPUT_CONFIRMATION_REQUIRED, SourceState.READY_TO_EVALUATE, SourceState.FAILED}
    ),
    SourceState.INPUT_CONFIRMATION_REQUIRED: frozenset(
        {SourceState.READY_TO_EVALUATE, SourceState.BLOCKED, SourceState.FAILED}
    ),
    SourceState.READY_TO_EVALUATE: frozenset(),
    SourceState.BLOCKED: frozenset(),
    SourceState.FAILED: frozenset(),
}


def validate_source_transition(previous: SourceState, next_state: SourceState) -> None:
    """Reject state jumps that bypass required preparation or review evidence."""
    if next_state not in _ALLOWED_TRANSITIONS[previous]:
        raise ValueError(
            f"ILLEGAL_SOURCE_STATE_TRANSITION: {previous.value}->{next_state.value}"
        )
