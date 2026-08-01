from __future__ import annotations

import pytest

from ansim_review.parsing.source_states import (
    SourceState,
    evaluate_source_readiness,
    validate_source_transition,
)


def test_reference_without_parser_is_pending_parser_output() -> None:
    result = evaluate_source_readiness(
        role="REFERENCE_DOCUMENT",
        parser_declared=False,
        parser_artifact_available=False,
        parser_supported=False,
    )

    assert result.state == "PENDING_PARSER_OUTPUT"
    assert result.reason_codes == ("PARSER_OUTPUT_REQUIRED",)
    assert result.can_ingest_reference is False
    assert result.can_evaluate is False


def test_reference_with_ready_parser_is_pending_ingestion() -> None:
    result = evaluate_source_readiness(
        role="REFERENCE_DOCUMENT",
        parser_declared=True,
        parser_artifact_available=True,
        parser_supported=True,
    )

    assert result.state == "PENDING_REFERENCE_INGESTION"
    assert result.can_ingest_reference is True
    assert result.can_evaluate is False


def test_unknown_parser_kind_is_blocked() -> None:
    result = evaluate_source_readiness(
        role="REFERENCE_DOCUMENT",
        parser_declared=True,
        parser_artifact_available=True,
        parser_supported=False,
    )

    assert result.state == "BLOCKED"
    assert result.reason_codes == ("UNSUPPORTED_PARSER_KIND",)


def test_drawing_routes_to_drawing_lane() -> None:
    result = evaluate_source_readiness(
        role="CASE_DRAWING",
        parser_declared=False,
        parser_artifact_available=False,
        parser_supported=False,
    )
    assert result.state == "PENDING_DRAWING_INGESTION"

    confirmation = evaluate_source_readiness(
        role="CASE_DRAWING",
        parser_declared=False,
        parser_artifact_available=False,
        parser_supported=False,
        input_confirmation_required=True,
    )
    assert confirmation.state == "INPUT_CONFIRMATION_REQUIRED"


def test_supporting_image_is_not_rule_evaluation_authority() -> None:
    result = evaluate_source_readiness(
        role="SUPPORTING_IMAGE",
        parser_declared=False,
        parser_artifact_available=False,
        parser_supported=False,
    )

    assert result.state == "BLOCKED"
    assert result.reason_codes == ("SUPPORTING_EVIDENCE_ONLY",)
    assert result.can_evaluate is False


def test_ingested_reference_is_ready_to_evaluate() -> None:
    result = evaluate_source_readiness(
        role="REFERENCE_DOCUMENT",
        parser_declared=True,
        parser_artifact_available=True,
        parser_supported=True,
        ingested=True,
    )

    assert result.state == "READY_TO_EVALUATE"
    assert result.can_evaluate is True


def test_invalid_configuration_fails() -> None:
    result = evaluate_source_readiness(
        role="REFERENCE_DOCUMENT",
        parser_declared=True,
        parser_artifact_available=False,
        parser_supported=True,
        configuration_valid=False,
    )

    assert result.state == "FAILED"
    assert result.reason_codes == ("SOURCE_CONFIGURATION_INVALID",)


def test_illegal_direct_transition_is_rejected() -> None:
    with pytest.raises(ValueError, match="ILLEGAL_SOURCE_STATE_TRANSITION"):
        validate_source_transition(
            SourceState.RECEIVED,
            SourceState.READY_TO_EVALUATE,
        )


def test_legal_preparation_transition_is_allowed() -> None:
    validate_source_transition(
        SourceState.CLASSIFYING_INPUTS,
        SourceState.PENDING_REFERENCE_INGESTION,
    )
