from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from evidence_review.evidence.finalization import finalize_evidence_database
from evidence_review.evidence.ingest import EvidenceSnapshot, ingest_snapshot
from evidence_review.evidence.store import EvidenceStore
from evidence_review.review_matter.events import list_matter_events
from evidence_review.review_matter.source_binding import bind_finalized_evidence
from evidence_review.review_matter.store import MatterStore


def _navigation_api():
    import importlib

    try:
        return importlib.import_module("evidence_review.navigation")
    except ModuleNotFoundError as error:
        pytest.fail(f"NAVIGATION_PACKAGE_MISSING: {error}")


def _finalized_database(path: Path, *, source_hash: str, text: str) -> None:
    with EvidenceStore(path, create=True) as store:
        ingest_snapshot(
            store,
            EvidenceSnapshot(
                documents=({"id": "DOC-001", "title": "Reference"},),
                revisions=(
                    {
                        "id": "REV-001",
                        "document_id": "DOC-001",
                        "source_hash": source_hash,
                        "byte_size": 10,
                        "page_count": 1,
                    },
                ),
                pages=(
                    {
                        "id": "PAGE-001",
                        "revision_id": "REV-001",
                        "page_number": 1,
                        "width": 600.0,
                        "height": 800.0,
                    },
                ),
                elements=(
                    {
                        "id": "EVID-001",
                        "page_id": "PAGE-001",
                        "element_type": "paragraph",
                        "raw_json": {"text": text},
                        "raw_text": text,
                        "normalized_text": text,
                        "raw_payload_hash": "d" * 64,
                        "bbox": [10.0, 10.0, 500.0, 30.0],
                        "parser_order": 0,
                    },
                ),
            ),
        )
        finalize_evidence_database(store)


def test_stale_navigation_result_fails_closed_without_matter_mutation(
    tmp_path: Path,
) -> None:
    first = tmp_path / "first.sqlite"
    second = tmp_path / "second.sqlite"
    _finalized_database(first, source_hash="a" * 64, text="reference")
    _finalized_database(second, source_hash="b" * 64, text="reference")
    first_before = first.read_bytes()
    second_before = second.read_bytes()

    matter = MatterStore(tmp_path / "matter.sqlite")
    matter.create(matter_id="MATTER-001", title="Review")
    bind_finalized_evidence(
        matter,
        matter_id="MATTER-001",
        expected_revision=1,
        evidence_db=first,
    )
    navigation = _navigation_api().navigate_evidence(first, "reference")
    events_before = list_matter_events(matter, "MATTER-001")

    with pytest.raises(ValueError, match="NAVIGATION_RESULT_STALE"):
        _navigation_api().promote_navigation_hit(
            matter,
            matter_id="MATTER-001",
            expected_revision=2,
            evidence_db=second,
            navigation_result=navigation,
            evidence_id="EVID-001",
        )

    assert matter.load("MATTER-001").revision == 2
    assert matter.load("MATTER-001").source_bindings == ()
    assert list_matter_events(matter, "MATTER-001") == events_before
    assert first.read_bytes() == first_before
    assert second.read_bytes() == second_before


def test_promotion_rejects_forged_citation_id_without_matter_mutation(
    tmp_path: Path,
) -> None:
    evidence = tmp_path / "evidence.sqlite"
    _finalized_database(evidence, source_hash="a" * 64, text="reference")
    matter = MatterStore(tmp_path / "matter.sqlite")
    matter.create(matter_id="MATTER-001", title="Review")
    bound = bind_finalized_evidence(
        matter,
        matter_id="MATTER-001",
        expected_revision=1,
        evidence_db=evidence,
    )
    navigation = _navigation_api().navigate_evidence(evidence, "reference")
    forged = replace(
        navigation,
        hits=(
            replace(
                navigation.hits[0],
                citation=replace(navigation.hits[0].citation, citation_id="CIT-FORGED"),
            ),
        ),
    )
    events_before = list_matter_events(matter, "MATTER-001")

    with pytest.raises(ValueError, match="NAVIGATION_RESULT_STALE"):
        _navigation_api().promote_navigation_hit(
            matter,
            matter_id="MATTER-001",
            expected_revision=bound.revision,
            evidence_db=evidence,
            navigation_result=forged,
            evidence_id="EVID-001",
        )

    assert matter.load("MATTER-001").revision == bound.revision
    assert matter.load("MATTER-001").source_bindings == ()
    assert list_matter_events(matter, "MATTER-001") == events_before


def test_valid_navigation_promotion_appends_exact_matter_binding(
    tmp_path: Path,
) -> None:
    evidence = tmp_path / "evidence.sqlite"
    _finalized_database(evidence, source_hash="a" * 64, text="reference")
    evidence_before = evidence.read_bytes()

    matter = MatterStore(tmp_path / "matter.sqlite")
    matter.create(matter_id="MATTER-001", title="Review")
    bound = bind_finalized_evidence(
        matter,
        matter_id="MATTER-001",
        expected_revision=1,
        evidence_db=evidence,
    )
    navigation = _navigation_api().navigate_evidence(evidence, "reference")

    promoted = _navigation_api().promote_navigation_hit(
        matter,
        matter_id="MATTER-001",
        expected_revision=bound.revision,
        evidence_db=evidence,
        navigation_result=navigation,
        evidence_id="EVID-001",
    )

    assert promoted.revision == 3
    assert len(promoted.source_bindings) == 1
    binding = promoted.source_bindings[0]
    assert binding.document_id == "DOC-001"
    assert binding.revision_id == "REV-001"
    assert binding.page_number == 1
    assert binding.evidence_id == "EVID-001"
    assert binding.source_hash == "a" * 64
    assert binding.evidence_snapshot_hash == navigation.evidence_snapshot_hash
    assert binding.evidence_db_sha256 == navigation.evidence_db_sha256
    assert matter.rebuild_projection("MATTER-001").source_bindings == (
        binding,
    )
    assert [event.kind for event in list_matter_events(matter, "MATTER-001")] == [
        "EVIDENCE_BOUND",
        "EVIDENCE_SELECTED",
    ]
    assert evidence.read_bytes() == evidence_before


def test_promotion_uses_matter_compare_and_swap_revision(
    tmp_path: Path,
) -> None:
    evidence = tmp_path / "evidence.sqlite"
    _finalized_database(evidence, source_hash="a" * 64, text="reference")
    matter = MatterStore(tmp_path / "matter.sqlite")
    matter.create(matter_id="MATTER-001", title="Review")
    bind_finalized_evidence(
        matter,
        matter_id="MATTER-001",
        expected_revision=1,
        evidence_db=evidence,
    )
    navigation = _navigation_api().navigate_evidence(evidence, "reference")
    matter.rename("MATTER-001", expected_revision=2, title="Changed")
    events_before = list_matter_events(matter, "MATTER-001")

    with pytest.raises(ValueError, match="MATTER_REVISION_CONFLICT"):
        _navigation_api().promote_navigation_hit(
            matter,
            matter_id="MATTER-001",
            expected_revision=2,
            evidence_db=evidence,
            navigation_result=navigation,
            evidence_id="EVID-001",
        )

    assert matter.load("MATTER-001").revision == 3
    assert list_matter_events(matter, "MATTER-001") == events_before
