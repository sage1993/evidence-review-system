from __future__ import annotations

import pytest

from evidence_review.review_matter.events import MatterEvent, append_matter_event
from evidence_review.review_matter.service import ReviewMatterService
from evidence_review.review_matter.store import MatterRevisionConflict, MatterStore


def _legacy_service(tmp_path):
    service = ReviewMatterService.open(tmp_path)
    service.create(matter_id="MATTER-1", title="Review")
    service.add_issue(matter_id="MATTER-1", expected_revision=1, issue_id="I1",
                      question="Check source", work_state="READY_TO_FORMALIZE")
    return service


def test_explicit_facets_are_append_only_and_revision_checked(tmp_path):
    service = _legacy_service(tmp_path)
    with MatterStore(tmp_path / "matter.sqlite") as store:
        before = store.list_events("MATTER-1")
    with pytest.raises(MatterRevisionConflict):
        service.set_required_facets(matter_id="MATTER-1", expected_revision=1,
                                    issue_id="I1", required_facet_ids=("source_support",))
    with MatterStore(tmp_path / "matter.sqlite") as store:
        assert store.list_events("MATTER-1") == before
        assert store.load("MATTER-1").revision == 2
    result = service.set_required_facets(matter_id="MATTER-1", expected_revision=2,
                                         issue_id="I1", required_facet_ids=("source_support",))
    assert result.revision == 3
    with pytest.raises(ValueError, match="already has"):
        service.set_required_facets(matter_id="MATTER-1", expected_revision=3,
                                    issue_id="I1", required_facet_ids=("different",))
    with MatterStore(tmp_path / "matter.sqlite") as store:
        assert store.list_events("MATTER-1")[:len(before)] == before
        assert len(store.list_events("MATTER-1")) == len(before) + 1
        assert store.rebuild_projection("MATTER-1").matter == result


@pytest.mark.parametrize("facets", [(), ("a", "a"), "abc", b"abc"])
def test_invalid_facets_do_not_append(tmp_path, facets):
    service = _legacy_service(tmp_path)
    with pytest.raises(ValueError):
        service.set_required_facets(matter_id="MATTER-1", expected_revision=2,
                                    issue_id="I1", required_facet_ids=facets)
    with MatterStore(tmp_path / "matter.sqlite") as store:
        assert store.load("MATTER-1").revision == 2
        assert len(store.list_events("MATTER-1")) == 1


def test_unknown_issue_does_not_append(tmp_path):
    service = _legacy_service(tmp_path)
    with pytest.raises(ValueError, match="unknown issue"):
        service.set_required_facets(matter_id="MATTER-1", expected_revision=2,
                                    issue_id="OTHER", required_facet_ids=("source_support",))
    with MatterStore(tmp_path / "matter.sqlite") as store:
        assert store.load("MATTER-1").revision == 2
        assert len(store.list_events("MATTER-1")) == 1


@pytest.mark.parametrize("kind,payload", [
    ("ISSUE_STATE_CHANGED", {"issue_id": "I1", "work_state": "NEEDS_EVIDENCE"}),
    ("EVIDENCE_REBOUND", {"evidence_snapshot_hash": "a" * 64,
                          "evidence_db_sha256": "b" * 64,
                          "schema_version": 4, "bound_revision": 4}),
    ("ISSUES_INVALIDATED", {"issue_ids": ["I1"], "source_key": None, "new_source_hash": "c" * 64}),
])
def test_facets_survive_state_changes_and_event_replay(tmp_path, kind, payload):
    service = _legacy_service(tmp_path)
    service.set_required_facets(matter_id="MATTER-1", expected_revision=2,
                                issue_id="I1", required_facet_ids=("source_support",))
    with MatterStore(tmp_path / "matter.sqlite") as store:
        append_matter_event(store, "MATTER-1", 3, MatterEvent(kind=kind, payload=payload))
        assert store.load("MATTER-1").issues[0].required_facet_ids == ("source_support",)
        rebuilt = store.rebuild_projection("MATTER-1")
        assert rebuilt.issues[0].required_facet_ids == ("source_support",)
