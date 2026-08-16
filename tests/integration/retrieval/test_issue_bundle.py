from __future__ import annotations

from pathlib import Path

from evidence_review.contracts.question_plan import decode_question_plan
from evidence_review.evidence.ingest import EvidenceSnapshot, ingest_snapshot
from evidence_review.evidence.store import EvidenceStore
from evidence_review.retrieval.index import build_fts_index
from evidence_review.retrieval.issue_bundle import retrieve_issue_bundle
from evidence_review.retrieval.policy import RetrievalPolicy


def _element(evidence_id: str, text: str, order: int) -> dict[str, object]:
    return {
        "id": evidence_id,
        "revision_id": "REV-1",
        "page_id": "P-1",
        "page_number": 1,
        "element_type": "paragraph",
        "raw_json": {"text": text},
        "raw_text": text,
        "normalized_text": text,
        "raw_payload_hash": format(order + 1, "x")[-1] * 64,
        "bbox": [10.0, float(10 + order * 10), 500.0, float(18 + order * 10)],
        "parser_order": order,
    }


def _budget_snapshot() -> EvidenceSnapshot:
    clause_rows: list[dict[str, object]] = []
    elements: list[dict[str, object]] = []
    links: list[dict[str, object]] = []
    for index in range(1, 7):
        clause_id = f"C-B{index}"
        evidence_id = f"E-B{index}"
        text = f"공통 기준 세부사항 {index}"
        clause_rows.append(
            {
                "id": clause_id,
                "revision_id": "REV-1",
                "title": f"공통 기준 {index}",
                "raw_text": text,
                "normalized_text": text,
                "review_status": "AUTOMATIC",
            }
        )
        elements.append(_element(evidence_id, text, index - 1))
        links.append(
            {
                "id": f"L-B{index}",
                "source_id": clause_id,
                "target_id": evidence_id,
                "relation_type": "source_element",
            }
        )
    clause_rows.append(
        {
            "id": "C-EXACT",
            "revision_id": "REV-1",
            "title": "특별 기준",
            "raw_text": "특별 기준 적용",
            "normalized_text": "특별 기준 적용",
            "review_status": "AUTOMATIC",
        }
    )
    elements.append(_element("E-EXACT", "특별 기준 적용", 6))
    links.append(
        {
            "id": "L-EXACT",
            "source_id": "C-EXACT",
            "target_id": "E-EXACT",
            "relation_type": "source_element",
        }
    )
    return EvidenceSnapshot(
        documents=({"id": "DOC-1", "title": "테스트 기준"},),
        revisions=(
            {
                "id": "REV-1",
                "document_id": "DOC-1",
                "source_hash": "a" * 64,
                "byte_size": 100,
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
        elements=tuple(elements),
        clauses=tuple(clause_rows),
        links=tuple(links),
    )


def _two_issue_plan():
    question = "공통 기준과 특별 기준을 각각 검토해줘"
    return decode_question_plan(
        {
            "format": "evidence-review/question-plan",
            "version": 2,
            "original_question": question,
            "facts": [],
            "assumptions": [],
            "issues": [
                {
                    "id": "I1",
                    "question": "공통 기준은 무엇인가?",
                    "depends_on": [],
                    "required_evidence_roles": ["rule"],
                },
                {
                    "id": "I2",
                    "question": "특별 기준은 무엇인가?",
                    "depends_on": [],
                    "required_evidence_roles": ["rule"],
                },
            ],
            "legal_anchors": [],
            "search_requests": [
                {
                    "id": "S1",
                    "issue_ids": ["I1"],
                    "text": "공통 기준",
                    "kind": "concept_relation",
                    "source": "planner",
                    "role": "rule",
                },
                {
                    "id": "S2",
                    "issue_ids": ["I2"],
                    "text": "특별 기준",
                    "kind": "concept_relation",
                    "source": "planner",
                    "role": "rule",
                },
            ],
        },
        question,
    )


def test_broad_issue_cannot_starve_exact_other_issue(tmp_path: Path) -> None:
    with EvidenceStore(tmp_path / "evidence.sqlite", create=True) as store:
        ingest_snapshot(store, _budget_snapshot())
        connection = store.require_connection()
        build_fts_index(connection)

        bundle = retrieve_issue_bundle(
            connection,
            _two_issue_plan(),
            policy=RetrievalPolicy(
                per_issue_role_limit=2,
                global_candidate_cap=3,
                max_selected_evidence=3,
            ),
        )

    clause_ids = {candidate.clause.clause_id for candidate in bundle.candidates}
    broad = [candidate for candidate in bundle.candidates if "I1" in candidate.issue_ids]
    exact = next(
        candidate for candidate in bundle.candidates if candidate.clause.clause_id == "C-EXACT"
    )

    assert len(bundle.candidates) == 3
    assert len(broad) <= 2
    assert "C-EXACT" in clause_ids
    assert exact.issue_ids == ("I2",)
    assert "E-EXACT" in {hit.evidence_id for hit in bundle.selected_evidence}


def test_semantic_clause_dedupe_merges_issue_lineage(tmp_path: Path) -> None:
    snapshot = _budget_snapshot()
    shared = EvidenceSnapshot(
        documents=snapshot.documents,
        revisions=snapshot.revisions,
        pages=snapshot.pages,
        elements=(_element("E-SHARED", "주차장 설치기준 공통", 0),),
        clauses=(
            {
                "id": "C-SHARED",
                "revision_id": "REV-1",
                "title": "주차 공통기준",
                "raw_text": "주차장 설치기준 공통",
                "normalized_text": "주차장 설치기준 공통",
                "review_status": "AUTOMATIC",
            },
        ),
        links=(
            {
                "id": "L-SHARED",
                "source_id": "C-SHARED",
                "target_id": "E-SHARED",
                "relation_type": "source_element",
            },
        ),
    )
    question = "두 주차 쟁점을 검토해줘"
    plan = decode_question_plan(
        {
            "format": "evidence-review/question-plan",
            "version": 2,
            "original_question": question,
            "facts": [],
            "assumptions": [],
            "issues": [
                {
                    "id": "I1",
                    "question": "주차장 설치기준은?",
                    "depends_on": [],
                    "required_evidence_roles": ["rule"],
                },
                {
                    "id": "I2",
                    "question": "공통 적용기준은?",
                    "depends_on": [],
                    "required_evidence_roles": ["rule"],
                },
            ],
            "legal_anchors": [],
            "search_requests": [
                {
                    "id": "S1",
                    "issue_ids": ["I1"],
                    "text": "주차장 설치기준",
                    "kind": "concept_relation",
                    "source": "planner",
                    "role": "rule",
                },
                {
                    "id": "S2",
                    "issue_ids": ["I2"],
                    "text": "설치기준 공통",
                    "kind": "concept_relation",
                    "source": "planner",
                    "role": "rule",
                },
            ],
        },
        question,
    )
    with EvidenceStore(tmp_path / "shared.sqlite", create=True) as store:
        ingest_snapshot(store, shared)
        connection = store.require_connection()
        build_fts_index(connection)
        bundle = retrieve_issue_bundle(connection, plan)

    assert len(bundle.candidates) == 1
    candidate = bundle.candidates[0]
    assert candidate.clause.clause_id == "C-SHARED"
    assert candidate.issue_ids == ("I1", "I2")
    assert candidate.search_request_ids == ("S1", "S2")
    assert len(candidate.matches) == 2
    assert [hit.evidence_id for hit in bundle.selected_evidence] == ["E-SHARED"]


def test_query_budget_is_round_robin_across_required_roles(tmp_path: Path) -> None:
    question = "외부 사실과 규칙을 함께 확인해줘"
    requests = [
        ("S1", "supporting_fact", "외부 사실 첫번째"),
        ("S2", "supporting_fact", "외부 사실 두번째"),
        ("S3", "supporting_fact", "외부 사실 세번째"),
        ("S4", "rule", "적용 규칙 첫번째"),
        ("S5", "rule", "적용 규칙 두번째"),
    ]
    plan = decode_question_plan(
        {
            "format": "evidence-review/question-plan",
            "version": 2,
            "original_question": question,
            "facts": [],
            "assumptions": [],
            "issues": [
                {
                    "id": "I1",
                    "question": "외부 사실과 규칙은?",
                    "depends_on": [],
                    "required_evidence_roles": ["supporting_fact", "rule"],
                }
            ],
            "legal_anchors": [],
            "search_requests": [
                {
                    "id": request_id,
                    "issue_ids": ["I1"],
                    "text": text,
                    "kind": "concept_relation",
                    "source": "planner",
                    "role": role,
                }
                for request_id, role, text in requests
            ],
        },
        question,
    )
    with EvidenceStore(tmp_path / "query-budget.sqlite", create=True) as store:
        ingest_snapshot(store, _budget_snapshot())
        connection = store.require_connection()
        build_fts_index(connection)
        bundle = retrieve_issue_bundle(
            connection,
            plan,
            policy=RetrievalPolicy(max_queries_per_issue=2),
        )

    dropped = {
        (drop.issue_id, drop.search_request_id)
        for drop in bundle.budget_drops
        if drop.reason == "QUERY_BUDGET"
    }
    assert dropped == {("I1", "S2"), ("I1", "S3"), ("I1", "S5")}


def test_global_evidence_budget_is_enforced_after_clause_selection(tmp_path: Path) -> None:
    with EvidenceStore(tmp_path / "evidence-cap.sqlite", create=True) as store:
        ingest_snapshot(store, _budget_snapshot())
        connection = store.require_connection()
        build_fts_index(connection)
        bundle = retrieve_issue_bundle(
            connection,
            _two_issue_plan(),
            policy=RetrievalPolicy(
                per_issue_role_limit=2,
                global_candidate_cap=3,
                max_selected_evidence=1,
            ),
        )

    assert len(bundle.candidates) == 3
    assert len(bundle.selected_evidence) == 1
    assert sum(len(candidate.evidence) for candidate in bundle.candidates) == 1
    assert any(candidate.evidence_budget_limited for candidate in bundle.candidates)
