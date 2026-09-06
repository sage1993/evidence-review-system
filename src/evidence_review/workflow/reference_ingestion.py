"""Reference-ingestion receipts and source-batch adapter boundaries."""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Literal, Protocol, cast

from evidence_review import canonical_json
from evidence_review.contracts.attachments import ImmutableAttachment
from evidence_review.contracts.formats import REFERENCE_INGESTION_RECEIPT_FORMAT
from evidence_review.contracts.identifiers import validate_identifier
from evidence_review.contracts.source_batch import SourceBatch
from evidence_review.contracts.validation import (
    expect_bool,
    expect_int,
    expect_mapping,
    expect_sequence,
    expect_sha256,
    expect_string,
    reject_unknown,
    require_fields,
)
from evidence_review.filesystem_trust import (
    verified_regular_directory,
    verified_regular_file_below,
)
from evidence_review.parsing.parser_registry import ParserRegistry
from evidence_review.parsing.source_batch_importer import import_source_batch
from evidence_review.workflow.request import (
    ReviewRequest,
    confirmed_attachments,
    review_request_sha256,
)
from evidence_review.workflow.run_layout import ReviewRunLayout


@dataclass(frozen=True, slots=True)
class ReferenceSourceResult:
    """Resolved reference identity for one immutable source hash."""

    attachment_ids: tuple[str, ...]
    original_names: tuple[str, ...]
    source_sha256: str
    document_id: str
    revision_id: str


@dataclass(frozen=True, slots=True)
class ReferenceIngestionBatchResult:
    """Result returned by one trusted deterministic ingestion backend."""

    snapshot_sha256: str
    output_db_relative_path: str
    output_db_sha256: str
    output_db_byte_size: int
    sources: tuple[ReferenceSourceResult, ...]


@dataclass(frozen=True, slots=True)
class ReferenceIngestionReceipt:
    """Create-only proof that all request reference sources were ingested."""

    format: Literal["evidence-review/reference-ingestion-receipt"]
    version: Literal[1]
    request_sha256: str
    snapshot_sha256: str
    output_db_relative_path: str
    output_db_sha256: str
    output_db_byte_size: int
    sources: tuple[ReferenceSourceResult, ...]
    changed_original_names: tuple[str, ...]
    review_required: bool


class ReferenceIngestionBackend(Protocol):
    """Trusted backend boundary used by the resumable orchestrator."""

    def ingest(
        self,
        *,
        request: ReviewRequest,
        attachments: tuple[ImmutableAttachment, ...],
        run_dir: Path,
    ) -> ReferenceIngestionBatchResult:
        """Ingest all supplied reference attachments or raise without success."""


def _safe_machine_path(value: object) -> str:
    path = expect_string(value, "output_db_relative_path")
    parsed = PurePosixPath(path)
    first = parsed.parts[0] if parsed.parts else ""
    if (
        not parsed.parts
        or parsed.is_absolute()
        or parsed.parts[0] != "machine"
        or ".." in parsed.parts
        or "\\" in path
        or ":" in first
        or len(parsed.parts) < 2
    ):
        raise ValueError("output_db_relative_path must stay under machine/")
    return path


def _positive_size(value: object, field: str) -> int:
    size = expect_int(value, field)
    if size < 1:
        raise ValueError(f"{field} must be positive")
    return size


def _decode_string_tuple(value: object, field: str) -> tuple[str, ...]:
    items = tuple(
        expect_string(item, f"{field}[{index}]")
        for index, item in enumerate(expect_sequence(value, field))
    )
    if len(items) != len(set(items)):
        raise ValueError(f"{field} must contain unique values")
    return tuple(sorted(items))


