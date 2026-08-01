from __future__ import annotations

import pytest

from ansim_review.contracts.source_batch import (
    decode_source_batch,
    source_batch_document,
)


def _v2_payload() -> dict[str, object]:
    return {
        "format": "evidence-review/source-batch",
        "version": 2,
        "sources": [
            {
                "source_path": "inputs/original/policy.pdf",
                "role": "REFERENCE_DOCUMENT",
                "document_id": None,
                "display_title": "정책 자료",
                "parser": {
                    "kind": "OPENDATALOADER_JSON",
                    "artifact_path": "inputs/parser/policy.json",
                    "options": {},
                },
            }
        ],
    }


def _v1_payload() -> dict[str, object]:
    payload = _v2_payload()
    payload["version"] = 1
    sources = payload["sources"]
    assert isinstance(sources, list)
    parser = sources[0]["parser"]
    assert isinstance(parser, dict)
    parser.pop("options")
    return payload


def test_source_batch_v2_round_trips_canonical_document() -> None:
    payload = _v2_payload()
    batch = decode_source_batch(payload)

    assert batch.version == 2
    assert source_batch_document(batch) == payload


def test_source_batch_v1_decodes_to_v2_internal_model() -> None:
    batch = decode_source_batch(_v1_payload())

    assert batch.version == 2
    assert batch.sources[0].parser is not None
    assert batch.sources[0].parser.options == {}
    assert source_batch_document(batch)["version"] == 2


def test_source_batch_v2_allows_registry_resolved_parser_kind() -> None:
    payload = _v2_payload()
    sources = payload["sources"]
    assert isinstance(sources, list)
    parser = sources[0]["parser"]
    assert isinstance(parser, dict)
    parser["kind"] = "VENDOR_TABLE_PARSER"
    parser["options"] = {"profile": "strict"}

    batch = decode_source_batch(payload)

    assert batch.sources[0].parser is not None
    assert batch.sources[0].parser.kind == "VENDOR_TABLE_PARSER"
    assert batch.sources[0].parser.options == {"profile": "strict"}


def test_source_batch_allows_pending_parser_output() -> None:
    payload = _v2_payload()
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
    payload = _v2_payload()
    sources = payload["sources"]
    assert isinstance(sources, list)
    sources[0]["source_path"] = path
    with pytest.raises(ValueError, match="source_path"):
        decode_source_batch(payload)


def test_source_batch_rejects_unsafe_parser_artifact_path() -> None:
    payload = _v2_payload()
    sources = payload["sources"]
    assert isinstance(sources, list)
    parser = sources[0]["parser"]
    assert isinstance(parser, dict)
    parser["artifact_path"] = "../parser.json"

    with pytest.raises(ValueError, match="parser.artifact_path"):
        decode_source_batch(payload)


def test_source_batch_rejects_non_object_options() -> None:
    payload = _v2_payload()
    sources = payload["sources"]
    assert isinstance(sources, list)
    parser = sources[0]["parser"]
    assert isinstance(parser, dict)
    parser["options"] = []

    with pytest.raises(ValueError, match="parser.options"):
        decode_source_batch(payload)


def test_source_batch_v1_rejects_unknown_parser_kind() -> None:
    payload = _v1_payload()
    sources = payload["sources"]
    assert isinstance(sources, list)
    parser = sources[0]["parser"]
    assert isinstance(parser, dict)
    parser["kind"] = "FILENAME_GUESS"
    with pytest.raises(ValueError, match="parser.kind"):
        decode_source_batch(payload)


def test_source_batch_rejects_duplicate_source_paths() -> None:
    payload = _v2_payload()
    sources = payload["sources"]
    assert isinstance(sources, list)
    sources.append(dict(sources[0]))
    with pytest.raises(ValueError, match="duplicate source_path"):
        decode_source_batch(payload)


def test_source_batch_requires_new_generic_format() -> None:
    payload = _v2_payload()
    payload["format"] = "ansim/source-batch"
    with pytest.raises(ValueError, match="unsupported format"):
        decode_source_batch(payload)
