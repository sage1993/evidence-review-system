"""Pure deterministic readiness gates for review evaluation."""

from __future__ import annotations

from dataclasses import dataclass

from ansim_review.contracts.attachments import AttachmentRole
from ansim_review.contracts.workflow import (
    ReasonCode,
    WorkflowState,
    WorkflowStateRecord,
    decode_workflow_state_record,
)
from ansim_review.parsing.source_states import (
    SourceState,
    evaluate_source_readiness,
)
from ansim_review.workflow.request import ReviewRequest

_BLOCKER_PRIORITY: tuple[ReasonCode, ...] = (
    "SOURCE_CONFLICT",
    "SOURCE_HASH_MISMATCH",
    "STALE_SNAPSHOT",
    "UNAPPROVED_RULE",
    "MISSING_FORMULA",
    "MISSING_REQUIRED_INPUT",
)


@dataclass(frozen=True, slots=True)
class AttachmentReadiness:
    """Observed preparation facts for one confirmed request attachment."""

    attachment_id: str
    parser_declared: bool
    parser_artifact_available: bool
    parser_supported: bool
    ingested: bool
    input_confirmation_required: bool
    configuration_valid: bool


@dataclass(frozen=True, slots=True)
class ReadinessDecision:
    """Canonical workflow projection plus deterministic pending identities."""

    state: WorkflowStateRecord
    pending_attachment_ids: tuple[str, ...]
    pending_details: tuple[str, ...]


def _state_record(
    state: WorkflowState,
    *,
    run_id: str,
    reason_codes: tuple[ReasonCode, ...] = (),
    resumable: bool = False,
) -> WorkflowStateRecord:
    return decode_workflow_state_record(
        {
            "format": "evidence-review/workflow-state",
            "version": 1,
            "run_id": run_id,
            "workflow_state": state,
            "finalizer_status": None,
            "reason_codes": list(reason_codes),
            "resumable": resumable,
        }
    )


def _decision(
    state: WorkflowState,
    *,
    run_id: str,
    pending_ids: tuple[str, ...] = (),
    pending_details: tuple[str, ...] = (),
    reason_codes: tuple[ReasonCode, ...] = (),
    resumable: bool = False,
) -> ReadinessDecision:
    return ReadinessDecision(
        state=_state_record(
            state,
            run_id=run_id,
            reason_codes=reason_codes,
            resumable=resumable,
        ),
        pending_attachment_ids=tuple(sorted(pending_ids)),
        pending_details=tuple(sorted(pending_details)),
    )


def _fact_map(
    facts: tuple[AttachmentReadiness, ...],
) -> dict[str, AttachmentReadiness]:
    result: dict[str, AttachmentReadiness] = {}
    for fact in facts:
        if fact.attachment_id in result:
            raise ValueError("attachment readiness IDs must be unique")
        result[fact.attachment_id] = fact
    return result


def _source_state(
    *,
    role: AttachmentRole,
    fact: AttachmentReadiness,
) -> SourceState:
    return evaluate_source_readiness(
        role=role,
        parser_declared=fact.parser_declared,
        parser_artifact_available=fact.parser_artifact_available,
        parser_supported=fact.parser_supported,
        ingested=fact.ingested,
        input_confirmation_required=fact.input_confirmation_required,
        configuration_valid=fact.configuration_valid,
    ).state


def evaluate_review_readiness(
    request: ReviewRequest,
    attachment_facts: tuple[AttachmentReadiness, ...],
    *,
    run_id: str = "RUN-READINESS",
    source_conflict: bool = False,
    source_hash_mismatch: bool = False,
    stale_snapshot: bool = False,
    unapproved_rule: bool = False,
    missing_formula: bool = False,
    missing_required_input: bool = False,
) -> ReadinessDecision:
    """Evaluate gates in one fixed order without reading or writing files."""
    unresolved_roles = tuple(
        attachment.attachment_id
        for attachment in request.attachments
        if attachment.role is None
    )
    if unresolved_roles:
        return _decision(
            "ROLE_CONFIRMATION_REQUIRED",
            run_id=run_id,
            pending_ids=unresolved_roles,
            pending_details=("ROLE_CONFIRMATION_REQUIRED",),
        )

    facts = _fact_map(attachment_facts)
    request_ids = {attachment.attachment_id for attachment in request.attachments}
    unknown_facts = tuple(sorted(set(facts) - request_ids))
    if unknown_facts:
        raise ValueError(
            "attachment readiness references unknown IDs: " + ", ".join(unknown_facts)
        )

    reference_pending: list[str] = []
    drawing_pending: list[str] = []
    confirmation_pending: list[str] = []
    missing_fact = missing_required_input

    for attachment in request.attachments:
        role = attachment.role
        if role is None:
            raise AssertionError("unresolved roles must be handled before source gates")
        if role == "SUPPORTING_IMAGE":
            continue
        fact = facts.get(attachment.attachment_id)
        if fact is None:
            missing_fact = True
            continue
        if role == "CASE_DRAWING":
            if not fact.configuration_valid:
                missing_fact = True
            elif not fact.ingested:
                drawing_pending.append(attachment.attachment_id)
            elif fact.input_confirmation_required:
                confirmation_pending.append(attachment.attachment_id)
            continue

        state = _source_state(role=role, fact=fact)
        if state in {
            SourceState.PENDING_PARSER_OUTPUT,
            SourceState.PENDING_REFERENCE_INGESTION,
        }:
            reference_pending.append(attachment.attachment_id)
        elif state in {SourceState.BLOCKED, SourceState.FAILED}:
            missing_fact = True

    if reference_pending:
        return _decision(
            "PENDING_REFERENCE_INGESTION",
            run_id=run_id,
            pending_ids=tuple(reference_pending),
            pending_details=("REFERENCE_PREPARATION_REQUIRED",),
        )
    if drawing_pending:
        return _decision(
            "PENDING_DRAWING_INGESTION",
            run_id=run_id,
            pending_ids=tuple(drawing_pending),
            pending_details=("DRAWING_INGESTION_REQUIRED",),
        )
    if confirmation_pending:
        return _decision(
            "INPUT_CONFIRMATION_REQUIRED",
            run_id=run_id,
            pending_ids=tuple(confirmation_pending),
            pending_details=("DRAWING_CONFIRMATION_REQUIRED",),
        )

    active_blockers = {
        "SOURCE_CONFLICT": source_conflict,
        "SOURCE_HASH_MISMATCH": source_hash_mismatch,
        "STALE_SNAPSHOT": stale_snapshot,
        "UNAPPROVED_RULE": unapproved_rule,
        "MISSING_FORMULA": missing_formula,
        "MISSING_REQUIRED_INPUT": missing_fact,
    }
    reason_codes = tuple(
        reason for reason in _BLOCKER_PRIORITY if active_blockers[reason]
    )
    if reason_codes:
        return _decision(
            "BLOCKED",
            run_id=run_id,
            reason_codes=reason_codes,
            resumable=True,
        )

    return _decision("READY_TO_EVALUATE", run_id=run_id)
