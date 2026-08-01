"""Local Decimal contexts for deterministic formulas."""
from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from decimal import Context, ROUND_HALF_EVEN, ROUND_HALF_UP, localcontext

_ROUNDING_MODES = {
    "ROUND_HALF_EVEN": ROUND_HALF_EVEN,
    "ROUND_HALF_UP": ROUND_HALF_UP,
}


def resolve_rounding(rounding: str) -> str:
    """Resolve a declared rounding-mode name to a Decimal constant."""
    try:
        return _ROUNDING_MODES[rounding]
    except KeyError as error:
        raise ValueError(f"unsupported rounding mode: {rounding}") from error


@contextmanager
def decimal_context(*, precision: int, rounding: str) -> Iterator[Context]:
    """Yield a local context without mutating the process-global Decimal context."""
    if precision < 1:
        raise ValueError("precision must be positive")
    selected = resolve_rounding(rounding) if rounding in _ROUNDING_MODES else rounding
    context = Context(prec=precision, rounding=selected)
    with localcontext(context) as active:
        yield active
