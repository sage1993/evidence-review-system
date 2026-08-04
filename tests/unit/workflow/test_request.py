from __future__ import annotations

import importlib
import json
from types import ModuleType

import pytest


def _request_module() -> ModuleType:
    try:
        return importlib.import_module("ansim_review.workflow.request")
    except ModuleNotFoundError:
        pytest.fail("workflow request module is missing")


def _attachment(
    attachment_id: str = "ATT-001",
    *,
    role: str | None = "REFERENCE_DOCUMENT",
    role_confirmation: str | None = "USER_CONFIRMED",
    proposed_role: str | None = None,
) -> dict[str, object]:
    return {
        "attachment_id": attachment_id,
        "original_name": f"{attachment_id}.pdf",
        "stored_path": f"inputs/original/{attachment_id}.pdf",
        "sha256": "a" * 64,
        "byte_size": 123,
        "mime": "application/pdf",
        "role": role,
        "role_confirmation": role_confirmation,
        "proposed_role": proposed_role,
    }


def _payload(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "format": "evidence-review/review-request",
        "version": 1,
        "case_id": "CASE-001",
        "question": "이 기준을 충족하는가?",
        "attachments": [_attachment()],
    }
    payload.update(overrides)
    return payload


def test_review_request_rejects_empty_question_and_case_id() -> None:
    request = _request_module()
    with pytest.raises(ValueError, match="case_id"):
        request.decode_review_request(_payload(case_id=""))
    with pytest.raises(ValueError, match="question"):
        request.decode_review_request(_payload(question=""))


def test_review_request_rejects_unknown_fields() -> None:
    request = _request_module()
    with pytest.raises(ValueError, match="unknown fields: run_id"):
        request.decode_review_request(_payload(run_id="RUN-001"))


def test_attachment_metadata_uses_existing_strict_validation() -> None:
    request = _request_module()
    unsafe = _attachment()
    unsafe["stored_path"] = "../outside.pdf"
    with pytest.raises(ValueError, match="stored_path"):
        request.decode_review_request(_payload(attachments=[unsafe]))

    invalid_hash = _attachment()
    invalid_hash["sha256"] = "A" * 64
    with pytest.raises(ValueError, match="sha256"):
        request.decode_review_request(_payload(attachments=[invalid_hash]))


def test_request_rejects_duplicate_attachment_identity_and_path() -> None:
    request = _request_module()
    first = _attachment("ATT-001")
    duplicate_id = _attachment("ATT-001")
    duplicate_id["stored_path"] = "inputs/original/other.pdf"
    with pytest.raises(ValueError, match="attachment_id"):
        request.decode_review_request(_payload(attachments=[first, duplicate_id]))

    duplicate_path = _attachment("ATT-002")
    duplicate_path["stored_path"] = first["stored_path"]
    with pytest.raises(ValueError, match="stored_path"):
        request.decode_review_request(_payload(attachments=[first, duplicate_path]))


def test_proposed_role_does_not_confirm_ingestion_lane() -> None:
    request = _request_module()
    pending = _attachment(
        role=None,
        role_confirmation=None,
        proposed_role="CASE_DRAWING",
    )
    decoded = request.decode_review_request(_payload(attachments=[pending]))
    assert request.requires_role_confirmation(decoded) is True
    assert request.confirmed_attachments(decoded) == ()


def test_only_user_confirmed_role_becomes_immutable_attachment() -> None:
    request = _request_module()
    invalid = _attachment(
        role="CASE_DRAWING",
        role_confirmation=None,
        proposed_role="CASE_DRAWING",
    )
    with pytest.raises(ValueError, match="USER_CONFIRMED"):
        request.decode_review_request(_payload(attachments=[invalid]))

    decoded = request.decode_review_request(
        _payload(attachments=[_attachment(role="CASE_DRAWING")])
    )
    attachments = request.confirmed_attachments(decoded)
    assert len(attachments) == 1
    assert attachments[0].role == "CASE_DRAWING"


def test_request_hash_is_canonical_and_attachment_order_independent() -> None:
    request = _request_module()
    first = _attachment("ATT-001")
    second = _attachment("ATT-002", role="CASE_DRAWING")
    left = request.decode_review_request(_payload(attachments=[first, second]))
    right = request.decode_review_request(_payload(attachments=[second, first]))

    assert request.review_request_document(left) == request.review_request_document(right)
    assert request.review_request_bytes(left) == request.review_request_bytes(right)
    assert request.review_request_sha256(left) == request.review_request_sha256(right)
    assert request.review_request_bytes(left).endswith(b"\n")
    assert json.loads(request.review_request_bytes(left)) == request.review_request_document(left)


def test_request_hash_has_no_operational_run_fields() -> None:
    request = _request_module()
    decoded = request.decode_review_request(_payload())
    document = request.review_request_document(decoded)
    assert "run_id" not in document
    assert "recorded_at" not in document
