from __future__ import annotations

from pathlib import Path

import pytest

import evidence_review.llm_layer.track_a as track_a_module
from evidence_review.contracts.common import BBox, Citation
from evidence_review.contracts.review import Claim, TrackADraft
from evidence_review.llm_layer.track_a import (
    ClaimReferences,
    EvidenceExcerpt,
    ValidatedTrackA,
    build_track_a_bundle,
    validate_track_a_output,
)
from evidence_review.llm_layer.track_b import validate_track_b_output
from evidence_review.llm_layer.validators import validate_track_a_integrity
from evidence_review.math_engine.comparison import relation_holds


def _citation(citation_id: str = "C1", evidence_id: str = "E1") -> Citation:
    return Citation(
        citation_id=citation_id,
        document_id="DOC",
        revision_id="REV",
        page_number=1,
        evidence_id=evidence_id,
        bbox=BBox(left=0, bottom=0, right=10, top=10),
        source_hash="a" * 64,
    )


def _bundle(
    *,
    question: str,
    evidence_text: str,
    issue_ids: tuple[str, ...] = ("I1",),
):
    inputs = {
        "question_plan": {
            "issues": [{"id": issue_id} for issue_id in issue_ids],
            "facts": [
                {
                    "id": "F1",
                    "text": question,
                    "polarity": "positive",
                }
            ],
        }
    }
    return build_track_a_bundle(
        run_id="RUN-REGRESSION",
        question=question,
        inputs=inputs,
        evidence=(
            EvidenceExcerpt(
                citation=_citation(),
                text=evidence_text,
                issue_ids=("I1",),
                role="rule",
            ),
        ),
        rules=(),
        calculations=(),
    )


def _payload(
    *,
    claim_id: str,
    text: str,
    issue_ids: list[str] | None = None,
    numeric_tokens: list[str] | None = None,
) -> dict[str, object]:
    return {
        "run_id": "RUN-REGRESSION",
        "claims": [
            {
                "claim_id": claim_id,
                "text": text,
                "issue_ids": ["I1"] if issue_ids is None else issue_ids,
                "citation_ids": ["C1"],
                "numeric_tokens": [] if numeric_tokens is None else numeric_tokens,
                "calculation_result_ids": [],
                "rule_references": [],
            }
        ],
        "citations": ["C1"],
        "missing_inputs": [],
        "exceptions": [],
        "conflicts": [],
        "explanation": "회귀 검증",
    }


def test_af50_user_area_is_deterministically_below_rule_threshold() -> None:
    bundle = _bundle(
        question="대상 면적은 4,800㎡이다.",
        evidence_text="적용 기준은 5,000㎡ 이상이다.",
    )
    validated = validate_track_a_output(
        _payload(
            claim_id="CL-I1-1",
            text="4,800㎡는 5,000㎡ 미만이다.",
        ),
        bundle,
    )

    validate_track_a_integrity(validated, bundle)

    assert validated.draft.claims[0].numeric_tokens == ("4,800", "5,000")
    assert relation_holds("4,800", "<", "5,000") is True


def test_af50_false_numeric_relation_is_rejected() -> None:
    bundle = _bundle(
        question="대상 면적은 5,000㎡이다.",
        evidence_text="비교 기준은 4,800㎡이다.",
    )
    validated = validate_track_a_output(
        _payload(
            claim_id="CL-I1-1",
            text="5,000㎡는 4,800㎡ 미만이다.",
        ),
        bundle,
    )

    with pytest.raises(ValueError, match="CALCULATION_MISMATCH"):
        validate_track_a_integrity(validated, bundle)


def test_c20_claim_id_issue_mismatch_is_rejected_before_track_b() -> None:
    bundle = _bundle(
        question="이슈 1 검토",
        evidence_text="이슈 1 근거",
        issue_ids=("I1", "I3"),
    )

    with pytest.raises(ValueError, match="CLAIM_ISSUE_ID_MISMATCH"):
        validate_track_a_output(
            _payload(
                claim_id="CL-I3-1",
                text="이슈 1에 관한 주장",
                issue_ids=["I1"],
            ),
            bundle,
        )