def _decode_source_result(value: object) -> ReferenceSourceResult:
    payload = expect_mapping(value, "reference_source")
    required = {
        "attachment_ids",
        "original_names",
        "source_sha256",
        "document_id",
        "revision_id",
    }
    require_fields(payload, required, "reference_source")
    reject_unknown(payload, required, "reference_source")
    attachment_ids = tuple(
        validate_identifier(item, "attachment_id")
        for item in _decode_string_tuple(
            payload.get("attachment_ids"), "attachment_ids"
        )
    )
    original_names = _decode_string_tuple(
        payload.get("original_names"), "original_names"
    )
    if not attachment_ids:
        raise ValueError("attachment_ids must not be empty")
    if not original_names:
        raise ValueError("original_names must not be empty")
    return ReferenceSourceResult(
        attachment_ids=attachment_ids,
        original_names=original_names,
        source_sha256=expect_sha256(
            payload.get("source_sha256"), "source_sha256"
        ),
        document_id=validate_identifier(
            payload.get("document_id"), "document_id"
        ),
        revision_id=validate_identifier(
            payload.get("revision_id"), "revision_id"
        ),
    )


def reference_source_document(source: ReferenceSourceResult) -> dict[str, object]:
    """Return one canonical resolved-source document."""
    return {
        "attachment_ids": list(source.attachment_ids),
        "original_names": list(source.original_names),
        "source_sha256": source.source_sha256,
        "document_id": source.document_id,
        "revision_id": source.revision_id,
    }


def _merge_source_results(
    sources: tuple[ReferenceSourceResult, ...],
) -> tuple[ReferenceSourceResult, ...]:
    grouped: dict[str, ReferenceSourceResult] = {}
    for source in sources:
        validated = _decode_source_result(reference_source_document(source))
        existing = grouped.get(validated.source_sha256)
        if existing is None:
            grouped[validated.source_sha256] = validated
            continue
        if (
            existing.document_id != validated.document_id
            or existing.revision_id != validated.revision_id
        ):
            raise ValueError(
                "one source hash maps to conflicting reference identities"
            )
        grouped[validated.source_sha256] = ReferenceSourceResult(
            attachment_ids=tuple(
                sorted(set(existing.attachment_ids + validated.attachment_ids))
            ),
            original_names=tuple(
                sorted(set(existing.original_names + validated.original_names))
            ),
            source_sha256=validated.source_sha256,
            document_id=validated.document_id,
            revision_id=validated.revision_id,
        )
    return tuple(grouped[digest] for digest in sorted(grouped))


def _changed_names(
    attachments: tuple[ImmutableAttachment, ...],
) -> tuple[str, ...]:
    hashes_by_name: dict[str, set[str]] = {}
    for attachment in attachments:
        hashes_by_name.setdefault(attachment.original_name, set()).add(
            attachment.sha256
        )
    return tuple(
        sorted(
            name
            for name, digests in hashes_by_name.items()
            if len(digests) > 1
        )
    )


def _validate_result_coverage(
    attachments: tuple[ImmutableAttachment, ...],
    result: ReferenceIngestionBatchResult,
) -> tuple[ReferenceSourceResult, ...]:
    expected_by_id = {
        attachment.attachment_id: attachment for attachment in attachments
    }
    if len(expected_by_id) != len(attachments):
        raise ValueError("reference attachment IDs must be unique")
    merged = _merge_source_results(result.sources)
    seen_ids: set[str] = set()
    for source in merged:
        for attachment_id in source.attachment_ids:
            attachment = expected_by_id.get(attachment_id)
            if attachment is None:
                raise ValueError(
                    "ingestion result references an unknown attachment"
                )
            if attachment.sha256 != source.source_sha256:
                raise ValueError(
                    "ingestion result source hash does not match attachment"
                )
            seen_ids.add(attachment_id)
        expected_names = {
            expected_by_id[attachment_id].original_name
            for attachment_id in source.attachment_ids
        }
        if set(source.original_names) != expected_names:
            raise ValueError(
                "ingestion result original names do not match attachments"
            )
    if seen_ids != set(expected_by_id):
        raise ValueError(
            "ingestion result does not cover all reference attachments"
        )
    return merged


