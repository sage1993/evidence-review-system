from ansim_review.retrieval.korean_variants import derive_korean_query_variants


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
