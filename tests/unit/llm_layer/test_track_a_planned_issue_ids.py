import pytest

from evidence_review.contracts.common import BBox, Citation
from evidence_review.llm_layer.track_a import (
    EvidenceExcerpt,
    build_track_a_bundle,
    validate_track_a_output,
)


def _citation() -> Citation:
    return Citation(
        citation_id="CIT-1",
        document_id="DOC",
        revision_id="REV",
        page_number=1,
        evidence_id="E1",
        bbox=BBox(left=0, bottom=0, right=10, top=10),
        source_hash="a" * 64,
    )


def test_track_a_rejects_issue_id_not_declared_by_question_plan() -> None:
    bundle = build_track_a_bundle(
        run_id="RUN-1",
        question="복합 검토",
        inputs={
            "question_plan": {
                "issues": [
                    {
                        "id": "SITE_AREA",
                        "question": "최소 면적 기준은 무엇인가?",
                        "depends_on": [],
                        "required_evidence_roles": ["rule"],
                    }
                ]
            }
        },
        evidence=(
            EvidenceExcerpt(
                citation=_citation(),
                text="근거",
                issue_ids=("I8",),
                role="rule",
            ),
        ),
        rules=(),
        calculations=(),
    )
    output = {
        "run_id": "RUN-1",
        "claims": [
            {
                "claim_id": "CL-1",
                "text": "검토 결과",
                "issue_ids": ["I8"],
                "citation_ids": ["CIT-1"],
                "numeric_tokens": [],
                "calculation_result_ids": [],
                "rule_references": [],
            }
        ],
        "citations": ["CIT-1"],
        "missing_inputs": [],
        "exceptions": [],
        "conflicts": [],
        "explanation": "설명",
    }

    with pytest.raises(ValueError, match="UNKNOWN_CLAIM_ISSUE"):
        validate_track_a_output(output, bundle)