def make_reference_ingestion_receipt(
    request: ReviewRequest,
    attachments: tuple[ImmutableAttachment, ...],
    result: ReferenceIngestionBatchResult,
) -> ReferenceIngestionReceipt:
    """Validate backend output and bind it to the exact deterministic request."""
    sources = _validate_result_coverage(attachments, result)
    changed_original_names = _changed_names(attachments)
    return ReferenceIngestionReceipt(
        format=REFERENCE_INGESTION_RECEIPT_FORMAT,
        version=1,
        request_sha256=review_request_sha256(request),
        snapshot_sha256=expect_sha256(
            result.snapshot_sha256, "snapshot_sha256"
        ),
        output_db_relative_path=_safe_machine_path(
            result.output_db_relative_path
        ),
        output_db_sha256=expect_sha256(
            result.output_db_sha256, "output_db_sha256"
        ),
        output_db_byte_size=_positive_size(
            result.output_db_byte_size, "output_db_byte_size"
        ),
        sources=sources,
        changed_original_names=changed_original_names,
        review_required=bool(changed_original_names),
    )


def reference_ingestion_receipt_document(
    receipt: ReferenceIngestionReceipt,
) -> dict[str, object]:
    """Return the canonical receipt document."""
    return {
        "format": REFERENCE_INGESTION_RECEIPT_FORMAT,
        "version": receipt.version,
        "request_sha256": receipt.request_sha256,
        "snapshot_sha256": receipt.snapshot_sha256,
        "output_db_relative_path": receipt.output_db_relative_path,
        "output_db_sha256": receipt.output_db_sha256,
        "output_db_byte_size": receipt.output_db_byte_size,
        "sources": [
            reference_source_document(source) for source in receipt.sources
        ],
        "changed_original_names": list(receipt.changed_original_names),
        "review_required": receipt.review_required,
    }


def decode_reference_ingestion_receipt(
    value: object,
) -> ReferenceIngestionReceipt:
    """Decode one strict generic receipt."""
    payload = expect_mapping(value, "reference_ingestion_receipt")
    required = {
        "format",
        "version",
        "request_sha256",
        "snapshot_sha256",
        "output_db_relative_path",
        "output_db_sha256",
        "output_db_byte_size",
        "sources",
        "changed_original_names",
        "review_required",
    }
    require_fields(payload, required, "reference_ingestion_receipt")
    reject_unknown(payload, required, "reference_ingestion_receipt")
    if payload.get("format") != REFERENCE_INGESTION_RECEIPT_FORMAT:
        raise ValueError("unsupported reference ingestion receipt format")
    version = expect_int(payload.get("version"), "version")
    if version != 1:
        raise ValueError(f"unsupported version: {version}")
    sources = _merge_source_results(
        tuple(
            _decode_source_result(item)
            for item in expect_sequence(payload.get("sources"), "sources")
        )
    )
    if not sources:
        raise ValueError("reference ingestion receipt requires sources")
    changed_names = _decode_string_tuple(
        payload.get("changed_original_names"), "changed_original_names"
    )
    review_required = expect_bool(
        payload.get("review_required"), "review_required"
    )
    if review_required != bool(changed_names):
        raise ValueError("review_required must match changed_original_names")
    return ReferenceIngestionReceipt(
        format=REFERENCE_INGESTION_RECEIPT_FORMAT,
        version=1,
        request_sha256=expect_sha256(
            payload.get("request_sha256"), "request_sha256"
        ),
        snapshot_sha256=expect_sha256(
            payload.get("snapshot_sha256"), "snapshot_sha256"
        ),
        output_db_relative_path=_safe_machine_path(
            payload.get("output_db_relative_path")
        ),
        output_db_sha256=expect_sha256(
            payload.get("output_db_sha256"), "output_db_sha256"
        ),
        output_db_byte_size=_positive_size(
            payload.get("output_db_byte_size"), "output_db_byte_size"
        ),
        sources=sources,
        changed_original_names=changed_names,
        review_required=review_required,
    )


def reference_ingestion_receipt_bytes(
    receipt: ReferenceIngestionReceipt,
) -> bytes:
    """Return canonical receipt bytes with one trailing newline."""
    return canonical_json.dump_bytes(
        reference_ingestion_receipt_document(receipt)
    ) + b"\n"


