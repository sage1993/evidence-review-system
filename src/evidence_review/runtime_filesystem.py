"""Windows-safe temporary filesystem primitives for workspace-local artifacts."""

from __future__ import annotations

import shutil
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import BinaryIO


def _unique_path(parent: Path, prefix: str, suffix: str = "") -> Path:
    parent = Path(parent)
    if not prefix:
        raise ValueError("temporary path prefix must not be empty")
    parent.mkdir(parents=True, exist_ok=True)
    for _ in range(32):
        candidate = parent / f"{prefix}{uuid.uuid4().hex}{suffix}"
        if not candidate.exists():
            return candidate
    raise FileExistsError(f"could not allocate a unique temporary path below {parent}")


@contextmanager
def create_inherited_temp_directory(parent: Path, *, prefix: str) -> Iterator[Path]:
    """Create a directory with the already trusted parent's inherited ACL."""
    path = _unique_path(parent, prefix)
    path.mkdir()
    try:
        yield path
    finally:
        shutil.rmtree(path, ignore_errors=True)


@contextmanager
def create_inherited_temp_file(
    parent: Path,
    *,
    prefix: str,
    suffix: str = ".tmp",
    delete: bool = True,
) -> Iterator[tuple[Path, BinaryIO]]:
    """Open a create-only file whose ACL is inherited from ``parent``.

    Callers performing an atomic ``os.replace`` may set ``delete=False`` and
    own cleanup after publication.
    """
    path = _unique_path(parent, prefix, suffix)
    stream = path.open("xb")
    try:
        yield path, stream
    finally:
        stream.close()
        if delete:
            path.unlink(missing_ok=True)


__all__ = ["create_inherited_temp_directory", "create_inherited_temp_file"]
