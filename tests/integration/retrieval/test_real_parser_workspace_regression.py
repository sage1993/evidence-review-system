from __future__ import annotations

from pathlib import Path

from evidence_review.contracts.question_plan import decode_question_plan
from evidence_review.evidence.clause_rebuild import ensure_clause_index
from evidence_review.evidence.ingest import EvidenceSnapshot, ingest_snapshot
from evidence_review.evidence.store import EvidenceStore
from evidence_review.retrieval.coverage import evaluate_issue_coverage
from evidence_review.retrieval.index import build_fts_index
from evidence_review.retrieval.issue_bundle import retrieve_issue_bundle


def _snapshot() -> EvidenceSnapshot:
    texts = (
        "2-1-2. 역세권 사업대상지",
        "역의 각 승강장 경계로부터 직각으로 250미터 이내로 한다.",
        (
            "통합심의위원회의 심의를 거쳐 역의 각 승강장 경계 및 출입구로부터 "
            "350미터 이내의 토지를 사업대상지로 지정할 수 있다."
        ),
        "제13조(주차장 설치기준 완화)",
        (
            "① 사업시행자는 임대형기숙사를 제외한 안심주택인 경우 "
            "주택건설기준 등에 관한 규정에 따라 주차장을 설치하여야 한다."
        ),
        (
            "② 사업시행자는 임대형기숙사인 경우 서울특별시 주차장 설치 및 "
            "관리 조례 별표 2에 따라 주차장을 설치하여야 한다."
        ),
        (
            "③ 안심주택을 복합으로 계획하는 경우 주택용도에 따라 "
            "제1항 및 제2항을 각각 적용한다."
        ),
        (
            "④ 시장은 원활한 교통소통 또는 보행환경 조성을 위하여 "
            "지구단위계획으로 주차장 설치기준을 완화하여 적용할 수 있다."
        ),
    )
    return EvidenceSnapshot(
        documents=({"id": "DOC-1", "title": "서울특별시 안심주택 기준"},),
        revisions=(
            {
                "id": "REV-1",
                "document_id": "DOC-1",
                "source_hash": "a" * 64,
                "byte_size": 1000,
                "page_count": 1,
            },
        ),
        pages=(
            {
                "id": "P-1",
                "revision_id": "REV-1",
                "page_number": 1,
                "width": 595.0,
                "height": 842.0,
            },
        ),
        elements=tuple(
            {
                "id": f"E-{index:02d}",
                "revision_id": "REV-1",
                "page_id": "P-1",
                "page_number": 1,
                "element_type": "paragraph",
                "raw_json": {"text": text},
                "raw_text": text,
                "normalized_text": text,
                "raw_payload_hash": f"{index:x}".zfill(64),
                "bbox": [10.0, 10.0 + index * 30, 550.0, 30.0 + index * 30],
                "parser_order": index,
            }
            for index, text in enumerate(texts, start=1)
        ),
    )


def _plan():
    question = "역세권 300m 부지와 복합 안심주택의 주차기준을 검토해줘."
    return decode_question_plan(
        {
            "format": "evidence-review/question-plan",
            "version": 2,
            "original_question": question,
            "facts": [
                {
                    "id": "F1",
                    "text": "대상 부지는 승강장 경계에서 300m 떨어져 있다.",
                    "polarity": "positive",
                }
            ],
            "assumptions": [],
            "issues": [
                {
                    "id": issue_id,
                    "question": issue_question,
                    "depends_on": [],
                    "required_evidence_roles": ["rule"],
                }
                for issue_id, issue_question in (
                    ("I2", "300m 부지의 역세권 적용 기준은 무엇인가?"),
                    ("I3", "공공지원민간임대주택의 주차기준은 무엇인가?"),
                    ("I4", "임대형기숙사와 복합계획의 주차기준은 무엇인가?"),
                    ("I7", "지구단위계획 주차완화 요건은 무엇인가?"),
                )
            ],
            "legal_anchors": [],
            "search_requests": [
                {
                    "id": "S2",
                    "issue_ids": ["I2"],
                    "text": "역세권 승강장 경계 300m 사업대상지 면적 기준",
                    "kind": "concept_relation",
                    "source": "planner",
                    "role": "rule",
                },
                {
                    "id": "S3",
                    "issue_ids": ["I3"],
                    "text": "공공지원민간임대주택 주차장 설치기준",
                    "kind": "concept_relation",
                    "source": "planner",
                    "role": "rule",
                },
                {
                    "id": "S4",
                    "issue_ids": ["I4"],
                    "text": "임대형기숙사 주차장 설치기준 복합 적용",
                    "kind": "concept_relation",
                    "source": "planner",
                    "role": "rule",
                },
                {
                    "id": "S7",
                    "issue_ids": ["I7"],
                    "text": "지구단위계획 주차장 설치기준 추가 완화 요건 절차",
                    "kind": "concept_relation",
                    "source": "planner",
                    "role": "rule",
                },
            ],
        },
        question,
    )


def test_element_only_workspace_recovers_real_retrieval_gaps(tmp_path: Path) -> None:
    with EvidenceStore(tmp_path / "evidence.sqlite", create=True) as store:
        ingest_snapshot(store, _snapshot())
        connection = store.require_connection()
        build_fts_index(connection)
        assert connection.execute("SELECT COUNT(*) FROM clauses").fetchone() == (0,)

        assert ensure_clause_index(connection) is True
        bundle = retrieve_issue_bundle(connection, _plan())
        coverage = evaluate_issue_coverage(_plan(), bundle)

        assert connection.execute("SELECT COUNT(*) FROM clauses").fetchone()[0] >= 5
        assert connection.execute(
            "SELECT COUNT(*) FROM clause_retrieval_records"
        ).fetchone()[0] >= 5
        assert connection.execute("SELECT COUNT(*) FROM clause_fts").fetchone()[0] >= 5

    for issue_id in ("I2", "I3", "I4", "I7"):
        support = coverage.by_issue_id(issue_id)
        assert support.evidence_ids
        assert "RETRIEVAL_MISS" not in support.gap_codes

    i2_traces = [
        trace for trace in bundle.fallback_traces if trace.issue_id == "I2"
    ]
    assert i2_traces[0].derived_query == (
        "역세권 승강장 경계 300m 사업대상지 면적 기준"
    )
    assert any(
        "300m" not in trace.derived_query and trace.hit_count > 0
        for trace in i2_traces
    )

    i4_evidence = {
        hit.text
        for hit in bundle.selected_evidence
        if "임대형기숙사" in hit.text or "복합" in hit.text
    }
    assert any("임대형기숙사" in text for text in i4_evidence)
    assert any("복합" in text for text in i4_evidence)
