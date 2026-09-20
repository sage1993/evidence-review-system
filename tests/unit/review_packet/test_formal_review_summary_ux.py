from __future__ import annotations

from pathlib import Path

from evidence_review.review_packet.render_decision import render_decision_form
from evidence_review.review_packet.render_summary import render_status_band, render_summary


def _model() -> dict[str, object]:
    return {
        "status": "ABSTAIN",
        "display_status": "REVIEW_COMPLETED",
        "human_decision": "ADDITIONAL_REVIEW_REQUIRED",
        "question": "필수 항목을 모두 확인할 수 있는가?",
        "answer_summary": None,
        "issue_results": [
            {
                "issue_id": "I-1",
                "status": "SOURCE_MISSING",
                "missing_facet_ids": ["site-area", "parking-count"],
                "gap_codes": ["SOURCE_NOT_INGESTED"],
            }
        ],
        "summary": {
            "citation_count": 2,
            "missing_input_count": 0,
            "exception_count": 0,
            "conflict_count": 0,
        },
        "decision": {
            "allowed_values": ["SATISFIED", "ADDITIONAL_REVIEW_REQUIRED"],
            "human_decision": "ADDITIONAL_REVIEW_REQUIRED",
            "packet_sha256": "a" * 64,
        },
    }


def test_status_band_keeps_machine_abstention_separate_from_recorded_decision() -> None:
    html = render_status_band(_model())

    assert "기계 검토 결과" in html
    assert "현재 자료로 판정할 수 없음" in html
    assert "검토 완료" not in html
    assert "ADDITIONAL_REVIEW_REQUIRED" not in html
    assert "전체 검토 상태: 현재 자료로 판정할 수 없음" in render_summary(_model())
    assert "전체 검토 상태: 검토 완료" not in render_summary(_model())


def test_summary_prominently_lists_packet_backed_missing_facets_and_gaps() -> None:
    html = render_summary(_model())

    assert 'id="summary-attention"' in html
    assert "I-1: 필수 검토 항목 미확인 (site-area)" in html
    assert '<p class="summary-attention-primary">I-1: 필수 검토 항목 미확인 (site-area)</p>' in html
    assert "I-1: 필수 검토 항목 미확인 (parking-count)" in html
    assert "I-1: 참조 법령 원문 미수록" in html
    assert '<details class="summary-attention-details">' in html
    assert "추가 확인 항목 2건 보기" in html
    assert '<dt>인용 근거</dt><dd>2건</dd>' in html
    assert '<dt>추가 확인 항목</dt><dd>3건</dd>' in html


def test_summary_includes_descriptive_packet_missing_inputs_as_attention_items() -> None:
    model = _model()
    model["missing_inputs"] = [
        "계산에 필요한 계수 값을 확인할 수 없습니다.",
        "납품 도면의 주차 대수 입력값을 확인할 수 없습니다.",
    ]

    html = render_summary(model)

    assert "계산에 필요한 계수 값을 확인할 수 없습니다." in html
    assert "납품 도면의 주차 대수 입력값을 확인할 수 없습니다." in html
    assert '<dt>추가 확인 항목</dt><dd>5건</dd>' in html


def test_persisted_decision_panel_calls_the_record_a_human_decision() -> None:
    html = render_decision_form(_model())

    assert "기록된 사람의 결정" in html


def test_status_refresh_never_replaces_the_machine_result_indicator() -> None:
    script = (
        Path(__file__).parents[3]
        / "src"
        / "evidence_review"
        / "review_packet"
        / "assets"
        / "review.js"
    ).read_text(encoding="utf-8")

    assert 'querySelectorAll("[data-display-status]:not([data-machine-status])")' in script
