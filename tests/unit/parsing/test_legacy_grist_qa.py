from __future__ import annotations

from copy import deepcopy

import pytest

from ansim_review.canonical_json import dump_bytes
from ansim_review.parsing.legacy_grist_qa import (
    GRIST_QA_FORMAT,
    REQUIRED_SAMPLE_KINDS,
    REQUIRED_VIEW_IDS,
    decode_grist_qa,
    derive_grist_qa_status,
    grist_qa_document,
    grist_qa_status_document,
)


def valid_payload() -> dict[str, object]:
    evidence_id = "E-SCREEN-1"
    views = [
        {
            "view_id": view_id,
            "status": "PASS",
            "evidence_ids": [evidence_id],
            "notes": f"{view_id} checked in Grist Desktop",
        }
        for view_id in REQUIRED_VIEW_IDS
    ]
    samples = [
        {
            "sample_id": f"S-{index}",
            "content_kind": content_kind,
            "row_id": f"ROW-{index}",
            "asset_path": f"04_visuals/assets/{index}.png",
            "asset_sha256": str(index) * 64,
            "result": "PASS",
            "evidence_ids": [evidence_id],
            "notes": f"representative {content_kind}",
        }
        for index, content_kind in enumerate(REQUIRED_SAMPLE_KINDS, start=1)
    ]
    return {
        "format": GRIST_QA_FORMAT,
        "version": 1,
        "scope": "LEGACY_UI_QA",
        "identity_claim": "LEGACY_NON_CANONICAL",
        "review": {
            "reviewer_id": "reviewer@example.com",
            "reviewed_at": "2026-08-02T15:30:00+09:00",
        },
        "environment": {
            "grist_desktop_version": "0.3.1",
            "os": "Windows 11 24H2",
        },
        "sources": {
            "grist_file": {
                "path": "legacy/workspace.grist",
                "sha256": "a" * 64,
            },
            "visual_manifest": {
                "path": "04_visuals/manifests/visual_manifest.csv",
                "sha256": "b" * 64,
            },
            "inspection_report": {
                "path": "runs/legacy-visual-inspection.json",
                "sha256": "c" * 64,
            },
        },
        "evidence_files": [
            {
                "evidence_id": evidence_id,
                "path": "qa/screenshots/grist-overview.png",
                "sha256": "d" * 64,
            }
        ],
        "views": views,
        "samples": samples,
        "findings": [],
    }


def test_strict_artifact_round_trips_to_canonical_document() -> None:
    payload = valid_payload()

    artifact = decode_grist_qa(payload)

    assert artifact.format == "evidence-review/grist-desktop-qa"
    assert artifact.scope == "LEGACY_UI_QA"
    assert artifact.identity_claim == "LEGACY_NON_CANONICAL"
    assert tuple(view.view_id for view in artifact.views) == REQUIRED_VIEW_IDS
    assert grist_qa_document(artifact) == payload


def test_review_timestamp_requires_timezone() -> None:
    payload = valid_payload()
    review = payload["review"]
    assert isinstance(review, dict)
    review["reviewed_at"] = "2026-08-02T15:30:00"

    with pytest.raises(ValueError, match="timezone"):
        decode_grist_qa(payload)


def test_unknown_top_level_field_is_rejected() -> None:
    payload = valid_payload()
    payload["overall_status"] = "PASS"

    with pytest.raises(ValueError, match="unknown fields"):
        decode_grist_qa(payload)


def test_every_required_view_must_exist_exactly_once() -> None:
    payload = valid_payload()
    views = payload["views"]
    assert isinstance(views, list)
    views.pop()

    with pytest.raises(ValueError, match="MISSING_GRIST_QA_VIEW"):
        decode_grist_qa(payload)

    payload = valid_payload()
    views = payload["views"]
    assert isinstance(views, list)
    views.append(deepcopy(views[0]))

    with pytest.raises(ValueError, match="DUPLICATE_GRIST_QA_VIEW"):
        decode_grist_qa(payload)


def test_stable_ids_must_be_unique() -> None:
    payload = valid_payload()
    evidence = payload["evidence_files"]
    assert isinstance(evidence, list)
    evidence.append(deepcopy(evidence[0]))
    with pytest.raises(ValueError, match="DUPLICATE_EVIDENCE_ID"):
        decode_grist_qa(payload)

    payload = valid_payload()
    samples = payload["samples"]
    assert isinstance(samples, list)
    samples.append(deepcopy(samples[0]))
    with pytest.raises(ValueError, match="DUPLICATE_SAMPLE_ID"):
        decode_grist_qa(payload)

    payload = valid_payload()
    payload["findings"] = [
        {
            "finding_id": "F-1",
            "view_id": "PAGE_RENDER",
            "status": "RESOLVED",
            "row_id": "ROW-1",
            "file_path": None,
            "description": "resolved display issue",
            "evidence_ids": [],
        },
        {
            "finding_id": "F-1",
            "view_id": "PAGE_RENDER",
            "status": "RESOLVED",
            "row_id": "ROW-2",
            "file_path": None,
            "description": "duplicate finding id",
            "evidence_ids": [],
        },
    ]
    with pytest.raises(ValueError, match="DUPLICATE_FINDING_ID"):
        decode_grist_qa(payload)


