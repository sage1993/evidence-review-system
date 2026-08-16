from evidence_review.contracts.common import BBox, Citation
from evidence_review.contracts.evidence import EvidenceRecord
from evidence_review.contracts.review import Claim
from evidence_review.retrieval.claims import validate_claims


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


def _record(evidence_id: str) -> EvidenceRecord:
    return EvidenceRecord(
        evidence_id=evidence_id,
        document_id="DOC",
        revision_id="REV",
        page_number=1,
        element_id=evidence_id,
        evidence_type="clause",
        bbox=BBox(left=0, bottom=0, right=10, top=10),
        source_hash="a" * 64,
    )


def test_claim_validator_rejects_missing_issue_ids_for_issue_aware_citations() -> None:
    issues = validate_claims(
        (Claim("CL-1", "결과", ("CIT-1",)),),
        (_citation("CIT-1", "E-1"),),
        (_record("E-1"),),
        citation_issue_ids={"CIT-1": ("I1",)},
    )
    assert [issue.code for issue in issues] == ["UNRELATED_CLAIM"]


def test_claim_validator_rejects_cross_issue_citation() -> None:
    issues = validate_claims(
        (Claim("CL-1", "결과", ("CIT-2",), issue_ids=("I1",)),),
        (_citation("CIT-2", "E-2"),),
        (_record("E-2"),),
        citation_issue_ids={"CIT-2": ("I2",)},
        valid_issue_ids=("I1", "I2"),
    )
    assert [issue.code for issue in issues] == ["CROSS_ISSUE_CITATION"]


def test_claim_validator_rejects_unknown_claim_issue() -> None:
    issues = validate_claims(
        (Claim("CL-1", "결과", ("CIT-1",), issue_ids=("I9",)),),
        (_citation("CIT-1", "E-1"),),
        (_record("E-1"),),
        citation_issue_ids={"CIT-1": ("I1",)},
        valid_issue_ids=("I1", "I2"),
    )
    assert [issue.code for issue in issues] == ["UNKNOWN_CLAIM_ISSUE"]


def test_claim_validator_accepts_overlapping_issue_lineage() -> None:
    issues = validate_claims(
        (Claim("CL-1", "결과", ("CIT-1",), issue_ids=("I1",)),),
        (_citation("CIT-1", "E-1"),),
        (_record("E-1"),),
        citation_issue_ids={"CIT-1": ("I1", "I2")},
        valid_issue_ids=("I1", "I2"),
    )
    assert issues == ()
