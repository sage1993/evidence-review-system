from decimal import ROUND_HALF_UP, getcontext

import pytest

from ansim_review.math_engine.decimal_context import decimal_context
from ansim_review.math_engine.registry import FormulaRegistry, FormulaSpec


def test_duplicate_formula_version_is_rejected() -> None:
    registry = FormulaRegistry()
    spec = FormulaSpec(
        formula_id="FRONTAGE_RATIO",
        version="1.0.0",
        precision=28,
        rounding="ROUND_HALF_UP",
        input_schema={"frontage_length_m": "decimal-string"},
        output_policy={"kind": "ratio"},
    )
    registry.register(spec)

    with pytest.raises(ValueError, match="formula already registered"):
        registry.register(spec)


def test_decimal_context_does_not_mutate_global_context() -> None:
    before_precision = getcontext().prec
    with decimal_context(precision=12, rounding=ROUND_HALF_UP) as context:
        assert context.prec == 12
        assert context.rounding == ROUND_HALF_UP
    assert getcontext().prec == before_precision
