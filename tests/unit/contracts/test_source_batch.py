from __future__ import annotations

import pytest

from ansim_review.contracts.source_batch import (
    decode_source_batch,
    source_batch_document,
)


def _payload() -> dict[str, object]:
    return {
        "format": "evidence-review/source-batch",
        "version": 1,
        "sources": [
            {
                "source_path": "inputs/original/policy.pdf",
                "role": "REFERENCE_DOCUMENT",
                "document_id": None,
                "display_title": "정책 자료",
                "parser": {
                    "kind": "OPENDATALOADER_JSON",
                    "artifact_path": "inputs/parser/policy.json",
                },
            }
        ],
    }


def test_source_batch_round_trips_canonical_document() -> None:
    payload = _payload()
    batch = decode_source_batch(payload)
    assert source_batch_document(batch) == payload


def test_source_batch_allows_pending_parser_output() -> None:
    payload = _payload()
    sources = payload["sources"]
    assert isinstance(sources, list)
    sources[0]["parser"] = None
    batch = decode_source_batch(payload)
    assert batch.sources[0].parser is None


@pytest.mark.parametrize(
    "path",
    ["../policy.pdf", "/tmp/policy.pdf", "C:\\policy.pdf", "inputs\\policy.pdf"],
)
def test_source_batch_rejects_unsafe_source_path(path: str) -> None:
    payload = _payload()
    sources = payload["sources"]
    assert isinstance(sources, list)
    sources[0]["source_path"] = path
    with pytest.raises(ValueError, match="source_path"):
        decode_source_batch(payload)


def test_source_batch_rejects_unknown_parser_kind() -> None:
    payload = _payload()
    sources = payload["sources"]
    assert isinstance(sources, list)
    parser = sources[0]["parser"]
    assert isinstance(parser, dict)
    parser["kind"] = "FILENAME_GUESS"
    with pytest.raises(ValueError, match="parser.kind"):
        decode_source_batch(payload)


def test_source_batch_rejects_duplicate_source_paths() -> None:
    payload = _payload()
    sources = payload["sources"]
    assert isinstance(sources, list)
    sources.append(dict(sources[0]))
    with pytest.raises(ValueError, match="duplicate source_path"):
        decode_source_batch(payload)


def test_source_batch_requires_new_generic_format() -> None:
    payload = _payload()
    payload["format"] = "ansim/source-batch"
    with pytest.raises(ValueError, match="unsupported format"):
        decode_source_batch(payload)
