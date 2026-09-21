from pathlib import Path

from evidence_review.canonical_json import dump_bytes
from evidence_review.contracts.review import TrackBAudit
from evidence_review.review_run import (
    _required_facet_completeness,
    _track_b_bundle_document,
    _track_b_validation_document,
)


def test_required_facet_completeness_is_a_non_authoritative_summary() -> None:
    assert _required_facet_completeness(
        (
            {"issue_id": "I1", "missing_facet_ids": []},
            {"issue_id": "I2", "missing_facet_ids": ["distance"]},
        )
    ) == {
        "status": "INCOMPLETE",
        "covered_issue_count": 1,
        "total_issue_count": 2,
    }


def test_required_facet_completeness_explicitly_marks_absence() -> None:
    assert _required_facet_completeness(()) == {
        "status": "NOT_APPLICABLE",
        "covered_issue_count": 0,
        "total_issue_count": 0,
    }


def test_track_b_bundle_uses_v3_planner_obligations_not_retrieval_coverage(tmp_path: Path) -> None:
    (tmp_path / "review-request.json").write_bytes(
        dump_bytes(
            {
                "question": "FAR and contribution review",
                "inputs": {
                    "question_plan": {
                        "issues": [
                            {
                                "id": "I1",
                                "required_facet_ids": [
                                    "basic_far",
                                    "contribution_delivery_method",
                                ],
                            }
                        ]
                    },
                    "facet_coverage": [
                        {"issue_id": "I1", "missing_facet_ids": []}
                    ],
                },
                "evidence": [
                    {
                        "citation": {"citation_id": "C1"},
                        "text": "cited evidence",
                    }
                ],
            }
        )
    )

    bundle = _track_b_bundle_document(
        tmp_path,
        "RUN-1",
        {"claims": [{"citation_ids": ["C1"]}]},
    )

    assert bundle["version"] == 2
    assert bundle["required_facets_by_issue"] == {
        "I1": ["basic_far", "contribution_delivery_method"]
    }
    assert "required_facet_completeness" not in bundle


def test_track_b_bundle_keeps_legacy_retrieval_summary_at_version_one(tmp_path: Path) -> None:
    (tmp_path / "review-request.json").write_bytes(
        dump_bytes(
            {
                "question": "Legacy review",
                "inputs": {"facet_coverage": []},
                "evidence": [],
            }
        )
    )

    bundle = _track_b_bundle_document(tmp_path, "RUN-1", {"claims": []})

    assert bundle["version"] == 1
    assert bundle["required_facet_completeness"] == {
        "status": "NOT_APPLICABLE",
        "covered_issue_count": 0,
        "total_issue_count": 0,
    }


def test_track_b_validation_records_v3_audit_status_and_obligations(tmp_path: Path) -> None:
    (tmp_path / "track-b-bundle.json").write_bytes(
        dump_bytes(
            {
                "question": "FAR and contribution review",
                "required_facets_by_issue": {
                    "I1": ["basic_far", "contribution_delivery_method"]
                },
            }
        )
    )
    track_b_path = tmp_path / "track-b-output.json"
    track_b_path.write_bytes(dump_bytes({"run_id": "RUN-1"}))

    document = _track_b_validation_document(
        tmp_path,
        "RUN-1",
        track_b_path,
        TrackBAudit(
            run_id="RUN-1",
            claim_audits=(),
            overall_disposition="INCOMPLETE",
            required_facet_completeness="INCOMPLETE",
        ),
    )

    assert document["version"] == 3
    assert document["required_facet_completeness"] == {
        "status": "INCOMPLETE",
        "required_facets_by_issue": {
            "I1": ["basic_far", "contribution_delivery_method"]
        },
    }


def test_track_b_validation_keeps_legacy_metadata_at_version_two(tmp_path: Path) -> None:
    summary = {
        "status": "NOT_APPLICABLE",
        "covered_issue_count": 0,
        "total_issue_count": 0,
    }
    (tmp_path / "track-b-bundle.json").write_bytes(
        dump_bytes({"question": "Legacy review", "required_facet_completeness": summary})
    )
    track_b_path = tmp_path / "track-b-output.json"
    track_b_path.write_bytes(dump_bytes({"run_id": "RUN-1"}))

    document = _track_b_validation_document(
        tmp_path,
        "RUN-1",
        track_b_path,
        TrackBAudit(
            run_id="RUN-1",
            claim_audits=(),
            overall_disposition="INCOMPLETE",
        ),
    )

    assert document["version"] == 2
    assert document["required_facet_completeness"] == summary
