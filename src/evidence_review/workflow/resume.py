"""Resume and reproducibility helpers for deterministic review artifacts."""

from __future__ import annotations

from pathlib import Path

from evidence_review.filesystem_trust import (
    verified_regular_directory,
    verified_regular_file_below,
)


def _json_files(root: Path) -> tuple[Path, ...]:
    trusted_root = verified_regular_directory(root, field="machine artifact root")
    verified_files: list[Path] = []
    for path in trusted_root.rglob("*.json"):
        relative = path.relative_to(trusted_root)
        verified_files.append(
            verified_regular_file_below(
                trusted_root,
                relative.parts,
                field="machine artifact",
            )
        )
    return tuple(
        sorted(
            verified_files,
            key=lambda path: path.relative_to(trusted_root).as_posix(),
        )
    )


def machine_artifacts_byte_equal(left: Path, right: Path) -> bool:
    """Compare deterministic machine JSON bytes and member names exactly."""
    left_files = _json_files(left)
    right_files = _json_files(right)
    left_root = verified_regular_directory(left, field="left machine artifact root")
    right_root = verified_regular_directory(right, field="right machine artifact root")
    left_names = tuple(path.relative_to(left_root).as_posix() for path in left_files)
    right_names = tuple(path.relative_to(right_root).as_posix() for path in right_files)
    if left_names != right_names:
        return False
    return all(
        left_path.read_bytes() == right_path.read_bytes()
        for left_path, right_path in zip(left_files, right_files, strict=True)
    )


__all__ = ["machine_artifacts_byte_equal"]
