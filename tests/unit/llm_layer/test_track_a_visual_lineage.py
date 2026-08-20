import pytest

from evidence_review.contracts.common import BBox, Citation
from evidence_review.llm_layer.track_a import (
    EvidenceExcerpt,
    build_track_a_bundle,
    validate_track_a_output,
)


def _citation() -> Citation:
    return Citation(
        citation_id="CIT-I1",
        document_id="DOC",
        revision_id="REV",
        page_number=1,
        evidence_id="E-I1",
        bbox=BBox(left=0, bottom=0, right=10, top=10),
        source_hash="a" * 64,
    )


def _bundle(*, candidate_issue: str = "I1"):
    return build_track_a_bundle(
        run_id="RUN-1",
        question="도면과 기준을 함께 검토",
        inputs={
            "case_visual_context": {
                "attachments": [],
                "drawing_candidates": [{"candidate_id": "CAND-1"}],
                "visual_status": "VISUAL_ANALYSIS_VALIDATED",
                "reason_codes": [],
                "candidate_lineage": [
                    {"candidate_id": "CAND-1", "issue_ids": [candidate_issue]}
                ],
            }
        },
        evidence=(
            EvidenceExcerpt(
                citation=_citation(),
                text="이슈 1의 권위 근거",
                issue_ids=("I1",),
                role="rule",
            ),
        ),
        rules=(),
        calculations=(),
    )


def _payload(*, candidate_ids: list[str], citation_ids: list[str] | None = None):
    citations = ["CIT-I1"] if citation_ids is None else citation_ids
    return {
        "run_id": "RUN-1",
        "claims": [
            {
                "claim_id": "CL-1",
                "text": "도면 관찰과 권위 근거를 함께 검토했다.",
                "issue_ids": ["I1"],
                "citation_ids": citations,
                "numeric_tokens": [],
                "calculation_result_ids": [],
                "rule_references": [],
                "drawing_candidate_ids": candidate_ids,
            }
        ],
        "citations": citations,
        "missing_inputs": [],
        "exceptions": [],
        "conflicts": [],
        "explanation": "설명",
    }


def test_track_a_accepts_known_visual_candidate_for_same_issue() -> None:
    validated = validate_track_a_output(_payload(candidate_ids=["CAND-1"]), _bundle())

    assert validated.claim_references[0].drawing_candidate_ids == ("CAND-1",)


def test_track_a_rejects_unknown_visual_candidate() -> None:
    with pytest.raises(ValueError, match="UNKNOWN_DRAWING_CANDIDATE"):
        validate_track_a_output(_payload(candidate_ids=["CAND-9"]), _bundle())


def test_track_a_rejects_cross_issue_visual_candidate() -> None:
    with pytest.raises(ValueError, match="CROSS_ISSUE_DRAWING_CANDIDATE"):
        validate_track_a_output(
            _payload(candidate_ids=["CAND-1"]),
            _bundle(candidate_issue="I2"),
        )


def test_visual_candidate_cannot_replace_normative_citation() -> None:
    with pytest.raises(ValueError, match="requires at least one citation"):
        validate_track_a_output(
            _payload(candidate_ids=["CAND-1"], citation_ids=[]),
            _bundle(),
        )


def test_existing_track_a_payload_without_visual_field_remains_valid() -> None:
    payload = _payload(candidate_ids=[])
    payload["claims"][0].pop("drawing_candidate_ids")

    validated = validate_track_a_output(payload, _bundle())

    assert validated.claim_references[0].drawing_candidate_ids == ()
