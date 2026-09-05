from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

from evidence_review.filesystem_trust import (
    REPARSE_POINT_ATTRIBUTE,
    verified_regular_directory,
    verified_regular_file_below,
)


def test_verified_regular_file_below_accepts_normal_file(tmp_path: Path) -> None:
    root = tmp_path / "root"
    nested = root / "nested"
    nested.mkdir(parents=True)
    target = nested / "asset.png"
    target.write_bytes(b"png")

    resolved = verified_regular_file_below(
        root,
        ("nested", "asset.png"),
        field="asset",
    )

    assert resolved == target.resolve(strict=True)


def test_verified_regular_directory_accepts_normal_directory(tmp_path: Path) -> None:
    root = tmp_path / "root"
    root.mkdir()

    assert verified_regular_directory(root, field="root") == root.resolve(strict=True)


def test_verified_regular_file_below_rejects_final_symlink(tmp_path: Path) -> None:
    root = tmp_path / "root"
    root.mkdir()
    target = root / "target.png"
    target.write_bytes(b"png")
    link = root / "asset.png"
    try:
        link.symlink_to(target)
    except OSError as error:
        pytest.skip(f"symlink creation unavailable: {error}")

    with pytest.raises(ValueError, match="symlink|reparse"):
        verified_regular_file_below(root, ("asset.png",), field="asset")


def test_verified_regular_file_below_rejects_intermediate_symlink(tmp_path: Path) -> None:
    root = tmp_path / "root"
    root.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "asset.png").write_bytes(b"png")
    link = root / "nested"
    try:
        link.symlink_to(outside, target_is_directory=True)
    except OSError as error:
        pytest.skip(f"directory symlink creation unavailable: {error}")

    with pytest.raises(ValueError, match="symlink|reparse"):
        verified_regular_file_below(root, ("nested", "asset.png"), field="asset")


def test_verified_regular_file_below_rejects_parent_traversal(tmp_path: Path) -> None:
    root = tmp_path / "root"
    root.mkdir()
    outside = tmp_path / "outside.png"
    outside.write_bytes(b"outside")

    with pytest.raises(ValueError, match="relative path component"):
        verified_regular_file_below(root, ("..", "outside.png"), field="asset")


def test_verified_regular_file_below_rejects_regular_file_outside_root_via_link(
    tmp_path: Path,
) -> None:
    root = tmp_path / "root"
    root.mkdir()
    outside = tmp_path / "outside.png"
    outside.write_bytes(b"outside")
    link = root / "asset.png"
    try:
        link.symlink_to(outside)
    except OSError as error:
        pytest.skip(f"symlink creation unavailable: {error}")

    with pytest.raises(ValueError, match="symlink|reparse"):
        verified_regular_file_below(root, ("asset.png",), field="asset")


def test_verified_regular_directory_rejects_symlink(tmp_path: Path) -> None:
    target = tmp_path / "target"
    target.mkdir()
    link = tmp_path / "root"
    try:
        link.symlink_to(target, target_is_directory=True)
    except OSError as error:
        pytest.skip(f"directory symlink creation unavailable: {error}")

    with pytest.raises(ValueError, match="symlink|reparse"):
        verified_regular_directory(link, field="root")


@pytest.mark.skipif(sys.platform != "win32", reason="Windows junction semantics")
def test_verified_regular_file_below_rejects_windows_junction_component(
    tmp_path: Path,
) -> None:
    root = tmp_path / "root"
    root.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "asset.png").write_bytes(b"png")
    junction = root / "nested"
    completed = subprocess.run(
        ["cmd.exe", "/d", "/c", "mklink", "/J", str(junction), str(outside)],
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout).strip()
        pytest.skip(
            "junction creation unavailable: "
            f"exit={completed.returncode}; detail={detail or '<empty>'}"
        )

    status = junction.lstat()
    assert getattr(status, "st_file_attributes", 0) & REPARSE_POINT_ATTRIBUTE
    with pytest.raises(ValueError, match="reparse"):
        verified_regular_file_below(root, ("nested", "asset.png"), field="asset")


@pytest.mark.skipif(sys.platform != "win32", reason="Windows reparse semantics")
def test_verified_regular_file_below_rejects_windows_reparse_final_component(
    tmp_path: Path,
) -> None:
    root = tmp_path / "root"
    root.mkdir()
    target = root / "target.png"
    target.write_bytes(b"png")
    link = root / "asset.png"
    try:
        os.symlink(target, link, target_is_directory=False)
    except OSError as error:
        pytest.skip(f"Windows file reparse creation unavailable: {error}")

    status = link.lstat()
    assert getattr(status, "st_file_attributes", 0) & REPARSE_POINT_ATTRIBUTE
    with pytest.raises(ValueError, match="symlink|reparse"):
        verified_regular_file_below(root, ("asset.png",), field="asset")
