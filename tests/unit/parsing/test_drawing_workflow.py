from ansim_review.parsing.drawing_workflow import (
    DrawingWorkflowFacts,
    project_drawing_workflow,
)


def test_missing_source_projects_pending_ingestion() -> None:
    record = project_drawing_workflow(
        "RUN-001", DrawingWorkflowFacts(has_source=False)
    )
    assert record.workflow_state == "PENDING_DRAWING_INGESTION"
    assert record.reason_codes == ()
    assert record.resumable is False


def test_rejected_quality_projects_resumable_block() -> None:
    record = project_drawing_workflow(
        "RUN-001",
        DrawingWorkflowFacts(has_source=True, quality_rejected=True),
    )
    assert record.workflow_state == "BLOCKED"
    assert record.reason_codes == ("DRAWING_QUALITY_REJECTED",)
    assert record.resumable is True


def test_integrity_failure_projects_terminal_failure() -> None:
    record = project_drawing_workflow(
        "RUN-001",
        DrawingWorkflowFacts(has_source=True, terminal_integrity_failure=True),
    )
    assert record.workflow_state == "FAILED"
    assert record.reason_codes == ("SOURCE_HASH_MISMATCH",)
    assert record.resumable is False


def test_conflict_projects_confirmation_required_without_reason_codes() -> None:
    record = project_drawing_workflow(
        "RUN-001",
        DrawingWorkflowFacts(has_source=True, has_conflict=True),
    )
    assert record.workflow_state == "INPUT_CONFIRMATION_REQUIRED"
    assert record.reason_codes == ()
    assert record.resumable is False


def test_missing_required_input_projects_confirmation_required() -> None:
    record = project_drawing_workflow(
        "RUN-001",
        DrawingWorkflowFacts(has_source=True, missing_required_inputs=True),
    )
    assert record.workflow_state == "INPUT_CONFIRMATION_REQUIRED"


def test_validated_inputs_project_ready_to_evaluate() -> None:
    record = project_drawing_workflow(
        "RUN-001",
        DrawingWorkflowFacts(has_source=True, has_validated_inputs=True),
    )
    assert record.workflow_state == "READY_TO_EVALUATE"
    assert record.finalizer_status is None
