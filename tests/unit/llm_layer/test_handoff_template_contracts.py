from __future__ import annotations

from pathlib import Path

import evidence_review.llm_layer


def _template(name: str) -> str:
    root = Path(evidence_review.llm_layer.__file__).parent / "templates"
    return (root / name).read_text(encoding="utf-8")


def test_visual_analysis_template_declares_strict_scalar_and_geometry_contracts() -> None:
    text = _template("visual-analysis.md")

    assert "`raw_value` must be a JSON string or null" in text
    assert "`normalized_candidate` must be a JSON string or null" in text
    assert "must never be an object, array, number, or boolean" in text
    assert "final point must exactly equal the first point" in text
    assert "`asset_path` is relative to the review workspace" in text


def test_question_planner_template_declares_exact_v2_shape() -> None:
    text = _template("question-planner.md")

    for field in (
        "format",
        "version",
        "original_question",
        "facts",
        "assumptions",
        "issues",
        "legal_anchors",
        "search_requests",
    ):
        assert f'"{field}"' in text
    for value in (
        "positive",
        "negative",
        "phrase",
        "legal_anchor",
        "concept_relation",
        "counterfactual",
        "supporting_fact",
        "rule",
    ):
        assert value in text
    assert "legal anchors are retrieval hypotheses" in text.lower()
    assert "not evidence" in text.lower()


def test_track_b_template_declares_exact_audit_and_overall_contract() -> None:
    text = _template("track-b.md")

    for field in (
        "run_id",
        "claim_audits",
        "overall_disposition",
        "claim_id",
        "disposition",
        "finding_codes",
        "notes",
    ):
        assert field in text
    for value in ("ACCEPT", "REJECT", "INCOMPLETE"):
        assert value in text
    assert "exactly once" in text.lower()
    assert "any `REJECT`" in text
    assert "any `INCOMPLETE`" in text
    assert "ACCEPT" in text and "finding_codes" in text
