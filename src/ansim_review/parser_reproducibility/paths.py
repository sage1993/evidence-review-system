"""Safe relative path handling for immutable parser run artifacts."""

from __future__ import annotations

from pathlib import Path, PurePosixPath


def validate_posix_relative_name(name: str) -> PurePosixPath:
    """Return one safe POSIX relative artifact path."""

    if not isinstance(name, str) or not name:
        raise ValueError("artifact name must be a non-empty string")
    if "\\" in name:
        raise ValueError("artifact name must not contain backslashes")
    if ":" in name:
        raise ValueError("artifact name must not contain a drive or scheme")
    if name.startswith("/"):
        raise ValueError("artifact name must be relative")
    components = name.split("/")
    if any(component in {"", ".", ".."} for component in components):
        raise ValueError("artifact name contains an unsafe path component")
    path = PurePosixPath(name)
    if path.is_absolute():
        raise ValueError("artifact name must be relative")
    return path


def resolve_run_artifact(root: Path, name: str) -> Path:
    """Resolve a declared artifact and reject symlink or junction escapes."""

    relative = validate_posix_relative_name(name)
    resolved_root = root.resolve()
    if not resolved_root.is_dir():
        raise FileNotFoundError(resolved_root)
    candidate = (resolved_root / Path(*relative.parts)).resolve()
    if not candidate.is_relative_to(resolved_root):
        raise ValueError("artifact path escapes run root")
    if not candidate.is_file():
        raise FileNotFoundError(candidate)
    return candidate


def canonical_relative_path(root: Path, path: Path) -> str:
    """Return a canonical POSIX path for a file under *root*."""

    resolved_root = root.resolve()
    resolved_path = path.resolve()
    if not resolved_path.is_relative_to(resolved_root):
        raise ValueError("path escapes run root")
    if not resolved_path.is_file():
        raise FileNotFoundError(resolved_path)
    return resolved_path.relative_to(resolved_root).as_posix()
