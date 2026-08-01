"""Versioned deterministic formula registry."""
from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field

from ansim_review.contracts.engines import CalculationResult

FormulaExecutor = Callable[[Mapping[str, str]], CalculationResult]


@dataclass(frozen=True, slots=True)
class FormulaSpec:
    """Immutable formula metadata and optional execution function."""

    formula_id: str
    version: str
    precision: int
    rounding: str
    input_schema: Mapping[str, str]
    output_policy: Mapping[str, object]
    execute: FormulaExecutor | None = field(default=None, compare=False, repr=False)

    def __post_init__(self) -> None:
        if not self.formula_id or not self.version:
            raise ValueError("formula_id and version are required")
        if self.precision < 1:
            raise ValueError("precision must be positive")
        object.__setattr__(self, "input_schema", dict(sorted(self.input_schema.items())))
        object.__setattr__(self, "output_policy", dict(sorted(self.output_policy.items())))

    @property
    def key(self) -> tuple[str, str]:
        return self.formula_id, self.version


class FormulaRegistry:
    """Registry that rejects duplicate formula ID/version pairs."""

    def __init__(self) -> None:
        self._specs: dict[tuple[str, str], FormulaSpec] = {}

    def register(self, spec: FormulaSpec) -> None:
        if spec.key in self._specs:
            raise ValueError(f"formula already registered: {spec.formula_id}@{spec.version}")
        self._specs[spec.key] = spec

    def get(self, formula_id: str, version: str) -> FormulaSpec | None:
        return self._specs.get((formula_id, version))

    def values(self) -> tuple[FormulaSpec, ...]:
        return tuple(self._specs[key] for key in sorted(self._specs))
