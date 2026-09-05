from __future__ import annotations

import pytest

from evidence_review.review_packet.builder import _v2_evidence_records


def _record(
    *,
    citation_id: str = "CIT-E1",
    evidence_id: str = "E1",
    quote: str = "packet quote",
) -> dict[str, object]:
    return {
        "evidence_id": evidence_id,
        "citation": {
            "citation_id": citation_id,
            "evidence_id": evidence_id,
            "document_id": "DOC1",
            "revision_id": "REV1",
            "page_number": 1,
            "bbox": [0, 0, 10, 10],
            "source_hash": "a" * 64,
        },
        "quote": quote,
        "numeric_tokens": [],
    }


def test_v2_evidence_records_reject_conflicting_duplicate_citation_id() -> None:
    document = {
        "version": 2,
        "evidence": [
            _record(),
            _record(quote="different packet quote"),
        ],
    }

    with pytest.raises(ValueError, match="conflicting v2 evidence record"):
        _v2_evidence_records(document)


def test_v2_evidence_records_reject_duplicate_evidence_id_with_new_citation() -> None:
    document = {
        "version": 2,
        "evidence": [
            _record(),
            _record(citation_id="CIT-E1-OTHER", evidence_id="E1"),
        ],
    }

    with pytest.raises(ValueError, match="conflicting v2 evidence record"):
        _v2_evidence_records(document)


def test_v2_evidence_records_preserve_packet_quote() -> None:
    document = {
        "version": 2,
        "evidence": [_record(quote="IMMUTABLE PACKET QUOTE")],
    }

    records = _v2_evidence_records(document)

    assert records["CIT-E1"]["quote"] == "IMMUTABLE PACKET QUOTE"
