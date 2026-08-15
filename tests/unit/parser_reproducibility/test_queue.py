from __future__ import annotations

from dataclasses import replace

import pytest

from evidence_review.parser_reproducibility.queue import (
    build_review_queue,
    decode_review_queue,
    queue_document,
)
from evidence_review.parser_reproducibility.report import report_bytes
from evidence_review.parser_reproducibility.warnings import (
    ParserWarning,
    warning_id_for,
)


def parser_warning(page_number: int | None = 3) -> ParserWarning:
    provisional = ParserWarning(
        warning_id="",
        severity="WARNING",
        code="PARSER_WARNING_LAYOUT",
        document_id="DOC-TEST",
        revision_id="DOC-TEST-000000000000",
        source_sha256="0" * 64,
        parser_kind="opendataloader",
        parser_version="1.2.3",
        configuration_sha256="B" * 64,
        page_number=page_number,
        raw_source_relative_path="parser.log",
        raw_location="line:1",
        raw_message="layout warning",
        normalized_message_sha256="C" * 64,
        run_id="PRUN-" + "D" * 24,
    )
    return replace(provisional, warning_id=warning_id_for(provisional))


def test_repeated_warning_updates_one_entry() -> None:
    warning = parser_warning()
    first = build_review_queue((warning,), "PRUN-" + "A" * 24)
    second = build_review_queue(
        (warning, warning),
        "PRUN-" + "B" * 24,
        first,
    )

    assert len(second.entries) == 1
    assert second.entries[0].status == "REVIEW_REQUIRED"
    assert second.entries[0].first_seen_run_id == "PRUN-" + "A" * 24
    assert second.entries[0].last_seen_run_id == "PRUN-" + "B" * 24
    assert second.entries[0].occurrence_count == 3


def test_absent_warning_does_not_delete_history() -> None:
    previous = build_review_queue(
        (parser_warning(),),
        "PRUN-" + "A" * 24,
    )
    current = build_review_queue((), "PRUN-" + "B" * 24, previous)
    assert current.entries == previous.entries


def test_queue_round_trip_is_strict_and_deterministic() -> None:
    queue = build_review_queue(
        (parser_warning(),),
        "PRUN-" + "A" * 24,
    )
    encoded = report_bytes(queue)

    assert decode_review_queue(encoded) == queue
    assert report_bytes(decode_review_queue(encoded)) == encoded
    assert queue_document(queue)["format"] == "evidence-review/parser-review-queue"


def test_queue_decoder_rejects_tampered_identity() -> None:
    queue = build_review_queue(
        (parser_warning(),),
        "PRUN-" + "A" * 24,
    )
    encoded = report_bytes(queue).replace(b"PQUE-", b"PQUE-F")

    try:
        decode_review_queue(encoded)
    except ValueError as error:
        assert "queue_id" in str(error)
    else:
        raise AssertionError("tampered queue identity was accepted")


def test_queue_decoder_rejects_nonfinite_json_constants() -> None:
    with pytest.raises(ValueError, match="non-finite"):
        decode_review_queue(b'{"format":NaN,"version":1,"entries":[]}')
