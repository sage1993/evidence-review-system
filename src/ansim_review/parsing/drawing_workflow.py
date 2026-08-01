"""M0-compliant workflow projection for drawing evidence processing."""

from __future__ import annotations

from dataclasses import dataclass

from ansim_review.contracts.workflow import (
    WorkflowStateRecord,
    decode_workflow_state_record,
    workflow_state_document,
)


@dataclass(frozen=True, slots=True)
class DrawingWorkflowFacts:
    """Minimal deterministic facts used to project drawing workflow progress."""

    has_source: bool
    terminal_integrity_failure: bool = False
    quality_rejected: bool = False
    has_conflict: bool = False
    missing_required_inputs: bool = False
    has_validated_inputs: bool = False

    def __post_init__(self) -> None:
        for field, value in (
            ("has_source", self.has_source),
            ("terminal_integrity_failure", self.terminal_integrity_failure),
            ("quality_rejected", self.quality_rejected),
            ("has_conflict", self.has_conflict),
            ("missing_required_inputs", self.missing_required_inputs),
            ("has_validated_inputs", self.has_validated_inputs),
        ):
            if not isinstance(value, bool):
                raise ValueError(f"{field} must be a boolean")


def project_drawing_workflow(
    run_id: str,
    facts: DrawingWorkflowFacts,
) -> WorkflowStateRecord:
    """Project drawing facts using the fixed M0 precedence and relationships."""
    if facts.terminal_integrity_failure:
        record = WorkflowStateRecord(
            format="ansim/workflow-state",
            version=1,
            run_id=run_id,
            workflow_state="FAILED",
            finalizer_status=None,
            reason_codes=("SOURCE_HASH_MISMATCH",),
            resumable=False,
        )
    elif facts.quality_rejected:
        record = WorkflowStateRecord(
            format="ansim/workflow-state",
            version=1,
            run_id=run_id,
            workflow_state="BLOCKED",
            finalizer_status=None,
            reason_codes=("DRAWING_QUALITY_REJECTED",),
            resumable=True,
        )
    elif not facts.has_source:
        record = WorkflowStateRecord(
            format="ansim/workflow-state",
            version=1,
            run_id=run_id,
            workflow_state="PENDING_DRAWING_INGESTION",
            finalizer_status=None,
            reason_codes=(),
            resumable=False,
        )
    elif facts.has_conflict or facts.missing_required_inputs:
        record = WorkflowStateRecord(
            format="ansim/workflow-state",
            version=1,
            run_id=run_id,
            workflow_state="INPUT_CONFIRMATION_REQUIRED",
            finalizer_status=None,
            reason_codes=(),
            resumable=False,
        )
    elif facts.has_validated_inputs:
        record = WorkflowStateRecord(
            format="ansim/workflow-state",
            version=1,
            run_id=run_id,
            workflow_state="READY_TO_EVALUATE",
            finalizer_status=None,
            reason_codes=(),
            resumable=False,
        )
    else:
        record = WorkflowStateRecord(
            format="ansim/workflow-state",
            version=1,
            run_id=run_id,
            workflow_state="INPUT_CONFIRMATION_REQUIRED",
            finalizer_status=None,
            reason_codes=(),
            resumable=False,
        )
    return decode_workflow_state_record(workflow_state_document(record))
