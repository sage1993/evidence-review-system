from ansim_review.math_engine.formulas import (
    DEFAULT_REGISTRY,
    DRAWING_LENGTH_ID,
    DRAWING_LENGTH_VERSION,
    DRAWING_REGISTRY,
    DRAWING_SCALE_ID,
    DRAWING_SCALE_VERSION,
    run_calculation,
)


def test_drawing_formulas_are_isolated_from_legacy_default_registry() -> None:
    assert DEFAULT_REGISTRY.get(DRAWING_SCALE_ID, DRAWING_SCALE_VERSION) is None
    assert DRAWING_REGISTRY.get(DRAWING_SCALE_ID, DRAWING_SCALE_VERSION) is not None
    assert DRAWING_REGISTRY.get(DRAWING_LENGTH_ID, DRAWING_LENGTH_VERSION) is not None

    result = run_calculation(
        DRAWING_SCALE_ID,
        DRAWING_SCALE_VERSION,
        {"real_length": "35.0", "pixel_length": "100"},
        registry=DRAWING_REGISTRY,
    )

    assert result.status == "SUCCESS"
    assert result.raw_result == "0.35"
    assert result.result_hash is not None
