from ansim_review.contracts.common import BBox, Citation
from ansim_review.contracts.evidence import EvidenceRecord
from ansim_review.contracts.review import Claim
from ansim_review.retrieval.claims import validate_claims


def _evidence() -> EvidenceRecord:
    return EvidenceRecord(
        evidence_id="E1",
        document_id="LAW1",
        revision_id="LAW1-REV1",
        page_number=3,
        element_id="E1",
        evidence_type="clause",
        bbox=BBox(10.0, 20.0, 30.0, 40.0),
        source_hash="a" * 64,
        raw_text="기준 내용",
        normalized_text="기준 내용",
    )


def _citation(**overrides: object) -> Citation:
    values: dict[str, object] = {
        "citation_id": "C1",
        "document_id": "LAW1",
        "revision_id": "LAW1-REV1",
        "page_number": 3,
        "evidence_id": "E1",
        "bbox": BBox(10.005, 20.0, 30.0, 40.0),
        "source_hash": "a" * 64,
    }
    values.update(overrides)
    return Citation(**values)  # type: ignore[arg-type]


def _codes(
    claim: Claim,
    citation: Citation | None = None,
) -> tuple[str, ...]:
    issues = validate_claims(
        (claim,),
        () if citation is None else (citation,),
        (_evidence(),),
    )
    return tuple(issue.code for issue in issues)


def test_uncited_claim_is_rejected() -> None:
    assert _codes(Claim("CL1", "기준 사실", ())) == (
        "UNCITED_CLAIM",
    )


def test_page_mismatch_is_rejected() -> None:
    assert _codes(
        Claim("CL1", "기준 사실", ("C1",)),
        _citation(page_number=4),
    ) == ("CITATION_PAGE_MISMATCH",)


def test_source_hash_mismatch_is_rejected() -> None:
    assert _codes(
        Claim("CL1", "기준 사실", ("C1",)),
        _citation(source_hash="b" * 64),
    ) == ("SOURCE_HASH_MISMATCH",)


def test_bbox_tolerance_and_mismatch() -> None:
    assert _codes(
        Claim("CL1", "기준 사실", ("C1",)),
        _citation(),
    ) == ()
    assert _codes(
        Claim("CL1", "기준 사실", ("C1",)),
        _citation(bbox=BBox(10.011, 20.0, 30.0, 40.0)),
    ) == ("CITATION_BBOX_MISMATCH",)
