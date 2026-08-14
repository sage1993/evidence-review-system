import pytest

from ansim_review.retrieval.korean_variants import (
    derive_korean_compound_variants,
    derive_korean_query_variants,
)


def test_real_question_derives_bounded_groups() -> None:
    variants = derive_korean_query_variants(
        "청소년 문화의집은 면적이 1500제곱미터 이상이어야 한다."
    )

    assert variants.entity == ("청소년 문화의집", "청소년문화의집")
    assert variants.numeric == (
        "1500",
        "1,500",
        "1500제곱미터",
        "1,500제곱미터",
    )
    assert variants.concept == ("면적", "연면적", "연건축면적", "이상")


def test_variant_derivation_is_deterministic() -> None:
    question = "청소년 문화의집은 면적이 1500제곱미터 이상이어야 한다."

    first = derive_korean_query_variants(question)
    second = derive_korean_query_variants(question)

    assert first == second


def test_unrelated_short_question_does_not_invent_numeric_variants() -> None:
    variants = derive_korean_query_variants("기준을 확인한다.")

    assert variants.numeric == ()


@pytest.mark.parametrize(
    ("query", "expected"),
    [
        (
            "\uc8fc\uccad\uc18c\ub144\ubb38\ud654\uc758\uc9d1 \uc124\uce58\uae30\uc900",
            ("\uc8fc\uccad\uc18c\ub144\ubb38\ud654\uc758\uc9d1",),
        ),
        (
            "\uc8fc\uccad\uc18c\ub144 \ubb38\ud654\uc758\uc9d1 \uc124\uce58\uae30\uc900",
            (
                "\uc8fc\uccad\uc18c\ub144 \ubb38\ud654\uc758\uc9d1",
                "\uc8fc\uccad\uc18c\ub144\ubb38\ud654\uc758\uc9d1",
            ),
        ),
        (
            "\uc18c\ubc29\ucc28 \uc804\uc6a9\uad6c\uc5ed",
            (
                "\uc18c\ubc29\ucc28 \uc804\uc6a9\uad6c\uc5ed",
                "\uc18c\ubc29\ucc28\uc804\uc6a9\uad6c\uc5ed",
            ),
        ),
        (
            "\ud53c\ub09c\uc548\uc804\uad6c\uc5ed\uc5d0\uc11c",
            ("\ud53c\ub09c\uc548\uc804\uad6c\uc5ed",),
        ),
        ("\uc124\uce58\uae30\uc900", ()),
    ],
)
def test_derive_korean_compound_variants_is_bounded(
    query: str,
    expected: tuple[str, ...],
) -> None:
    assert derive_korean_compound_variants(query) == expected


def test_compound_variants_remove_only_known_zero_width_markers() -> None:
    assert derive_korean_compound_variants(
        "\uc8fc\ucc28\u200b\uad6c\ud68d\uc120 \uc124\uce58\uae30\uc900"
    ) == ("\uc8fc\ucc28\uad6c\ud68d\uc120",)
