"""Resume and reproducibility helpers for deterministic review artifacts."""

from __future__ import annotations

from pathlib import Path


def _json_files(root: Path) -> tuple[Path, ...]:
    if not root.is_dir():
        raise FileNotFoundError(root)
    return tuple(
        sorted(
            (path for path in root.rglob("*.json") if path.is_file()),
            key=lambda path: path.relative_to(root).as_posix(),
        )
    )


def machine_artifacts_byte_equal(left: Path, right: Path) -> bool:
    """Compare deterministic machine JSON bytes and member names exactly."""
    left_files = _json_files(left)
    right_files = _json_files(right)
    left_names = tuple(path.relative_to(left).as_posix() for path in left_files)
    right_names = tuple(path.relative_to(right).as_posix() for path in right_files)
    if left_names != right_names:
        return False
    return all(
        left_path.read_bytes() == right_path.read_bytes()
        for left_path, right_path in zip(left_files, right_files, strict=True)
    )


__all__ = ["machine_artifacts_byte_equal"]
