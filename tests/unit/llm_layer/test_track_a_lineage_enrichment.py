from evidence_review.contracts.common import BBox, Citation
from evidence_review.llm_layer.track_a import EvidenceExcerpt, build_track_a_bundle


def _citation() -> Citation:
    return Citation(
        citation_id="CIT-E1",
        document_id="DOC",
        revision_id="REV",
        page_number=1,
        evidence_id="E1",
        bbox=BBox(left=0, bottom=0, right=10, top=10),
        source_hash="a" * 64,
    )


def test_build_track_a_bundle_enriches_evidence_from_retrieval_lineage() -> None:
    bundle = build_track_a_bundle(
        run_id="RUN-1",
        question="질문",
        inputs={
            "retrieval_lineage": [
                {
                    "evidence_id": "E1",
                    "citation_id": "CIT-E1",
                    "matches": [
                        {
                            "search_request_id": "S1",
                            "issue_ids": ["I1"],
                            "query_text": "주차장 설치기준",
                            "origin": "llm",
                            "role": "rule",
                            "fallback_stage": "PHRASE",
                            "retrieval_query": "주차장 설치기준",
                        }
                    ],
                }
            ]
        },
        evidence=(EvidenceExcerpt(citation=_citation(), text="근거"),),
        rules=(),
        calculations=(),
    )

    assert bundle.evidence[0].issue_ids == ("I1",)
    assert bundle.evidence[0].role == "rule"
