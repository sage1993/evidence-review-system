"""Canonical filesystem trust boundary for repository-controlled assets."""
from __future__ import annotations

import os
import stat
from collections.abc import Sequence
from pathlib import Path

REPARSE_POINT_ATTRIBUTE = 0x400


def _status(path: Path, *, field: str) -> os.stat_result:
    try:
        return path.lstat()
    except PermissionError:
        raise
    except OSError as error:
        raise FileNotFoundError(f"{field} not found: {path}") from error


def _reject_link_or_reparse(
    path: Path,
    status: os.stat_result,
    *,
    field: str,
) -> None:
    if stat.S_ISLNK(status.st_mode):
        raise ValueError(f"{field} must not contain a symlink: {path}")
    if getattr(status, "st_file_attributes", 0) & REPARSE_POINT_ATTRIBUTE:
        raise ValueError(f"{field} must not contain a reparse point: {path}")


def _absolute_components(path: Path) -> tuple[Path, ...]:
    """Return existing path components without resolving links."""
    absolute = path if path.is_absolute() else Path.cwd() / path
    anchor = Path(absolute.anchor)
    current = anchor
    components: list[Path] = []
    for part in absolute.parts:
        if part == absolute.anchor:
            continue
        current = current / part
        components.append(current)
    return tuple(components)


def verified_regular_directory(path: Path, *, field: str) -> Path:
    """Return a strict resolved directory after rejecting links and reparse points."""
    if not isinstance(path, Path):
        path = Path(path)
    components = _absolute_components(path)
    if not components:
        resolved_root = path.resolve(strict=True)
        if not resolved_root.is_dir():
            raise ValueError(f"{field} must be a directory: {resolved_root}")
        return resolved_root

    for component in components:
        status = _status(component, field=field)
        _reject_link_or_reparse(component, status, field=field)
        if not stat.S_ISDIR(status.st_mode):
            raise ValueError(f"{field} must be a directory: {component}")

    try:
        resolved = path.resolve(strict=True)
    except PermissionError:
        raise
    except OSError as error:
        raise FileNotFoundError(f"{field} not found: {path}") from error
    if not resolved.is_dir():
        raise ValueError(f"{field} must be a directory: {resolved}")
    return resolved


def verified_regular_file(path: Path, *, field: str) -> Path:
    """Return a strict resolved regular file after rejecting links and reparse points."""
    if not isinstance(path, Path):
        path = Path(path)
    components = _absolute_components(path)
    if not components:
        raise FileNotFoundError(f"{field} not found: {path}")
    for index, component in enumerate(components):
        status = _status(component, field=field)
        _reject_link_or_reparse(component, status, field=field)
        if index < len(components) - 1:
            if not stat.S_ISDIR(status.st_mode):
                raise ValueError(f"{field} path component must be a directory: {component}")
        elif not stat.S_ISREG(status.st_mode):
            raise ValueError(f"{field} must be a regular file: {component}")
    try:
        resolved = path.resolve(strict=True)
    except PermissionError:
        raise
    except OSError as error:
        raise FileNotFoundError(f"{field} not found: {path}") from error
    if not resolved.is_file():
        raise ValueError(f"{field} must be a regular file: {resolved}")
    return resolved


def _relative_component(value: str, *, field: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{field} relative path component must be a string")
    if value in {"", ".", ".."}:
        raise ValueError(f"{field} relative path component is invalid: {value!r}")
    if "/" in value or "\\" in value:
        raise ValueError(f"{field} relative path component is invalid: {value!r}")
    if Path(value).is_absolute() or Path(value).drive:
        raise ValueError(f"{field} relative path component is invalid: {value!r}")
    return value


def verified_regular_file_below(
    root: Path,
    relative_parts: Sequence[str],
    *,
    field: str,
) -> Path:
    """Return a verified regular file strictly contained below ``root``.

    Every component below the verified root is inspected with ``lstat`` before any
    resolving operation. Symlinks and Windows reparse points are rejected at the
    component where they occur.
    """
    verified_root = verified_regular_directory(root, field=f"{field} root")
    parts = tuple(_relative_component(part, field=field) for part in relative_parts)
    if not parts:
        raise ValueError(f"{field} relative path must identify a file")

    current = verified_root
    for index, part in enumerate(parts):
        current = current / part
        status = _status(current, field=field)
        _reject_link_or_reparse(current, status, field=field)
        if index < len(parts) - 1:
            if not stat.S_ISDIR(status.st_mode):
                raise ValueError(f"{field} path component must be a directory: {current}")
        elif not stat.S_ISREG(status.st_mode):
            raise ValueError(f"{field} must be a regular file: {current}")

    try:
        resolved = current.resolve(strict=True)
    except PermissionError:
        raise
    except OSError as error:
        raise FileNotFoundError(f"{field} not found: {current}") from error
    try:
        resolved.relative_to(verified_root)
    except ValueError as error:
        raise ValueError(f"{field} escaped trusted root: {resolved}") from error
    return resolved


def verified_create_target_below(
    root: Path,
    relative_parts: Sequence[str],
    *,
    field: str,
) -> Path:
    """Validate a create-only target and reject existing link/reparse components.

    The final component must not exist. Missing parent components are allowed so
    the caller can create a new artifact tree below the already verified root.
    The caller remains responsible for using create-only publication semantics.
    """
    verified_root = verified_regular_directory(root, field=f"{field} root")
    parts = tuple(_relative_component(part, field=field) for part in relative_parts)
    if not parts:
        raise ValueError(f"{field} relative path must identify a target")

    current = verified_root
    for index, part in enumerate(parts):
        current = current / part
        try:
            status = current.lstat()
        except FileNotFoundError:
            return current.joinpath(*parts[index + 1 :])
        except PermissionError:
            raise
        except OSError as error:
            raise FileNotFoundError(f"{field} not found: {current}") from error
        _reject_link_or_reparse(current, status, field=field)
        if index < len(parts) - 1:
            if not stat.S_ISDIR(status.st_mode):
                raise ValueError(f"{field} path component must be a directory: {current}")
        else:
            raise FileExistsError(f"{field} already exists: {current}")
    return current


__all__ = [
    "REPARSE_POINT_ATTRIBUTE",
    "verified_create_target_below",
    "verified_regular_directory",
    "verified_regular_file",
    "verified_regular_file_below",
]
