from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pytest

from evidence_review.contracts.source_batch import decode_source_batch
from evidence_review.parsing.parser_models import (
    NormalizedParserContribution,
    PageDimensions,
    ParsedElement,
)
from evidence_review.parsing.parser_registry import ParserContext, ParserRegistry
from evidence_review.parsing.source_batch_importer import (
    SourceBatchNotReady,
    import_source_batch,
    prepare_source_batch,
)
from tests.helpers.pdf_fixtures import write_pdf_fixture


@dataclass(frozen=True)
class _CustomAdapter:
    kind: str = "CUSTOM_TEXT_JSON"

    def parse(self, context: ParserContext) -> NormalizedParserContribution:
        assert context.options == {"mode": "strict"}
        return NormalizedParserContribution(
            page_dimensions=(PageDimensions(1, 100.0, 200.0),),
            elements=(
                ParsedElement(
                    element_key="P0001-E00001",
                    page_number=1,
                    parser_order=0,
                    element_type="paragraph",
                    raw_payload={"content": "custom evidence"},
                    raw_payload_hash="b" * 64,
                    raw_text="custom evidence",
                    bbox=(1.0, 2.0, 20.0, 30.0),
                ),
            ),
            tables=(),
            visuals=(),
            parser_artifact_sha256=(
                __import__("hashlib").sha256(
                    context.parser_artifact_path.read_bytes()
                ).hexdigest()
            ),
            document_title="Custom document",
        )


def _batch(role: str, parser: dict[str, object] | None):
    return decode_source_batch(
        {
            "format": "evidence-review/source-batch",
            "version": 2,
            "sources": [
                {
                    "source_path": "inputs/source.pdf",
                    "role": role,
                    "document_id": None,
                    "display_title": None,
                    "parser": parser,
                }
            ],
        }
    )


def test_unknown_parser_kind_is_blocked_without_database(tmp_path: Path) -> None:
    (tmp_path / "inputs").mkdir()
    write_pdf_fixture(tmp_path / "inputs/source.pdf", page_sizes=((100.0, 200.0),))
    (tmp_path / "inputs/parser.json").write_text("{}", encoding="utf-8")
    batch = _batch(
        "REFERENCE_DOCUMENT",
        {
            "kind": "UNKNOWN_PARSER",
            "artifact_path": "inputs/parser.json",
            "options": {},
        },
    )
    registry = ParserRegistry()

    prepared = prepare_source_batch(tmp_path, batch, registry)
    assert prepared[0].state == "BLOCKED"
    assert prepared[0].reason_codes == ("UNSUPPORTED_PARSER_KIND",)

    output = tmp_path / "evidence.sqlite"
    with pytest.raises(SourceBatchNotReady, match="UNSUPPORTED_PARSER_KIND"):
        import_source_batch(tmp_path, batch, output, registry)
    assert not output.exists()


def test_drawing_only_batch_does_not_create_empty_database(tmp_path: Path) -> None:
    (tmp_path / "inputs").mkdir()
    (tmp_path / "inputs/source.pdf").write_bytes(b"drawing")
    batch = _batch("CASE_DRAWING", None)
    output = tmp_path / "evidence.sqlite"

    prepared = prepare_source_batch(tmp_path, batch)
    assert prepared[0].state == "PENDING_DRAWING_INGESTION"

    with pytest.raises(SourceBatchNotReady, match="NO_EVIDENCE_SOURCES"):
        import_source_batch(tmp_path, batch, output)
    assert not output.exists()


def test_registered_custom_adapter_can_ingest_v2_source(tmp_path: Path) -> None:
    (tmp_path / "inputs").mkdir()
    write_pdf_fixture(tmp_path / "inputs/source.pdf", page_sizes=((100.0, 200.0),))
    (tmp_path / "inputs/parser.json").write_text("{}", encoding="utf-8")
    batch = _batch(
        "REFERENCE_DOCUMENT",
        {
            "kind": "CUSTOM_TEXT_JSON",
            "artifact_path": "inputs/parser.json",
            "options": {"mode": "strict"},
        },
    )
    registry = ParserRegistry()
    registry.register(_CustomAdapter())

    report = import_source_batch(
        tmp_path,
        batch,
        tmp_path / "evidence.sqlite",
        registry,
    )

    assert report.counts["documents"] == 1
    assert report.counts["elements"] == 1
    assert report.sources[0].state == "READY_TO_EVALUATE"
