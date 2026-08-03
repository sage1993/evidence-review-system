"""Deterministic review queue for OpenDataLoader parser warnings."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Sequence
from dataclasses import asdict, dataclass, replace
from typing import Literal, cast

from ansim_review.canonical_json import dump_bytes
from ansim_review.parser_reproducibility.contract import (
    reject_nonfinite_json_constant,
)
from ansim_review.parser_reproducibility.warnings import (
    ParserWarning,
    warning_sort_key,
)

_SHA256 = re.compile(r"^[0-9A-Fa-f]{64}$")
_QUEUE_ID = re.compile(r"^PQUE-[0-9A-F]{24}$")
_WARNING_ID = re.compile(r"^PWRN-[0-9A-F]{24}$")
_RUN_ID = re.compile(r"^PRUN-[0-9A-F]{24}$")


@dataclass(frozen=True, slots=True)
class ParserReviewQueueEntry:
    queue_id: str
    status: Literal["REVIEW_REQUIRED"]
    warning_id: str
    document_id: str
    revision_id: str
    source_sha256: str
    parser_version: str
    configuration_sha256: str
    page_number: int | None
    warning_code: str
    normalized_message_sha256: str
    first_seen_run_id: str
    last_seen_run_id: str
    occurrence_count: int


@dataclass(frozen=True, slots=True)
class ParserReviewQueue:
    format: Literal["evidence-review/parser-review-queue"]
    version: Literal[1]
    entries: tuple[ParserReviewQueueEntry, ...]


def _queue_id(
    *,
    source_sha256: str,
    parser_version: str,
    configuration_sha256: str,
    page_number: int | None,
    warning_code: str,
    normalized_message_sha256: str,
) -> str:
    authority = {
        "source_sha256": source_sha256,
        "parser_version": parser_version,
        "configuration_sha256": configuration_sha256,
        "page_number": page_number,
        "warning_code": warning_code,
        "normalized_message_sha256": normalized_message_sha256,
    }
    digest = hashlib.sha256(dump_bytes(authority)).hexdigest()[:24].upper()
    return f"PQUE-{digest}"


def _warning_id(
    *,
    source_sha256: str,
    parser_version: str,
    configuration_sha256: str,
    page_number: int | None,
    warning_code: str,
    normalized_message_sha256: str,
) -> str:
    authority = {
        "source_sha256": source_sha256,
        "parser_kind": "opendataloader",
        "parser_version": parser_version,
        "configuration_sha256": configuration_sha256,
        "page_number": page_number,
        "code": warning_code,
        "normalized_message_sha256": normalized_message_sha256,
    }
    digest = hashlib.sha256(dump_bytes(authority)).hexdigest()[:24].upper()
    return f"PWRN-{digest}"


def queue_id_for(warning: ParserWarning) -> str:
    return _queue_id(
        source_sha256=warning.source_sha256,
        parser_version=warning.parser_version,
        configuration_sha256=warning.configuration_sha256,
        page_number=warning.page_number,
        warning_code=warning.code,
        normalized_message_sha256=warning.normalized_message_sha256,
    )


def _new_entry(warning: ParserWarning, run_id: str) -> ParserReviewQueueEntry:
    return ParserReviewQueueEntry(
        queue_id=queue_id_for(warning),
        status="REVIEW_REQUIRED",
        warning_id=warning.warning_id,
        document_id=warning.document_id,
        revision_id=warning.revision_id,
        source_sha256=warning.source_sha256,
        parser_version=warning.parser_version,
        configuration_sha256=warning.configuration_sha256,
        page_number=warning.page_number,
        warning_code=warning.code,
        normalized_message_sha256=warning.normalized_message_sha256,
        first_seen_run_id=run_id,
        last_seen_run_id=run_id,
        occurrence_count=1,
    )


def queue_sort_key(entry: ParserReviewQueueEntry) -> tuple[object, ...]:
    return (
        entry.source_sha256,
        entry.parser_version,
        entry.configuration_sha256,
        -1 if entry.page_number is None else entry.page_number,
        entry.warning_code,
        entry.normalized_message_sha256,
        entry.queue_id,
    )


def build_review_queue(
    warnings: Sequence[ParserWarning],
    run_id: str,
    previous: ParserReviewQueue | None = None,
) -> ParserReviewQueue:
    """Merge warnings without deleting immutable historical queue evidence."""

    if _RUN_ID.fullmatch(run_id) is None:
        raise ValueError("run_id must be a canonical parser run ID")
    prior_entries = () if previous is None else previous.entries
    entries = {entry.queue_id: entry for entry in prior_entries}
    if len(entries) != len(prior_entries):
        raise ValueError("previous queue contains duplicate queue_id values")
    for warning in sorted(warnings, key=warning_sort_key):
        queue_id = queue_id_for(warning)
        existing = entries.get(queue_id)
        if existing is None:
            entries[queue_id] = _new_entry(warning, run_id)
            continue
        entries[queue_id] = replace(
            existing,
            warning_id=warning.warning_id,
            last_seen_run_id=run_id,
            occurrence_count=existing.occurrence_count + 1,
        )
    return ParserReviewQueue(
        format="evidence-review/parser-review-queue",
        version=1,
        entries=tuple(sorted(entries.values(), key=queue_sort_key)),
    )


def queue_document(queue: ParserReviewQueue) -> dict[str, object]:
    return cast(dict[str, object], asdict(queue))


def _reject_duplicate_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _required_string(raw: dict[str, object], field: str, index: int) -> str:
    value = raw[field]
    if not isinstance(value, str) or not value:
        raise ValueError(f"previous queue entry {index} has invalid {field}")
    return value


def _entry_from_object(
    raw: dict[str, object],
    index: int,
) -> ParserReviewQueueEntry:
    expected = set(ParserReviewQueueEntry.__dataclass_fields__)
    if set(raw) != expected:
        raise ValueError(f"previous queue entry {index} has an invalid contract")
    if raw["status"] != "REVIEW_REQUIRED":
        raise ValueError(f"previous queue entry {index} has an invalid status")
    count = raw["occurrence_count"]
    if isinstance(count, bool) or not isinstance(count, int) or count < 1:
        raise ValueError(f"previous queue entry {index} has an invalid count")
    page = raw["page_number"]
    if page is not None and (
        isinstance(page, bool) or not isinstance(page, int) or page < 1
    ):
        raise ValueError(f"previous queue entry {index} has an invalid page")

    source_sha256 = _required_string(raw, "source_sha256", index)
    configuration_sha256 = _required_string(
        raw,
        "configuration_sha256",
        index,
    )
    normalized_message_sha256 = _required_string(
        raw,
        "normalized_message_sha256",
        index,
    )
    parser_version = _required_string(raw, "parser_version", index)
    warning_code = _required_string(raw, "warning_code", index)
    queue_id = _required_string(raw, "queue_id", index)
    warning_id = _required_string(raw, "warning_id", index)
    first_seen_run_id = _required_string(raw, "first_seen_run_id", index)
    last_seen_run_id = _required_string(raw, "last_seen_run_id", index)

    if any(
        _SHA256.fullmatch(value) is None
        for value in (
            source_sha256,
            configuration_sha256,
            normalized_message_sha256,
        )
    ):
        raise ValueError(f"previous queue entry {index} has an invalid digest")
    if _QUEUE_ID.fullmatch(queue_id) is None:
        raise ValueError(f"previous queue entry {index} has an invalid queue_id")
    if _WARNING_ID.fullmatch(warning_id) is None:
        raise ValueError(f"previous queue entry {index} has an invalid warning_id")
    if any(
        _RUN_ID.fullmatch(value) is None
        for value in (first_seen_run_id, last_seen_run_id)
    ):
        raise ValueError(f"previous queue entry {index} has an invalid run_id")

    expected_queue_id = _queue_id(
        source_sha256=source_sha256,
        parser_version=parser_version,
        configuration_sha256=configuration_sha256,
        page_number=page,
        warning_code=warning_code,
        normalized_message_sha256=normalized_message_sha256,
    )
    expected_warning_id = _warning_id(
        source_sha256=source_sha256,
        parser_version=parser_version,
        configuration_sha256=configuration_sha256,
        page_number=page,
        warning_code=warning_code,
        normalized_message_sha256=normalized_message_sha256,
    )
    if queue_id != expected_queue_id:
        raise ValueError(f"previous queue entry {index} queue_id mismatch")
    if warning_id != expected_warning_id:
        raise ValueError(f"previous queue entry {index} warning_id mismatch")

    return ParserReviewQueueEntry(
        queue_id=queue_id,
        status="REVIEW_REQUIRED",
        warning_id=warning_id,
        document_id=_required_string(raw, "document_id", index),
        revision_id=_required_string(raw, "revision_id", index),
        source_sha256=source_sha256,
        parser_version=parser_version,
        configuration_sha256=configuration_sha256,
        page_number=page,
        warning_code=warning_code,
        normalized_message_sha256=normalized_message_sha256,
        first_seen_run_id=first_seen_run_id,
        last_seen_run_id=last_seen_run_id,
        occurrence_count=count,
    )


def decode_review_queue(data: bytes) -> ParserReviewQueue:
    """Strictly decode prior history; malformed data never resets the queue."""

    try:
        decoded = data.decode("utf-8-sig")
        value = json.loads(
            decoded,
            object_pairs_hook=_reject_duplicate_keys,
            parse_constant=reject_nonfinite_json_constant,
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("previous queue must be UTF-8 JSON") from exc
    if not isinstance(value, dict) or set(value) != {
        "format",
        "version",
        "entries",
    }:
        raise ValueError("previous queue has an invalid top-level contract")
    if (
        value["format"] != "evidence-review/parser-review-queue"
        or value["version"] != 1
    ):
        raise ValueError("previous queue has an unsupported format or version")
    raw_entries = value["entries"]
    if not isinstance(raw_entries, list):
        raise ValueError("previous queue entries must be an array")
    entries: list[ParserReviewQueueEntry] = []
    for index, raw in enumerate(raw_entries):
        if not isinstance(raw, dict):
            raise ValueError(f"previous queue entry {index} must be an object")
        entries.append(_entry_from_object(raw, index))
    queue = ParserReviewQueue(
        format="evidence-review/parser-review-queue",
        version=1,
        entries=tuple(sorted(entries, key=queue_sort_key)),
    )
    if len({entry.queue_id for entry in queue.entries}) != len(queue.entries):
        raise ValueError("previous queue contains duplicate queue_id values")
    return queue
