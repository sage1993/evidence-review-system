import pytest

from evidence_review.review_matter.contracts import (
    MATTER_SOURCE_BINDING_FORMAT,
    MatterSourceBinding,
    decode_review_matter,
    review_matter_document,
)


def _matter_document() -> dict[str, object]:
    return {
        "format": "evidence-review/review-matter",
        "version": 1,
        "matter_id": "MATTER-001",
        "title": "Accessible toilet review",
        "revision": 1,
        "issues": [
            {
                "issue_id": "ISSUE-001",
                "question": "Is the entrance width sufficient?",
                "work_state": "NEEDS_EVIDENCE",
                "depends_on": [],
            }
        ],
        "source_bindings": [],
    }


def test_matter_issue_rejects_formal_issue_status_as_work_state() -> None:
    document = _matter_document()
    issue = document["issues"][0]
    assert isinstance(issue, dict)
    issue["work_state"] = "RESOLVED"
    with pytest.raises(ValueError, match="work_state"):
        decode_review_matter(document)


def test_review_matter_round_trips_through_strict_canonical_document() -> None:
    matter = decode_review_matter(_matter_document())
    assert review_matter_document(matter) == _matter_document()


def test_review_matter_rejects_unknown_fields_and_duplicate_issue_ids() -> None:
    unknown = _matter_document()
    unknown["unexpected"] = True
    with pytest.raises(ValueError, match="unknown fields"):
        decode_review_matter(unknown)

    duplicate = _matter_document()
    issues = duplicate["issues"]
    assert isinstance(issues, list)
    issues.append(dict(issues[0]))
    with pytest.raises(ValueError, match="duplicate issue"):
        decode_review_matter(duplicate)


def test_matter_id_cannot_use_drawing_case_identity() -> None:
    document = _matter_document()
    document["matter_id"] = "CASE-VIS-001"
    with pytest.raises(ValueError, match="matter_id"):
        decode_review_matter(document)


def test_source_binding_document_keeps_exact_evidence_identity() -> None:
    binding = MatterSourceBinding(
        binding_id="BIND-001",
        document_id="LAW-001",
        revision_id="LAW-001-REV-1",
        page_number=3,
        evidence_id="EVID-001",
        bbox=(10.0, 20.0, 30.0, 40.0),
        source_hash="a" * 64,
        evidence_snapshot_hash="b" * 64,
        evidence_db_sha256="c" * 64,
    )
    assert binding.format == MATTER_SOURCE_BINDING_FORMAT
    assert binding.evidence_db_sha256 == "c" * 64