def reference_ingestion_receipt_sha256(
    receipt: ReferenceIngestionReceipt,
) -> str:
    """Return the exact byte-level receipt digest."""
    return hashlib.sha256(reference_ingestion_receipt_bytes(receipt)).hexdigest()


def _persist_create_only_bytes(path: Path, payload: bytes) -> Path:
    """Persist one immutable sidecar, permitting only byte-identical retries."""
    path.parent.mkdir(parents=True, exist_ok=True)
    parent = verified_regular_directory(
        path.parent,
        field="reference receipt directory",
    )
    target = parent / path.name
    try:
        descriptor = os.open(
            target,
            os.O_WRONLY
            | os.O_CREAT
            | os.O_EXCL
            | getattr(os, "O_NOFOLLOW", 0),
            0o600,
        )
    except FileExistsError:
        existing = verified_regular_file_below(
            parent,
            (path.name,),
            field=f"reference receipt artifact {path.name}",
        )
        if existing.read_bytes() == payload:
            return existing
        raise FileExistsError(
            "reference receipt sidecar already contains different bytes"
        ) from None
    with os.fdopen(descriptor, "wb") as stream:
        stream.write(payload)
        stream.flush()
        os.fsync(stream.fileno())
    return path


def _strict_json(raw: bytes) -> object:
    def reject_constant(value: str) -> object:
        raise ValueError(f"invalid JSON constant: {value}")

    def reject_duplicates(
        pairs: list[tuple[str, object]],
    ) -> dict[str, object]:
        result: dict[str, object] = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f"duplicate JSON key: {key}")
            result[key] = value
        return result

    try:
        return cast(
            object,
            json.loads(
                raw.decode("utf-8"),
                parse_constant=reject_constant,
                object_pairs_hook=reject_duplicates,
            ),
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(
            "reference receipt must be valid UTF-8 JSON"
        ) from exc


def load_reference_ingestion_receipt(
    layout: ReviewRunLayout,
) -> ReferenceIngestionReceipt:
    """Load and byte-revalidate the receipt and its evidence database."""
    receipt_path = verified_regular_file_below(
        layout.run_dir,
        ("machine", "reference-ingestion.json"),
        field="reference ingestion receipt",
    )
    raw = receipt_path.read_bytes()
    receipt = decode_reference_ingestion_receipt(_strict_json(raw))
    if raw != reference_ingestion_receipt_bytes(receipt):
        raise ValueError("reference receipt bytes are not canonical")
    digest_path = verified_regular_file_below(
        layout.run_dir,
        ("machine", "reference-ingestion.sha256"),
        field="reference ingestion receipt hash",
    )
    digest_raw = digest_path.read_bytes()
    expected_digest = f"{reference_ingestion_receipt_sha256(receipt)}\n".encode(
        "ascii"
    )
    if digest_raw != expected_digest:
        raise ValueError("reference receipt SHA-256 sidecar mismatch")
    if receipt.request_sha256 != layout.load_request_sha256():
        raise ValueError("reference receipt request SHA-256 is stale")
    request = layout.load_request()
    attachments = tuple(
        attachment
        for attachment in confirmed_attachments(request)
        if attachment.role in {"REFERENCE_DOCUMENT", "CASE_TABLE"}
    )
    _validate_result_coverage(
        attachments,
        ReferenceIngestionBatchResult(
            snapshot_sha256=receipt.snapshot_sha256,
            output_db_relative_path=receipt.output_db_relative_path,
            output_db_sha256=receipt.output_db_sha256,
            output_db_byte_size=receipt.output_db_byte_size,
            sources=receipt.sources,
        ),
    )
    if receipt.changed_original_names != _changed_names(attachments):
        raise ValueError("reference receipt changed names do not match request")
    if receipt.review_required != bool(receipt.changed_original_names):
        raise ValueError("reference receipt review flag is inconsistent")
    output_path = verified_regular_file_below(
        layout.run_dir,
        tuple(receipt.output_db_relative_path.split("/")),
        field="reference output database",
    )
    payload = output_path.read_bytes()
    if len(payload) != receipt.output_db_byte_size:
        raise ValueError("reference output database byte size mismatch")
    if hashlib.sha256(payload).hexdigest() != receipt.output_db_sha256:
        raise ValueError("reference output database SHA-256 mismatch")
    return receipt


def persist_reference_ingestion_receipt(
    layout: ReviewRunLayout,
    receipt: ReferenceIngestionReceipt,
) -> Path:
    """Publish one receipt atomically, permitting only byte-identical retries."""
    encoded = reference_ingestion_receipt_bytes(receipt)
    target = layout.reference_receipt_path
    target.parent.mkdir(parents=True, exist_ok=True)
    parent = verified_regular_directory(
        target.parent,
        field="reference receipt directory",
    )
    target = parent / target.name
    try:
        descriptor = os.open(
            target,
            os.O_WRONLY
            | os.O_CREAT
            | os.O_EXCL
            | getattr(os, "O_NOFOLLOW", 0),
            0o600,
        )
    except FileExistsError:
        existing = verified_regular_file_below(
            parent,
            (target.name,),
            field="reference ingestion receipt",
        )
        if existing.read_bytes() != encoded:
            raise FileExistsError(
                "reference receipt already contains different bytes"
            ) from None
    else:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(encoded)
            stream.flush()
            os.fsync(stream.fileno())
    _persist_create_only_bytes(
        layout.reference_receipt_sha256_path,
        f"{reference_ingestion_receipt_sha256(receipt)}\n".encode("ascii"),
    )
    return target


@dataclass(slots=True)
class SourceBatchReferenceBackend:
    """Delegate parser and EvidenceStore work to the existing importer."""

    batch: SourceBatch
    output_db_relative_path: str = "machine/evidence.sqlite"
    registry: ParserRegistry | None = None

    def ingest(
        self,
        *,
        request: ReviewRequest,
        attachments: tuple[ImmutableAttachment, ...],
        run_dir: Path,
    ) -> ReferenceIngestionBatchResult:
        del request
        output_relative = _safe_machine_path(self.output_db_relative_path)
        declared_paths = {
            source.source_path
            for source in self.batch.sources
            if source.role in {"REFERENCE_DOCUMENT", "CASE_TABLE"}
        }
        expected_paths = {
            attachment.stored_path for attachment in attachments
        }
        if declared_paths != expected_paths:
            raise ValueError(
                "source batch reference paths do not match request attachments"
            )
        output = run_dir.joinpath(*output_relative.split("/"))
        output.parent.mkdir(parents=True, exist_ok=True)
        verified_regular_directory(
            output.parent,
            field="source batch output directory",
        )
        report = import_source_batch(
            run_dir,
            self.batch,
            output,
            self.registry,
        )
        attachments_by_hash: dict[str, list[ImmutableAttachment]] = {}
        for attachment in attachments:
            attachments_by_hash.setdefault(
                attachment.sha256,
                [],
            ).append(attachment)
        sources: list[ReferenceSourceResult] = []
        for prepared in report.sources:
            if prepared.role not in {"REFERENCE_DOCUMENT", "CASE_TABLE"}:
                continue
            matching = attachments_by_hash.get(prepared.source_sha256, [])
            if not matching:
                raise ValueError(
                    "source batch report contains an unrequested reference source"
                )
            sources.append(
                ReferenceSourceResult(
                    attachment_ids=tuple(
                        sorted(
                            attachment.attachment_id
                            for attachment in matching
                        )
                    ),
                    original_names=tuple(
                        sorted(
                            {
                                attachment.original_name
                                for attachment in matching
                            }
                        )
                    ),
                    source_sha256=prepared.source_sha256,
                    document_id=prepared.document_id,
                    revision_id=prepared.revision_id,
                )
            )
        output = verified_regular_file_below(
            run_dir,
            tuple(output_relative.split("/")),
            field="source batch output database",
        )
        output_payload = output.read_bytes()
        return ReferenceIngestionBatchResult(
            snapshot_sha256=report.snapshot_hash,
            output_db_relative_path=output_relative,
            output_db_sha256=hashlib.sha256(output_payload).hexdigest(),
            output_db_byte_size=len(output_payload),
            sources=tuple(sources),
        )
