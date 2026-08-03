"""Immutable manifest construction for one OpenDataLoader parser run."""

from __future__ import annotations

import hashlib
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Literal, cast

from pypdf import PdfReader

from ansim_review.canonical_json import dump_bytes
from ansim_review.parser_reproducibility.contract import (
    ParserRunMetadata,
    ReproducibilityConfig,
    decode_parser_run_metadata,
)
from ansim_review.parser_reproducibility.opendataloader import (
    OpenDataLoaderArtifact,
    decode_opendataloader_json,
)
from ansim_review.parser_reproducibility.paths import (
    canonical_relative_path,
    resolve_run_artifact,
)
from ansim_review.parser_reproducibility.source_identity import SourceIdentity
from ansim_review.parser_reproducibility.warnings import (
    ParserWarning,
    WarningContext,
    extract_opendataloader_warnings,
)
from ansim_review.parsing.source_manifest import sha256_file


@dataclass(frozen=True, slots=True)
class ParserRunManifest:
    format: Literal["evidence-review/parser-run-manifest"]
    version: Literal[1]
    run_id: str
    source_relative_path: str
    source_sha256: str
    source_size: int
    source_page_count: int
    parser_page_count: int
    document_id: str
    revision_id: str
    parser_kind: str
    parser_version: str
    adapter_version: int
    configuration_sha256: str
    platform_family: str
    json_relative_path: str
    json_sha256: str
    json_size: int
    markdown_relative_path: str
    markdown_sha256: str
    markdown_size: int
    warning_source_relative_paths: tuple[str, ...]
    warning_count: int
    warning_codes: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class LoadedParserRun:
    manifest: ParserRunManifest
    artifact: OpenDataLoaderArtifact
    json_bytes: bytes
    markdown_bytes: bytes
    warnings: tuple[ParserWarning, ...]
    run_root: Path


def count_source_pdf_pages(path: Path) -> int:
    """Count pages independently from parser output."""

    with path.open("rb") as stream:
        count = len(PdfReader(stream, strict=True).pages)
    if count < 1:
        raise ValueError("source PDF must contain at least one page")
    return count


def read_parser_run_metadata(run_root: Path) -> ParserRunMetadata:
    """Read strict immutable parser-run authority from one artifact directory."""

    metadata_path = resolve_run_artifact(run_root, "parser-run.json")
    return decode_parser_run_metadata(metadata_path.read_bytes())


def _configuration_sha256(configuration: object) -> str:
    return hashlib.sha256(dump_bytes(configuration)).hexdigest().upper()


def _run_id(authority: dict[str, object]) -> str:
    digest = hashlib.sha256(dump_bytes(authority)).hexdigest()[:24].upper()
    return f"PRUN-{digest}"


def _single_name(names: tuple[str, ...], field: str) -> str:
    if len(names) != 1:
        raise ValueError(f"{field} must contain exactly one artifact in version 1")
    return names[0]


def _read_optional_log(
    run_root: Path,
    config: ReproducibilityConfig,
) -> tuple[str | None, tuple[str, ...]]:
    log_text: str | None = None
    present: list[str] = []
    for name in config.warning_sources:
        if name in config.json_artifact_names:
            present.append(name)
            continue
        candidate = run_root.resolve() / Path(*name.split("/"))
        if not candidate.exists():
            continue
        path = resolve_run_artifact(run_root, name)
        try:
            text = path.read_text(encoding="utf-8-sig")
        except UnicodeDecodeError as exc:
            raise ValueError(f"warning source must be UTF-8: {name}") from exc
        if name == "parser.log":
            log_text = text
        present.append(canonical_relative_path(run_root, path))
    return log_text, tuple(sorted(set(present)))


def _require_identity(
    metadata: ParserRunMetadata,
    identity: SourceIdentity,
) -> None:
    checks = (
        (
            metadata.source_relative_path == identity.source_relative_path,
            "source path does not match parser-run.json",
        ),
        (
            metadata.source_sha256 == identity.source_sha256,
            "source hash does not match parser-run.json",
        ),
        (
            metadata.source_size == identity.source_size,
            "source size does not match parser-run.json",
        ),
        (
            metadata.source_page_count == identity.source_page_count,
            "source page count does not match parser-run.json",
        ),
        (
            metadata.document_id == identity.document_id,
            "document identity does not match parser-run.json",
        ),
        (
            metadata.revision_id == identity.revision_id,
            "revision identity does not match parser-run.json",
        ),
    )
    for valid, message in checks:
        if not valid:
            raise ValueError(message)


