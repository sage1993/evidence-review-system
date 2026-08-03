"""Resolve one OpenDataLoader source identity from a strict source-batch manifest."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from ansim_review.contracts.source_batch import SourceItem, decode_source_batch
from ansim_review.parser_reproducibility.contract import ParserRunMetadata
from ansim_review.parsing.source_batch_importer import derive_document_id


class SourceIdentityAuthorityError(ValueError):
    """Authority failure with a stable machine-readable reason code."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass(frozen=True, slots=True)
class SourceIdentity:
    source_relative_path: str
    source_sha256: str
    source_size: int
    source_page_count: int
    document_id: str
    revision_id: str


def _reject_duplicate_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise SourceIdentityAuthorityError("SOURCE_MANIFEST_INVALID")
        result[key] = value
    return result


def _decode_source_manifest(path: Path) -> tuple[SourceItem, ...]:
    try:
        payload = json.loads(
            path.read_text(encoding="utf-8-sig"),
            object_pairs_hook=_reject_duplicate_keys,
        )
        return decode_source_batch(payload).sources
    except SourceIdentityAuthorityError:
        raise
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        raise SourceIdentityAuthorityError("SOURCE_MANIFEST_INVALID") from exc


def resolve_source_identity(
    source_manifest: Path,
    run_metadata: ParserRunMetadata,
) -> SourceIdentity:
    """Select exactly one source and bind it to parser-run authority."""

    matches = tuple(
        source
        for source in _decode_source_manifest(source_manifest)
        if source.source_path == run_metadata.source_relative_path
    )
    if not matches:
        raise SourceIdentityAuthorityError("SOURCE_MANIFEST_ENTRY_MISSING")
    if len(matches) != 1:
        raise SourceIdentityAuthorityError("SOURCE_MANIFEST_ENTRY_DUPLICATE")
    source = matches[0]
    if source.parser is None or source.parser.kind != "OPENDATALOADER_JSON":
        raise SourceIdentityAuthorityError("SOURCE_MANIFEST_PARSER_KIND_MISMATCH")

    document_id = derive_document_id(
        run_metadata.source_sha256,
        source.document_id,
    )
    revision_id = f"{document_id}-{run_metadata.source_sha256[:12]}"
    if document_id != run_metadata.document_id:
        raise SourceIdentityAuthorityError("SOURCE_IDENTITY_MISMATCH")
    if revision_id != run_metadata.revision_id:
        raise SourceIdentityAuthorityError("SOURCE_REVISION_MISMATCH")
    return SourceIdentity(
        source_relative_path=source.source_path,
        source_sha256=run_metadata.source_sha256,
        source_size=run_metadata.source_size,
        source_page_count=run_metadata.source_page_count,
        document_id=document_id,
        revision_id=revision_id,
    )
