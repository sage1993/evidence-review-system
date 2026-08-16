import pytest

from evidence_review.contracts.common import BBox, Citation
from evidence_review.llm_layer.track_a import (
    EvidenceExcerpt,
    build_track_a_bundle,
    validate_track_a_output,
)
from evidence_review.llm_layer.validators import validate_track_a_integrity


def _citation(citation_id: str, evidence_id: str) -> Citation:
    return Citation(
        citation_id=citation_id,
        document_id="DOC",
        revision_id="REV",
        page_number=1,
        evidence_id=evidence_id,
        bbox=BBox(left=0, bottom=0, right=10, top=10),
        source_hash="a" * 64,
    )


def _bundle():
    return build_track_a_bundle(
        run_id="RUN-1",
        question="복합 검토",
        inputs={},
        evidence=(
            EvidenceExcerpt(
                citation=_citation("CIT-I1", "E-I1"),
                text="이슈 1 근거",
                issue_ids=("I1",),
                role="rule",
            ),
            EvidenceExcerpt(
                citation=_citation("CIT-I2", "E-I2"),
                text="이슈 2 근거",
                issue_ids=("I2",),
                role="rule",
            ),
        ),
        rules=(),
        calculations=(),
    )


def _payload(*, issue_ids, citation_ids):
    return {
        "run_id": "RUN-1",
        "claims": [
            {
                "claim_id": "CL-1",
                "text": "검토 결과",
                "issue_ids": issue_ids,
                "citation_ids": citation_ids,
                "numeric_tokens": [],
                "calculation_result_ids": [],
                "rule_references": [],
            }
        ],
        "citations": citation_ids,
        "missing_inputs": [],
        "exceptions": [],
        "conflicts": [],
        "explanation": "설명",
    }


def test_track_a_claim_requires_issue_ids_when_bundle_has_issue_aware_evidence() -> None:
    with pytest.raises(ValueError, match="UNRELATED_CLAIM"):
        validate_track_a_output(
            _payload(issue_ids=[], citation_ids=["CIT-I1"]),
            _bundle(),
        )


def test_track_a_rejects_unknown_claim_issue() -> None:
    with pytest.raises(ValueError, match="UNKNOWN_CLAIM_ISSUE"):
        validate_track_a_output(
            _payload(issue_ids=["I9"], citation_ids=["CIT-I1"]),
            _bundle(),
        )


def test_track_a_rejects_cross_issue_citation() -> None:
    with pytest.raises(ValueError, match="CROSS_ISSUE_CITATION"):
        validate_track_a_output(
            _payload(issue_ids=["I1"], citation_ids=["CIT-I2"]),
            _bundle(),
        )


def test_track_a_accepts_claim_when_issue_and_citation_lineage_overlap() -> None:
    bundle = _bundle()
    validated = validate_track_a_output(
        _payload(issue_ids=["I1"], citation_ids=["CIT-I1"]),
        bundle,
    )

    validate_track_a_integrity(validated, bundle)
    assert validated.draft.claims[0].issue_ids == ("I1",)


def test_track_a_integrity_rejects_multi_issue_claim_with_partial_citation_coverage() -> None:
    bundle = _bundle()
    validated = validate_track_a_output(
        _payload(issue_ids=["I1", "I2"], citation_ids=["CIT-I1"]),
        bundle,
    )

    with pytest.raises(ValueError, match="UNSUPPORTED_CLAIM_ISSUE.*I2"):
        validate_track_a_integrity(validated, bundle)


def test_track_a_rejects_issue_claim_without_citations_at_structure_boundary() -> None:
    with pytest.raises(ValueError, match="claim CL-1 requires at least one citation"):
        validate_track_a_output(
            _payload(issue_ids=["I1"], citation_ids=[]),
            _bundle(),
        )


def test_track_a_integrity_accepts_multi_issue_claim_when_each_issue_is_cited() -> None:
    bundle = _bundle()
    validated = validate_track_a_output(
        _payload(issue_ids=["I1", "I2"], citation_ids=["CIT-I1", "CIT-I2"]),
        bundle,
    )

    validate_track_a_integrity(validated, bundle)
