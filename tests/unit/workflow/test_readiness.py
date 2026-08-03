from __future__ import annotations

import importlib
from types import ModuleType


def _modules() -> tuple[ModuleType, ModuleType]:
    return (
        importlib.import_module("ansim_review.workflow.request"),
        importlib.import_module("ansim_review.workflow.readiness"),
    )


def _attachment(
    attachment_id: str,
    *,
    role: str | None,
    role_confirmation: str | None,
) -> dict[str, object]:
    return {
        "attachment_id": attachment_id,
        "original_name": f"{attachment_id}.pdf",
        "stored_path": f"inputs/original/{attachment_id}.pdf",
        "sha256": "a" * 64,
        "byte_size": 10,
        "mime": "application/pdf",
        "role": role,
        "role_confirmation": role_confirmation,
        "proposed_role": role,
    }


def _request(request: ModuleType, attachments: list[dict[str, object]]):
    return request.decode_review_request(
        {
            "format": "evidence-review/review-request",
            "version": 1,
            "case_id": "CASE-001",
            "question": "검토 질문",
            "attachments": attachments,
        }
    )


def _fact(
    readiness: ModuleType,
    attachment_id: str,
    *,
    parser_declared: bool = True,
    parser_artifact_available: bool = True,
    parser_supported: bool = True,
    ingested: bool = True,
    input_confirmation_required: bool = False,
):
    return readiness.AttachmentReadiness(
        attachment_id=attachment_id,
        parser_declared=parser_declared,
        parser_artifact_available=parser_artifact_available,
        parser_supported=parser_supported,
        ingested=ingested,
        input_confirmation_required=input_confirmation_required,
        configuration_valid=True,
    )


def test_unconfirmed_role_has_highest_priority() -> None:
    request, readiness = _modules()
    review_request = _request(
        request,
        [
            _attachment(
                "ATT-ROLE",
                role=None,
                role_confirmation=None,
            )
        ],
    )
    decision = readiness.evaluate_review_readiness(
        review_request,
        (),
        source_hash_mismatch=True,
    )
    assert decision.state.workflow_state == "ROLE_CONFIRMATION_REQUIRED"
    assert decision.pending_attachment_ids == ("ATT-ROLE",)


def test_reference_parser_and_ingestion_waits_map_to_reference_pending() -> None:
    request, readiness = _modules()
    review_request = _request(
        request,
        [
            _attachment(
                "ATT-REF",
                role="REFERENCE_DOCUMENT",
                role_confirmation="USER_CONFIRMED",
            )
        ],
    )
    parser_pending = readiness.evaluate_review_readiness(
        review_request,
        (
            _fact(
                readiness,
                "ATT-REF",
                parser_artifact_available=False,
                ingested=False,
            ),
        ),
    )
    assert parser_pending.state.workflow_state == "PENDING_REFERENCE_INGESTION"

    ingestion_pending = readiness.evaluate_review_readiness(
        review_request,
        (_fact(readiness, "ATT-REF", ingested=False),),
    )
    assert ingestion_pending.state.workflow_state == "PENDING_REFERENCE_INGESTION"


def test_drawing_registration_and_confirmation_are_separate_gates() -> None:
    request, readiness = _modules()
    review_request = _request(
        request,
        [
            _attachment(
                "ATT-DRAWING",
                role="CASE_DRAWING",
                role_confirmation="USER_CONFIRMED",
            )
        ],
    )
    drawing_pending = readiness.evaluate_review_readiness(
        review_request,
        (_fact(readiness, "ATT-DRAWING", ingested=False),),
    )
    assert drawing_pending.state.workflow_state == "PENDING_DRAWING_INGESTION"

    confirmation_pending = readiness.evaluate_review_readiness(
        review_request,
        (
            _fact(
                readiness,
                "ATT-DRAWING",
                ingested=True,
                input_confirmation_required=True,
            ),
        ),
    )
    assert confirmation_pending.state.workflow_state == "INPUT_CONFIRMATION_REQUIRED"


def test_blocker_reason_codes_follow_canonical_priority() -> None:
    request, readiness = _modules()
    review_request = _request(request, [])
    decision = readiness.evaluate_review_readiness(
        review_request,
        (),
        source_conflict=True,
        source_hash_mismatch=True,
        stale_snapshot=True,
        unapproved_rule=True,
        missing_formula=True,
        missing_required_input=True,
    )
    assert decision.state.workflow_state == "BLOCKED"
    assert decision.state.reason_codes == (
        "SOURCE_CONFLICT",
        "SOURCE_HASH_MISMATCH",
        "STALE_SNAPSHOT",
        "UNAPPROVED_RULE",
        "MISSING_FORMULA",
        "MISSING_REQUIRED_INPUT",
    )
    assert decision.state.resumable is True


def test_all_verified_sources_and_inputs_are_ready_to_evaluate() -> None:
    request, readiness = _modules()
    review_request = _request(
        request,
        [
            _attachment(
                "ATT-REF",
                role="REFERENCE_DOCUMENT",
                role_confirmation="USER_CONFIRMED",
            ),
            _attachment(
                "ATT-DRAWING",
                role="CASE_DRAWING",
                role_confirmation="USER_CONFIRMED",
            ),
            _attachment(
                "ATT-SUPPORT",
                role="SUPPORTING_IMAGE",
                role_confirmation="USER_CONFIRMED",
            ),
        ],
    )
    facts = (
        _fact(readiness, "ATT-DRAWING"),
        _fact(readiness, "ATT-REF"),
        _fact(readiness, "ATT-SUPPORT", ingested=False),
    )
    left = readiness.evaluate_review_readiness(review_request, facts)
    right = readiness.evaluate_review_readiness(
        review_request,
        tuple(reversed(facts)),
    )
    assert left.state.workflow_state == "READY_TO_EVALUATE"
    assert left == right
