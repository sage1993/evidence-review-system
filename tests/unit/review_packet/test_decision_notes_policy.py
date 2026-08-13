import pytest

from ansim_review.review_packet.decision_record import validate_human_decision_request

_PACKET_HASH = "b" * 64


def _request(decision: str, notes: str) -> dict[str, str]:
    return {
        "reviewer_id": "reviewer-1",
        "packet_hash": _PACKET_HASH,
        "decision": decision,
        "notes": notes,
    }


def test_satisfied_allows_empty_notes() -> None:
    validated = validate_human_decision_request(_request("SATISFIED", ""))

    assert validated["decision"] == "SATISFIED"
    assert validated["notes"] == ""


@pytest.mark.parametrize(
    "decision",
    ["NOT_SATISFIED", "CONDITIONAL", "ADDITIONAL_REVIEW_REQUIRED"],
)
def test_other_decisions_require_notes(decision: str) -> None:
    with pytest.raises(ValueError, match="notes is required"):
        validate_human_decision_request(_request(decision, "   "))
