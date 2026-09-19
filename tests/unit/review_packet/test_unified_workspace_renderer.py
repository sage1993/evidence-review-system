from __future__ import annotations

from copy import deepcopy
from pathlib import Path

from evidence_review.review_packet.html_renderer import render_review_html


def _generic_model() -> dict[str, object]:
    return {
        "run_id": "RUN-SYNTHETIC-I1-I7",
        "status": "PARTIALLY_RESOLVED",
        "display_status": "PARTIALLY_RESOLVED",
        "human_decision": None,
        "question": "복합질문에 대한 종합 검토",
        "answer_summary": None,
        "claims": [],
        "calculations": [],
        "rules": [],
        "missing_inputs": [],
        "exceptions": [],
        "conflicts": [],
        "abstention_reasons": [],
        "issue_results": [
            {
                "issue_id": "I1",
                "status": "RESOLVED",
                "covered_facet_ids": ["minimum-area-threshold"],
                "missing_facet_ids": [],
                "comparison_ids": [],
                "gap_codes": [],
            },
            {
                "issue_id": "I2",
                "status": "CONDITIONAL",
                "covered_facet_ids": [
                    "minimum-area-threshold",
                    "distance-normal-threshold",
                    "distance-expanded-threshold",
                ],
                "missing_facet_ids": [],
                "comparison_ids": ["CMP-1", "CMP-2", "CMP-3"],
                "gap_codes": [],
            },
            *[
                {
                    "issue_id": f"I{index}",
                    "status": "SOURCE_MISSING",
                    "covered_facet_ids": [],
                    "missing_facet_ids": [f"facet-{index}"],
                    "comparison_ids": [],
                    "gap_codes": ["SOURCE_NOT_INGESTED"],
                }
                for index in range(3, 8)
            ],
        ],
        "decision": {
            "allowed_values": [
                "SATISFIED",
                "NOT_SATISFIED",
                "CONDITIONAL",
                "ADDITIONAL_REVIEW_REQUIRED",
            ],
            "human_decision": None,
            "packet_sha256": "a" * 64,
        },
        "metadata": {},
        "summary": {
            "citation_count": 0,
            "missing_input_count": 0,
            "exception_count": 0,
            "conflict_count": 0,
        },
    }


def test_generic_formal_review_uses_unified_reference_only_workspace_shell(
    tmp_path: Path,
) -> None:
    html = render_review_html(_generic_model(), tmp_path)

    assert 'data-review-workspace="unified"' in html
    assert 'data-review-workspace-mode="reference-only"' in html
    assert 'data-has-reference="false"' in html
    assert 'data-has-subject="false"' in html
    assert 'data-has-comparison="false"' in html
    assert 'id="evidence-viewer"' in html
    assert 'id="decision-form"' in html


def test_generic_formal_review_projects_issue_results_and_conclusion(
    tmp_path: Path,
) -> None:
    html = render_review_html(_generic_model(), tmp_path)

    assert 'id="review-issue-results"' in html
    assert "I1" in html
    assert "I2" in html
    assert "I7" in html
    assert "조건부" in html
    assert "전체 검토 상태" in html
    assert "질문에 대한 결론이 제공되지 않았습니다." not in html


def test_workspace_shell_uses_capabilities_without_switching_template_modes(
    tmp_path: Path,
) -> None:
    model = _generic_model()
    model["capabilities"] = {
        "has_reference": True,
        "has_subject": True,
        "has_comparison": True,
    }

    html = render_review_html(model, tmp_path)

    assert 'data-review-workspace-mode="reference-only"' in html
    assert 'data-has-reference="true"' in html
    assert 'data-has-subject="true"' in html
    assert 'data-has-comparison="true"' in html


def test_generic_formal_review_counts_issue_level_source_gaps(
    tmp_path: Path,
) -> None:
    html = render_review_html(_generic_model(), tmp_path)

    assert '<dt>추가 확인</dt><dd>5 건</dd>' in html
    assert "I3" in html and "참조 법령 원문 미수록" in html
    assert "SOURCE_NOT_INGESTED" in html
    assert "추가 확인 0 건" not in html


def test_renderer_does_not_mutate_machine_authority_fields(tmp_path: Path) -> None:
    model = _generic_model()
    before = deepcopy(model)

    render_review_html(model, tmp_path)

    assert model == before
    assert model["status"] == "PARTIALLY_RESOLVED"
    assert model["human_decision"] is None


def test_renderer_loads_workspace_v2_tokens_into_the_document_shell() -> None:
    html = render_review_html(_generic_model(), Path(":memory:"))

    assert "/* Review Workspace v2 tokens */" in html
    assert "--space-xs: 4px" in html
    assert "font-size: 15px" in html
    assert ".app-shell" in html and "max-width: none" in html
