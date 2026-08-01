"""Deterministic parser adapter registration and dispatch."""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from ansim_review.parsing.parser_models import NormalizedParserContribution

_KIND = re.compile(r"^[A-Z][A-Z0-9_]{0,63}$")


@dataclass(frozen=True, slots=True)
class ParserContext:
    """Immutable parser inputs resolved below a source-batch root."""

    source_path: Path
    parser_artifact_path: Path
    options: Mapping[str, object]


class ParserAdapter(Protocol):
    """Parser-neutral adapter boundary."""

    @property
    def kind(self) -> str: ...

    def parse(self, context: ParserContext) -> NormalizedParserContribution: ...


class ParserRegistry:
    """Case-sensitive, deterministic parser adapter registry."""

    def __init__(self) -> None:
        self._adapters: dict[str, ParserAdapter] = {}

    def register(self, adapter: ParserAdapter) -> None:
        kind = adapter.kind
        if not isinstance(kind, str) or _KIND.fullmatch(kind) is None:
            raise ValueError(f"PARSER_KIND_INVALID: {kind}")
        if kind in self._adapters:
            raise ValueError(f"PARSER_KIND_ALREADY_REGISTERED: {kind}")
        self._adapters[kind] = adapter

    def require(self, kind: str) -> ParserAdapter:
        try:
            return self._adapters[kind]
        except KeyError as error:
            raise ValueError(f"UNSUPPORTED_PARSER_KIND: {kind}") from error

    def kinds(self) -> tuple[str, ...]:
        return tuple(sorted(self._adapters))

    def parse(
        self,
        kind: str,
        context: ParserContext,
    ) -> NormalizedParserContribution:
        return self.require(kind).parse(context)


def build_default_parser_registry() -> ParserRegistry:
    """Build a new default registry without module-level mutable state."""
    from ansim_review.parsing.odl_adapter import OpenDataLoaderJsonAdapter

    registry = ParserRegistry()
    registry.register(OpenDataLoaderJsonAdapter())
    return registry
