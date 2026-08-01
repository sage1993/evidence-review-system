import pytest

from ansim_review.retrieval.query import normalize_query


def test_normalization_collapses_whitespace_nfc_and_tracks_origins() -> None:
    normalized = normalize_query(
        "  이면도로\t차량  진출입  ",
        expansions=(
            {"text": "  차량   출입 ", "origin": "llm"},
            {"text": "추가  검토", "origin": "llm"},
            {"text": "추가 검토", "origin": "llm"},
        ),
        synonym_manifest={
            "이면도로 차량 진출입": [
                "후면  도로 차량 진출입",
                "차량 출입",
            ]
        },
    )

    assert normalized.primary == "이면도로 차량 진출입"
    assert [(term.text, term.origin) for term in normalized.terms] == [
        ("이면도로 차량 진출입", "primary"),
        ("차량 출입", "approved_synonym"),
        ("후면 도로 차량 진출입", "approved_synonym"),
        ("추가 검토", "llm"),
    ]


def test_nfc_exact_deduplication() -> None:
    normalized = normalize_query(
        "가 기준",
        expansions=({"text": "가 기준", "origin": "llm"},),
        synonym_manifest={},
    )

    assert [(term.text, term.origin) for term in normalized.terms] == [
        ("가 기준", "primary")
    ]


def test_non_llm_expansion_origin_is_rejected() -> None:
    with pytest.raises(ValueError, match="unsupported expansion origin"):
        normalize_query(
            "기준",
            expansions=({"text": "확장", "origin": "approved"},),
            synonym_manifest={},
        )
