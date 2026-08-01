import json
from pathlib import Path

import pytest

from ansim_review.rule_engine.manifest import load_active_rules
from ansim_review.rule_engine.promotion import promote_candidate


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


def test_candidate_requires_human_identity_and_review_date(tmp_path: Path) -> None:
    candidate = tmp_path / "rules" / "candidates" / "candidate.json"
    candidate.parent.mkdir(parents=True)
    candidate.write_text(json.dumps(_candidate()), encoding="utf-8")
    approved = tmp_path / "rules" / "approved"
    manifest = tmp_path / "rules" / "manifests" / "active.json"

    with pytest.raises(ValueError, match="reviewer identity"):
        promote_candidate(candidate, approved, manifest, reviewer_id="", review_date="2026-08-01")
    with pytest.raises(ValueError, match="review date"):
        promote_candidate(candidate, approved, manifest, reviewer_id="reviewer", review_date="")


def test_promotion_preserves_candidate_and_only_manifested_rules_load(tmp_path: Path) -> None:
    candidate = tmp_path / "rules" / "candidates" / "candidate.json"
    candidate.parent.mkdir(parents=True)
    original = json.dumps(_candidate(), ensure_ascii=False, indent=2)
    candidate.write_text(original, encoding="utf-8")
    approved = tmp_path / "rules" / "approved"
    manifest = tmp_path / "rules" / "manifests" / "active.json"

    promoted = promote_candidate(
        candidate,
        approved,
        manifest,
        reviewer_id="test-reviewer",
        review_date="2026-08-01",
    )
    assert candidate.read_text(encoding="utf-8") == original
    assert promoted.name == "PROMOTION-TEST@1.0.0.json"
    rules = load_active_rules(tmp_path, manifest)
    assert [(rule.rule_id, rule.version) for rule in rules] == [("PROMOTION-TEST", "1.0.0")]

    unmanifested = approved / "UNMANIFESTED@1.0.0.json"
    unmanifested.write_text(promoted.read_text(encoding="utf-8"), encoding="utf-8")
    assert len(load_active_rules(tmp_path, manifest)) == 1


@pytest.mark.parametrize(
    "rule_id",
    ["../ESCAPE", "/tmp/ESCAPE", "C:\\tmp\\ESCAPE", "SUB/ESCAPE", "SUB\\ESCAPE"],
)
def test_promotion_rejects_rule_id_path_syntax_before_writing(
    tmp_path: Path, rule_id: str
) -> None:
    candidate_payload = _candidate()
    candidate_payload["rule_id"] = rule_id
    candidate = tmp_path / "rules" / "candidates" / "candidate.json"
    candidate.parent.mkdir(parents=True)
    candidate.write_text(json.dumps(candidate_payload), encoding="utf-8")
    approved = tmp_path / "rules" / "approved"
    manifest = tmp_path / "rules" / "manifests" / "active.json"

    with pytest.raises(ValueError, match="rule_id"):
        promote_candidate(
            candidate,
            approved,
            manifest,
            reviewer_id="test-reviewer",
            review_date="2026-08-01",
        )

    assert not approved.exists()
    assert not manifest.exists()
