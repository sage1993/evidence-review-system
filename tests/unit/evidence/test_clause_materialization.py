from __future__ import annotations

from evidence_review.evidence.clause_materialization import derive_legal_clauses


def _element(element_id: str, order: int, text: str) -> dict[str, object]:
    return {
        "id": element_id,
        "revision_id": "REV-1",
        "page_number": 5,
        "parser_order": order,
        "raw_text": text,
        "normalized_text": text,
    }


def test_derives_article_paragraphs_and_source_lineage_from_parser_elements() -> None:
    result = derive_legal_clauses(
        (
            _element("E-1", 0, "제13조(주차장 설치기준 완화)"),
            _element(
                "E-2",
                1,
                "① 사업시행자는 임대형기숙사를 제외한 안심주택인 경우 주차장을 설치하여야 한다.",
            ),
            _element(
                "E-3",
                2,
                "② 사업시행자는 임대형기숙사인 경우 별표 2에 따라 주차장을 설치하여야 한다.",
            ),
            _element(
                "E-4",
                3,
                "③ 복합으로 계획하는 경우 주택용도에 따라 제1항 및 제2항을 각각 적용한다.",
            ),
            _element(
                "E-5",
                4,
                "④ 지구단위계획으로 주차장 설치기준을 완화하여 적용할 수 있다.",
            ),
        )
    )

    assert [clause.structural_key for clause in result.clauses] == [
        "제13조#1",
        "제13조#2",
        "제13조#3",
        "제13조#4",
    ]
    assert all(clause.revision_id == "REV-1" for clause in result.clauses)
    assert {link.relation_type for link in result.links} >= {
        "source_element",
        "next_sibling",
        "previous_sibling",
    }
    assert any(
        link.source_id == result.clauses[1].id
        and link.target_id == "E-3"
        and link.relation_type == "source_element"
        for link in result.links
    )


def test_splits_multiple_paragraphs_inside_one_parser_element() -> None:
    result = derive_legal_clauses(
        (
            _element(
                "E-1",
                0,
                "제13조(주차장 설치기준 완화) ① 첫째 기준. ② 둘째 기준. ③ 셋째 기준.",
            ),
        )
    )

    assert [clause.structural_key for clause in result.clauses] == [
        "제13조#1",
        "제13조#2",
        "제13조#3",
    ]
    assert all(clause.source_element_ids == ("E-1",) for clause in result.clauses)


def test_derives_operational_standard_numbering_without_materializing_plain_prose() -> None:
    result = derive_legal_clauses(
        (
            _element("E-1", 0, "일반 설명 문장이다."),
            _element("E-2", 1, "2-1-2. 사업대상지의 범위"),
            _element("E-3", 2, "역의 각 승강장 경계로부터 250미터 이내로 한다."),
        )
    )

    assert len(result.clauses) == 1
    assert result.clauses[0].structural_key == "2-1-2"
    assert "250미터" in result.clauses[0].normalized_text
    assert result.clauses[0].source_element_ids == ("E-2", "E-3")


def test_clause_ids_are_stable_for_identical_source_content() -> None:
    elements = (
        _element("E-1", 0, "제13조(주차장 설치기준 완화)"),
        _element("E-2", 1, "① 주차장을 설치하여야 한다."),
    )

    left = derive_legal_clauses(elements)
    right = derive_legal_clauses(elements)

    assert [clause.id for clause in left.clauses] == [clause.id for clause in right.clauses]
