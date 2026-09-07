import json
from pathlib import Path

import pytest

from evidence_review.rule_engine.promotion import approve_candidate, promote_candidate


def _candidate() -> dict[str, object]:
    return {
        "rule_id": "PROMOTION-TEST",
        "version": "1.0.0",
        "title": "승격 테스트",
        "input_schema": {"value": {"type": "integer", "required": True}},
        "source_citations": [
            {
                "citation_id": "C-PROMOTE",
                "document_id": "LAW1",
                "revision_id": "REV-1",
                "page_number": 1,
                "evidence_id": "E-PROMOTE",
                "bbox": [0, 0, 1, 1],
                "source_hash": "a" * 64,
            }
        ],
        "human_decision_required": True,
        "expression": {
            "compare": {
                "operator": "gte",
                "left": {"input": "value"},
                "right": {"literal": 1},
            }
        },
    }


def _write_candidate(tmp_path: Path, payload: dict[str, object] | None = None) -> Path:
    candidate = tmp_path / "rules" / "candidates" / "candidate.json"
    candidate.parent.mkdir(parents=True)
    candidate.write_text(
        json.dumps(payload or _candidate(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return candidate


def test_candidate_requires_human_identity_and_review_date(tmp_path: Path) -> None:
    candidate = _write_candidate(tmp_path)
    approved = tmp_path / "rules" / "approved"

    with pytest.raises(ValueError, match="reviewer identity"):
        approve_candidate(
            candidate,
            approved,
            reviewer_id="",
            review_date="2026-08-01",
        )
    with pytest.raises(ValueError, match="review date"):
        approve_candidate(
            candidate,
            approved,
            reviewer_id="reviewer",
            review_date="",
        )


def test_approved_copy_preserves_exact_candidate_bytes_without_manifest(
    tmp_path: Path,
) -> None:
    candidate = _write_candidate(tmp_path)
    approved_dir = tmp_path / "rules" / "approved"
    manifest = tmp_path / "rules" / "manifests" / "active.json"

    approved = approve_candidate(
        candidate,
        approved_dir,
        reviewer_id="test-reviewer",
        review_date="2026-08-01",
    )

    assert approved.name == "PROMOTION-TEST@1.0.0.json"
    assert approved.read_bytes() == candidate.read_bytes()
    assert not manifest.exists()


def test_direct_promotion_is_disabled_before_any_write(tmp_path: Path) -> None:
    candidate = _write_candidate(tmp_path)
    approved = tmp_path / "rules" / "approved"
    manifest = tmp_path / "rules" / "manifests" / "active.json"

    with pytest.raises(ValueError, match="direct active promotion is disabled"):
        promote_candidate(
            candidate,
            approved,
            manifest,
            reviewer_id="test-reviewer",
            review_date="2026-08-01",
        )

    assert not approved.exists()
    assert not manifest.exists()


@pytest.mark.parametrize(
    "rule_id",
    ["../ESCAPE", "/tmp/ESCAPE", "C:\\tmp\\ESCAPE", "SUB/ESCAPE", "SUB\\ESCAPE"],
)
def test_approval_rejects_rule_id_path_syntax_before_writing(
    tmp_path: Path,
    rule_id: str,
) -> None:
    payload = _candidate()
    payload["rule_id"] = rule_id
    candidate = _write_candidate(tmp_path, payload)
    approved = tmp_path / "rules" / "approved"

    with pytest.raises(ValueError, match="rule_id"):
        approve_candidate(
            candidate,
            approved,
            reviewer_id="test-reviewer",
            review_date="2026-08-01",
        )

    assert not approved.exists()


def test_approved_copy_is_create_only(tmp_path: Path) -> None:
    candidate = _write_candidate(tmp_path)
    approved_dir = tmp_path / "rules" / "approved"
    approved = approve_candidate(
        candidate,
        approved_dir,
        reviewer_id="test-reviewer",
        review_date="2026-08-01",
    )
    existing = approved.read_bytes()

    with pytest.raises(FileExistsError):
        approve_candidate(
            candidate,
            approved_dir,
            reviewer_id="test-reviewer",
            review_date="2026-08-01",
        )

    assert approved.read_bytes() == existing


def test_approval_rejects_linked_candidate(tmp_path: Path) -> None:
    candidate = _write_candidate(tmp_path)
    external = tmp_path / "external-candidate.json"
    external.write_bytes(candidate.read_bytes())
    candidate.unlink()
    try:
        candidate.symlink_to(external)
    except OSError as error:
        pytest.skip(f"symlink creation unavailable: {error}")

    with pytest.raises(ValueError, match="symlink|reparse"):
        approve_candidate(
            candidate,
            tmp_path / "rules" / "approved",
            reviewer_id="test-reviewer",
            review_date="2026-08-01",
        )
