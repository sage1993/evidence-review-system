"""Deterministic review queue for OpenDataLoader parser warnings."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, replace
from typing import Literal, Sequence, cast

from ansim_review.canonical_json import dump_bytes
from ansim_review.parser_reproducibility.warnings import (
    ParserWarning,
    warning_sort_key,
)


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


def queue_id_for(warning: ParserWarning) -> str:
    authority = {
        "source_sha256": warning.source_sha256,
        "parser_version": warning.parser_version,
        "configuration_sha256": warning.configuration_sha256,
        "page_number": warning.page_number,
        "warning_code": warning.code,
        "normalized_message_sha256": warning.normalized_message_sha256,
    }
    digest = hashlib.sha256(dump_bytes(authority)).hexdigest()[:24].upper()
    return f"PQUE-{digest}"


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

    if not run_id:
        raise ValueError("run_id must not be empty")
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
    return asdict(queue)


def decode_review_queue(data: bytes) -> ParserReviewQueue:
    """Strictly decode prior history; malformed data never resets the queue."""

    try:
        value = json.loads(data.decode("utf-8-sig"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("previous queue must be UTF-8 JSON") from exc
    if not isinstance(value, dict) or set(value) != {"format", "version", "entries"}:
        raise ValueError("previous queue has an invalid top-level contract")
    if value["format"] != "evidence-review/parser-review-queue" or value["version"] != 1:
        raise ValueError("previous queue has an unsupported format or version")
    raw_entries = value["entries"]
    if not isinstance(raw_entries, list):
        raise ValueError("previous queue entries must be an array")
    entries: list[ParserReviewQueueEntry] = []
    expected = set(ParserReviewQueueEntry.__dataclass_fields__)
    for index, raw in enumerate(raw_entries):
        if not isinstance(raw, dict) or set(raw) != expected:
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
        entries.append(ParserReviewQueueEntry(**cast(dict[str, object], raw)))
    queue = ParserReviewQueue(
        format="evidence-review/parser-review-queue",
        version=1,
        entries=tuple(sorted(entries, key=queue_sort_key)),
    )
    if len({entry.queue_id for entry in queue.entries}) != len(queue.entries):
        raise ValueError("previous queue contains duplicate queue_id values")
    return queue
