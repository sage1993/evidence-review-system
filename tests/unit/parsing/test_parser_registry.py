from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pytest

from ansim_review.parsing.parser_models import NormalizedParserContribution
from ansim_review.parsing.parser_registry import (
    ParserContext,
    ParserRegistry,
)


@dataclass(frozen=True)
class _Adapter:
    kind: str
    result: NormalizedParserContribution | None = None
    error: Exception | None = None

    def parse(self, context: ParserContext) -> NormalizedParserContribution:
        assert context.source_path.name == "source.pdf"
        if self.error is not None:
            raise self.error
        assert self.result is not None
        return self.result


def _context(tmp_path: Path) -> ParserContext:
    source = tmp_path / "source.pdf"
    parser = tmp_path / "parser.json"
    source.write_bytes(b"%PDF-1.7\n")
    parser.write_text("{}", encoding="utf-8")
    return ParserContext(
        source_path=source,
        parser_artifact_path=parser,
        options={},
    )


def test_registry_registers_unique_kinds_in_sorted_order() -> None:
    registry = ParserRegistry()
    registry.register(_Adapter(kind="SECOND"))
    registry.register(_Adapter(kind="FIRST"))

    assert registry.kinds() == ("FIRST", "SECOND")
    assert registry.require("FIRST").kind == "FIRST"


def test_registry_rejects_duplicate_and_unsafe_kinds() -> None:
    registry = ParserRegistry()
    registry.register(_Adapter(kind="VALID_KIND"))

    with pytest.raises(ValueError, match="PARSER_KIND_ALREADY_REGISTERED"):
        registry.register(_Adapter(kind="VALID_KIND"))
    with pytest.raises(ValueError, match="PARSER_KIND_INVALID"):
        registry.register(_Adapter(kind="bad kind"))


def test_registry_rejects_unknown_kind_without_normalization() -> None:
    registry = ParserRegistry()
    registry.register(_Adapter(kind="KNOWN"))

    with pytest.raises(ValueError, match="UNSUPPORTED_PARSER_KIND: known"):
        registry.require("known")


def test_adapter_exception_is_not_converted_to_success(tmp_path: Path) -> None:
    registry = ParserRegistry()
    registry.register(_Adapter(kind="BROKEN", error=RuntimeError("parser failed")))

    with pytest.raises(RuntimeError, match="parser failed"):
        registry.parse("BROKEN", _context(tmp_path))