def test_evidence_references_must_resolve() -> None:
    payload = valid_payload()
    views = payload["views"]
    assert isinstance(views, list)
    first_view = views[0]
    assert isinstance(first_view, dict)
    first_view["evidence_ids"] = ["E-MISSING"]

    with pytest.raises(ValueError, match="EVIDENCE_ID_NOT_FOUND:E-MISSING"):
        decode_grist_qa(payload)


def test_finding_requires_reproducible_locator() -> None:
    payload = valid_payload()
    payload["findings"] = [
        {
            "finding_id": "F-1",
            "view_id": "PAGE_RENDER",
            "status": "OPEN",
            "row_id": None,
            "file_path": None,
            "description": "not reproducible",
            "evidence_ids": [],
        }
    ]

    with pytest.raises(ValueError, match="FINDING_LOCATOR_REQUIRED:F-1"):
        decode_grist_qa(payload)


def test_fail_view_requires_open_finding_for_same_view() -> None:
    payload = valid_payload()
    views = payload["views"]
    assert isinstance(views, list)
    first_view = views[0]
    assert isinstance(first_view, dict)
    first_view["status"] = "FAIL"

    with pytest.raises(ValueError, match="FAIL_VIEW_REQUIRES_OPEN_FINDING"):
        decode_grist_qa(payload)

    payload["findings"] = [
        {
            "finding_id": "F-1",
            "view_id": first_view["view_id"],
            "status": "OPEN",
            "row_id": "ROW-FAIL",
            "file_path": "04_visuals/assets/missing.png",
            "description": "thumbnail is broken",
            "evidence_ids": [],
        }
    ]
    artifact = decode_grist_qa(payload)
    assert artifact.views[0].status == "FAIL"
    assert artifact.findings[0].status == "OPEN"


def test_all_required_observations_derive_pass() -> None:
    artifact = decode_grist_qa(valid_payload())

    assert derive_grist_qa_status(artifact) == "PASS"


def test_failure_signals_take_precedence() -> None:
    payload = valid_payload()
    views = payload["views"]
    assert isinstance(views, list)
    view = views[0]
    assert isinstance(view, dict)
    view["status"] = "FAIL"
    payload["findings"] = [
        {
            "finding_id": "F-1",
            "view_id": view["view_id"],
            "status": "OPEN",
            "row_id": "ROW-FAIL",
            "file_path": None,
            "description": "broken attachment preview",
            "evidence_ids": [],
        }
    ]
    assert derive_grist_qa_status(decode_grist_qa(payload)) == "FAIL"

    payload = valid_payload()
    samples = payload["samples"]
    assert isinstance(samples, list)
    sample = samples[0]
    assert isinstance(sample, dict)
    sample["result"] = "FAIL"
    assert derive_grist_qa_status(decode_grist_qa(payload)) == "FAIL"

    payload = valid_payload()
    payload["findings"] = [
        {
            "finding_id": "F-2",
            "view_id": "PAGE_RENDER",
            "status": "OPEN",
            "row_id": "ROW-OPEN",
            "file_path": None,
            "description": "open issue despite PASS view",
            "evidence_ids": [],
        }
    ]
    assert derive_grist_qa_status(decode_grist_qa(payload)) == "FAIL"


def test_not_run_or_missing_pass_sample_derives_incomplete() -> None:
    payload = valid_payload()
    views = payload["views"]
    assert isinstance(views, list)
    view = views[0]
    assert isinstance(view, dict)
    view["status"] = "NOT_RUN"
    assert derive_grist_qa_status(decode_grist_qa(payload)) == "INCOMPLETE"

    payload = valid_payload()
    samples = payload["samples"]
    assert isinstance(samples, list)
    samples.pop()
    assert derive_grist_qa_status(decode_grist_qa(payload)) == "INCOMPLETE"


def test_status_document_is_deterministic_and_explicit() -> None:
    artifact = decode_grist_qa(valid_payload())

    document = grist_qa_status_document(artifact, "e" * 64)

    assert document == {
        "format": "evidence-review/grist-desktop-qa-status",
        "version": 1,
        "status": "PASS",
        "accepted": True,
        "artifact_sha256": "e" * 64,
        "reviewer_id": "reviewer@example.com",
        "reviewed_at": "2026-08-02T15:30:00+09:00",
        "view_counts": {"PASS": 9, "FAIL": 0, "NOT_RUN": 0},
        "open_finding_count": 0,
    }
    assert dump_bytes(document) == dump_bytes(
        grist_qa_status_document(artifact, "e" * 64)
    )
