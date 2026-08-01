"""Immutable source manifests for PDFs and parser artifacts."""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

_CHUNK_SIZE = 1024 * 1024


@dataclass(frozen=True, slots=True)
class ArtifactHash:
    relative_path: str
    byte_size: int
    sha256: str


@dataclass(frozen=True, slots=True)
class SourceEntry:
    document_id: str
    revision_id: str
    relative_path: str
    source_hash: str
    byte_size: int
    page_count: int
    parser_artifacts: tuple[ArtifactHash, ...]


@dataclass(frozen=True, slots=True)
class VerificationError:
    code: str
    path: str
    expected: str | int | None
    actual: str | int | None


def sha256_file(path: Path) -> str:
    """Hash a file without loading it into memory."""
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(_CHUNK_SIZE), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _artifact_hash(path: Path, *, base: Path) -> ArtifactHash:
    resolved = path.resolve()
    try:
        relative = resolved.relative_to(base.resolve()).as_posix()
    except ValueError:
        relative = path.name
    return ArtifactHash(
        relative_path=relative,
        byte_size=resolved.stat().st_size,
        sha256=sha256_file(resolved),
    )


def build_source_entry(
    source_path: Path,
    *,
    document_id: str,
    page_count: int,
    parser_artifacts: Iterable[Path] = (),
    relative_to: Path | None = None,
) -> SourceEntry:
    """Build an immutable manifest entry from source bytes and parser files."""
    if not document_id:
        raise ValueError("document_id must not be empty")
    if page_count < 1:
        raise ValueError("page_count must be positive")
    source = source_path.resolve()
    if not source.is_file():
        raise FileNotFoundError(source)
    base = (relative_to or source.parent).resolve()
    try:
        relative_path = source.relative_to(base).as_posix()
    except ValueError as exc:
        raise ValueError("source_path must be inside relative_to") from exc
    source_hash = sha256_file(source)
    artifacts = tuple(
        sorted(
            (_artifact_hash(path, base=base) for path in parser_artifacts),
            key=lambda item: item.relative_path,
        )
    )
    return SourceEntry(
        document_id=document_id,
        revision_id=f"{document_id}-{source_hash[:12]}",
        relative_path=relative_path,
        source_hash=source_hash,
        byte_size=source.stat().st_size,
        page_count=page_count,
        parser_artifacts=artifacts,
    )


def verify_source_entry(
    entry: SourceEntry,
    source_path: Path,
    *,
    parser_artifacts: Iterable[Path] = (),
    actual_page_count: int | None = None,
) -> list[VerificationError]:
    """Return deterministic verification errors without mutating evidence."""
    errors: list[VerificationError] = []
    source = source_path.resolve()
    if not source.is_file():
        return [VerificationError("SOURCE_MISSING", str(source), entry.source_hash, None)]
    actual_size = source.stat().st_size
    if actual_size != entry.byte_size:
        errors.append(
            VerificationError("SOURCE_SIZE_MISMATCH", str(source), entry.byte_size, actual_size)
        )
    actual_hash = sha256_file(source)
    if actual_hash != entry.source_hash:
        errors.append(
            VerificationError("SOURCE_HASH_MISMATCH", str(source), entry.source_hash, actual_hash)
        )
    if actual_page_count is not None and actual_page_count != entry.page_count:
        errors.append(
            VerificationError(
                "PAGE_COUNT_MISMATCH",
                str(source),
                entry.page_count,
                actual_page_count,
            )
        )

    supplied = {path.name: path.resolve() for path in parser_artifacts}
    for artifact in entry.parser_artifacts:
        path = supplied.get(Path(artifact.relative_path).name)
        if path is None or not path.is_file():
            errors.append(
                VerificationError(
                    "PARSER_ARTIFACT_MISSING", artifact.relative_path, artifact.sha256, None
                )
            )
            continue
        actual_artifact_hash = sha256_file(path)
        if actual_artifact_hash != artifact.sha256:
            errors.append(
                VerificationError(
                    "PARSER_ARTIFACT_HASH_MISMATCH",
                    artifact.relative_path,
                    artifact.sha256,
                    actual_artifact_hash,
                )
            )
    return sorted(errors, key=lambda error: (error.code, error.path))
