from pathlib import Path

import pytest

from evidence_review.evidence.lineage_migration import _publish_atomically


def _paths(root: Path, prefix: str) -> tuple[Path, Path, Path]:
    return (
        root / f"{prefix}-database.sqlite",
        root / f"{prefix}-aliases.json",
        root / f"{prefix}-report.json",
    )


def test_publication_never_overwrites_concurrently_created_first_output(
    tmp_path: Path,
) -> None:
    temporary = _paths(tmp_path, "temporary")
    final = _paths(tmp_path, "final")
    for index, path in enumerate(temporary):
        path.write_bytes(f"ours-{index}".encode())
    final[0].write_bytes(b"concurrent-database")

    with pytest.raises(FileExistsError):
        _publish_atomically(temporary, final)

    assert final[0].read_bytes() == b"concurrent-database"
    assert not final[1].exists()
    assert not final[2].exists()


def test_partial_publication_is_rolled_back_without_deleting_concurrent_file(
    tmp_path: Path,
) -> None:
    temporary = _paths(tmp_path, "temporary")
    final = _paths(tmp_path, "final")
    for index, path in enumerate(temporary):
        path.write_bytes(f"ours-{index}".encode())
    final[1].write_bytes(b"concurrent-aliases")

    with pytest.raises(FileExistsError):
        _publish_atomically(temporary, final)

    assert not final[0].exists()
    assert final[1].read_bytes() == b"concurrent-aliases"
    assert not final[2].exists()