def test_c20_track_b_cannot_accept_malformed_claim_lineage() -> None:
    malformed = ValidatedTrackA(
        draft=TrackADraft(
            run_id="RUN-REGRESSION",
            claims=(
                Claim(
                    claim_id="CL-I3-1",
                    text="잘못 연결된 주장",
                    citation_ids=("C1",),
                    issue_ids=("I1",),
                ),
            ),
            missing_inputs=(),
            exceptions=(),
            conflicts=(),
            explanation="회귀 검증",
        ),
        citation_ids=("C1",),
        calculation_result_ids=(),
        claim_references=(
            ClaimReferences(
                claim_id="CL-I3-1",
                calculation_result_ids=(),
                rule_references=(),
            ),
        ),
    )
    track_b = {
        "run_id": "RUN-REGRESSION",
        "claim_audits": [
            {
                "claim_id": "CL-I3-1",
                "disposition": "ACCEPT",
                "finding_codes": [],
                "notes": "",
            }
        ],
        "overall_disposition": "ACCEPT",
    }

    with pytest.raises(ValueError, match="CLAIM_ISSUE_ID_MISMATCH"):
        validate_track_b_output(track_b, malformed)


def test_e4f3_45_percent_is_below_strict_majority_threshold() -> None:
    bundle = _bundle(
        question="해당 비율은 45%이다.",
        evidence_text="과반은 50%를 초과해야 한다.",
    )
    validated = validate_track_a_output(
        _payload(
            claim_id="CL-I1-1",
            text="45%는 과반(50%)에 미달한다.",
        ),
        bundle,
    )

    validate_track_a_integrity(validated, bundle)

    assert validated.draft.claims[0].numeric_tokens == ("45%", "50%")
    assert relation_holds("45%", ">", "50%") is False


def test_korean_ordinal_category_claim_reaches_track_b_without_numeric_tokens() -> None:
    bundle = _bundle(
        question="대상지는 제2종일반주거지역이다.",
        evidence_text="대상지는 제2종일반주거지역이다.",
    )
    validated = validate_track_a_output(
        _payload(
            claim_id="CL-I1-1",
            text="대상지는 제2종일반주거지역이다.",
        ),
        bundle,
    )

    validate_track_a_integrity(validated, bundle)
    audit = validate_track_b_output(
        {
            "run_id": "RUN-REGRESSION",
            "claim_audits": [
                {
                    "claim_id": "CL-I1-1",
                    "disposition": "ACCEPT",
                    "finding_codes": [],
                    "notes": "",
                }
            ],
            "overall_disposition": "ACCEPT",
        },
        validated,
    )

    assert validated.draft.claims[0].numeric_tokens == ()
    assert audit.overall_disposition == "ACCEPT"


def test_numeric_tokens_are_inferred_only_when_omitted_or_empty() -> None:
    bundle = _bundle(
        question="대상 면적은 4,800㎡이다.",
        evidence_text="적용 기준은 5,000㎡ 이상이다.",
    )
    inferred = validate_track_a_output(
        _payload(
            claim_id="CL-I1-1",
            text="4,800㎡는 5,000㎡ 미만이다.",
            numeric_tokens=[],
        ),
        bundle,
    )
    wrong = validate_track_a_output(
        _payload(
            claim_id="CL-I1-2",
            text="4,800㎡는 5,000㎡ 미만이다.",
            numeric_tokens=["4,800"],
        ),
        bundle,
    )

    assert inferred.draft.claims[0].numeric_tokens == ("4,800", "5,000")
    with pytest.raises(ValueError, match="NUMERIC_TOKEN_MISMATCH"):
        validate_track_a_integrity(wrong, bundle)


def test_question_planner_contract_requires_atomic_mixed_polarity_facts() -> None:
    template = (
        Path(track_a_module.__file__).with_name("templates")
        / "question-planner.md"
    ).read_text(encoding="utf-8")

    assert "exactly one atomic proposition" in template
    assert "분양주택이 없다" in template
    assert "polarity=negative" in template
    assert "임대주택 전부를 어르신에게 공급한다" in template
    assert "polarity=positive" in template
