from __future__ import annotations

from evidence_review.evidence.legal_references import extract_legal_references


def test_extracts_article_paragraph_and_annex_references() -> None:
    text = (
        "「주택건설기준 등에 관한 규정」 제27조에 따라 설치한다. "
        "「서울특별시 주차장 설치 및 관리 조례」 제20조제1항 별표 2를 적용한다. "
        "「국토의 계획 및 이용에 관한 법률 시행령」 제46조제6항에 따른다."
    )

    references = extract_legal_references(text)

    assert [(item.authority_title, item.article, item.paragraph, item.annex) for item in references] == [
        ("주택건설기준 등에 관한 규정", "제27조", None, None),
        ("서울특별시 주차장 설치 및 관리 조례", "제20조", "제1항", "별표 2"),
        ("국토의 계획 및 이용에 관한 법률 시행령", "제46조", "제6항", None),
    ]


def test_deduplicates_identical_references_in_source_order() -> None:
    references = extract_legal_references(
        "「주차장법」 제19조를 적용하고 다시 「주차장법」 제19조를 확인한다."
    )

    assert len(references) == 1
    assert references[0].authority_title == "주차장법"
    assert references[0].article == "제19조"
