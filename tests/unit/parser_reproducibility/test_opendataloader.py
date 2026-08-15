from __future__ import annotations

import json

import pytest

from evidence_review.parser_reproducibility.opendataloader import (
    decode_opendataloader_json,
)


def test_decoder_preserves_raw_payload_and_page_order() -> None:
    payload = {
        "number of pages": 2,
        "pages": [
            {"page number": 1, "kids": []},
            {"page number": 2, "kids": []},
        ],
    }
    artifact = decode_opendataloader_json(
        json.dumps(payload, separators=(",", ":")).encode("utf-8")
    )

    assert artifact.page_count == 2
    assert artifact.page_numbers == (1, 2)
    pages = artifact.raw_payload["pages"]
    assert isinstance(pages, list)
    assert pages[0]["page number"] == 1


def test_decoder_rejects_duplicate_keys() -> None:
    with pytest.raises(ValueError, match="duplicate JSON key"):
        decode_opendataloader_json(b'{"kids":[],"kids":[]}')


def test_decoder_rejects_nonfinite_json_constants() -> None:
    with pytest.raises(ValueError, match="non-finite"):
        decode_opendataloader_json(
            b'{"number of pages":1,"kids":[{"value":NaN}]}'
        )


def test_decoder_rejects_page_beyond_declared_count() -> None:
    payload = {
        "number of pages": 1,
        "kids": [{"type": "paragraph", "page number": 2}],
    }
    with pytest.raises(ValueError, match="exceeds"):
        decode_opendataloader_json(json.dumps(payload).encode("utf-8"))


def test_decoder_rejects_duplicate_page_order() -> None:
    payload = {
        "number of pages": 2,
        "pages": [{"page number": 1}, {"page number": 1}],
    }
    with pytest.raises(ValueError, match="duplicate page numbers"):
        decode_opendataloader_json(json.dumps(payload).encode("utf-8"))
