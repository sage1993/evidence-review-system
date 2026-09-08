import pytest

from evidence_review.review_matter.contracts import MatterIssue
from evidence_review.review_matter.events import (
    MATTER_EVENT_FORMAT,
    MatterEvent,
    matter_event_document,
)
from evidence_review.review_matter.projection import project_event
from evidence_review.review_matter.store import MatterStore


def test_title_changed_event_has_strict_canonical_document() -> None:
    event = MatterEvent(kind="TITLE_CHANGED", payload={"title": "Changed"})
    assert matter_event_document(event) == {
        "format": MATTER_EVENT_FORMAT,
        "version": 1,
        "kind": "TITLE_CHANGED",
        "payload": {"title": "Changed"},
    }


def test_event_rejects_non_object_payload() -> None:
    with pytest.raises(ValueError, match="payload"):
        MatterEvent(kind="TITLE_CHANGED", payload=[])  # type: ignore[arg-type]


def _evidence_binding_payload() -> dict[str, object]:
    return {
        "evidence_snapshot_hash": "a" * 64,
        "evidence_db_sha256": "b" * 64,
        "schema_version": 4,
        "bound_revision": 2,
    }


@pytest.mark.parametrize("event_kind", ["EVIDENCE_BOUND", "EVIDENCE_REBOUND"])
def test_evidence_binding_projection_requires_all_provenance_fields(
    tmp_path, event_kind: str
) -> None:
    store = MatterStore(tmp_path / "review-matters.sqlite")
    matter = store.create(
        matter_id="MATTER-001",
        title="Review",
        issues=(
            MatterIssue(
                issue_id="ISSUE-001",
                question="Question",
                work_state="READY_TO_FORMALIZE",
                depends_on=(),
            ),
        ),
    )
    payload = _evidence_binding_payload()
    del payload["evidence_snapshot_hash"]

    with pytest.raises(ValueError, match="missing required fields"):
        project_event(matter, MatterEvent(kind=event_kind, payload=payload))


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("evidence_snapshot_hash", "not-a-sha256"),
        ("evidence_db_sha256", "not-a-sha256"),
        ("schema_version", 0),
        ("bound_revision", 99),
    ],
)
@pytest.mark.parametrize("event_kind", ["EVIDENCE_BOUND", "EVIDENCE_REBOUND"])
def test_evidence_binding_projection_rejects_invalid_provenance(
    tmp_path, event_kind: str, field: str, value: object
) -> None:
    store = MatterStore(tmp_path / f"review-matters-{event_kind}-{field}.sqlite")
    matter = store.create(matter_id="MATTER-001", title="Review")
    payload = _evidence_binding_payload()
    payload[field] = value

    with pytest.raises(ValueError):
        project_event(matter, MatterEvent(kind=event_kind, payload=payload))