def load_parser_run_for_identity(
    identity: SourceIdentity,
    run_root: Path,
    config: ReproducibilityConfig,
) -> LoadedParserRun:
    """Load one run using source identity already verified by an authority."""

    root = run_root.resolve()
    metadata = read_parser_run_metadata(root)
    if metadata.parser_kind != config.parser_kind:
        raise ValueError("parser run kind does not match configuration")
    if metadata.adapter_version != config.adapter_version:
        raise ValueError("parser run adapter version does not match configuration")
    _require_identity(metadata, identity)

    json_name = _single_name(config.json_artifact_names, "json_artifact_names")
    markdown_name = _single_name(
        config.markdown_artifact_names,
        "markdown_artifact_names",
    )
    json_path = resolve_run_artifact(root, json_name)
    markdown_path = resolve_run_artifact(root, markdown_name)
    json_bytes = json_path.read_bytes()
    markdown_bytes = markdown_path.read_bytes()
    try:
        markdown_bytes.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ValueError("OpenDataLoader Markdown must be UTF-8") from exc
    artifact = decode_opendataloader_json(json_bytes)
    if artifact.page_count != identity.source_page_count:
        raise ValueError("parser page count does not match parser-run.json")

    configuration_sha256 = _configuration_sha256(metadata.parser_configuration)
    json_sha256 = hashlib.sha256(json_bytes).hexdigest().upper()
    markdown_sha256 = hashlib.sha256(markdown_bytes).hexdigest().upper()
    run_id = _run_id(
        {
            "source_sha256": identity.source_sha256,
            "parser_kind": metadata.parser_kind,
            "parser_version": metadata.parser_version,
            "adapter_version": metadata.adapter_version,
            "configuration_sha256": configuration_sha256,
            "json_sha256": json_sha256,
            "markdown_sha256": markdown_sha256,
        }
    )
    log_text, warning_paths = _read_optional_log(root, config)
    warning_context = WarningContext(
        source_sha256=identity.source_sha256,
        document_id=identity.document_id,
        revision_id=identity.revision_id,
        parser_kind=metadata.parser_kind,
        parser_version=metadata.parser_version,
        configuration_sha256=configuration_sha256,
        run_id=run_id,
        run_root=root,
        parser_page_count=artifact.page_count,
    )
    warnings = extract_opendataloader_warnings(
        artifact,
        log_text,
        warning_context,
    )
    manifest = ParserRunManifest(
        format="evidence-review/parser-run-manifest",
        version=1,
        run_id=run_id,
        source_relative_path=identity.source_relative_path,
        source_sha256=identity.source_sha256,
        source_size=identity.source_size,
        source_page_count=identity.source_page_count,
        parser_page_count=artifact.page_count,
        document_id=identity.document_id,
        revision_id=identity.revision_id,
        parser_kind=metadata.parser_kind,
        parser_version=metadata.parser_version,
        adapter_version=metadata.adapter_version,
        configuration_sha256=configuration_sha256,
        platform_family=metadata.platform_family,
        json_relative_path=canonical_relative_path(root, json_path),
        json_sha256=json_sha256,
        json_size=len(json_bytes),
        markdown_relative_path=canonical_relative_path(root, markdown_path),
        markdown_sha256=markdown_sha256,
        markdown_size=len(markdown_bytes),
        warning_source_relative_paths=warning_paths,
        warning_count=len(warnings),
        warning_codes=tuple(sorted({warning.code for warning in warnings})),
    )
    return LoadedParserRun(
        manifest=manifest,
        artifact=artifact,
        json_bytes=json_bytes,
        markdown_bytes=markdown_bytes,
        warnings=warnings,
        run_root=root,
    )


def load_parser_run(
    source_pdf: Path,
    run_root: Path,
    config: ReproducibilityConfig,
) -> LoadedParserRun:
    """Load a run after independently verifying actual source PDF bytes."""

    source = source_pdf.resolve()
    if not source.is_file():
        raise FileNotFoundError(source)
    metadata = read_parser_run_metadata(run_root)
    identity = SourceIdentity(
        source_relative_path=metadata.source_relative_path,
        source_sha256=sha256_file(source),
        source_size=source.stat().st_size,
        source_page_count=count_source_pdf_pages(source),
        document_id=metadata.document_id,
        revision_id=metadata.revision_id,
    )
    return load_parser_run_for_identity(identity, run_root, config)


def build_parser_run_manifest(
    source_pdf: Path,
    run_root: Path,
    config: ReproducibilityConfig,
) -> ParserRunManifest:
    """Build one verified manifest from immutable evidence files."""

    return load_parser_run(source_pdf, run_root, config).manifest


def parser_run_manifest_document(
    manifest: ParserRunManifest,
) -> dict[str, object]:
    """Convert a manifest to canonical-JSON-ready values."""

    return cast(dict[str, object], asdict(manifest))
