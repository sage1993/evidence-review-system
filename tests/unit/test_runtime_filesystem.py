from __future__ import annotations

from pathlib import Path

from evidence_review.runtime_filesystem import (
    create_inherited_temp_directory,
    create_inherited_temp_file,
)


def test_inherited_temp_directory_is_created_by_parent_acl_inheritance(
    tmp_path: Path,
) -> None:
    parent = tmp_path / "workspace-cache"
    parent.mkdir()

    with create_inherited_temp_directory(parent, prefix=".revision-") as temporary:
        assert temporary.parent == parent
        assert temporary.is_dir()

    assert not temporary.exists()


def test_inherited_temp_file_is_created_by_parent_acl_inheritance(
    tmp_path: Path,
) -> None:
    parent = tmp_path / "workspace-state"
    parent.mkdir()

    with create_inherited_temp_file(parent, prefix=".binding-") as (path, stream):
        stream.write(b"state")
        stream.flush()
        assert path.parent == parent
        assert path.read_bytes() == b"state"

    assert not path.exists()
