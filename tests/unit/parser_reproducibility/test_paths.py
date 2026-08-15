from __future__ import annotations

from pathlib import Path

import pytest

from evidence_review.parser_reproducibility.paths import (
    canonical_relative_path,
    resolve_run_artifact,
)


@pytest.mark.parametrize(
    "name",
    ["../x", "/x", "C:/x", "a\\b", "a/./b", "a//b"],
)
def test_rejects_unsafe_artifact_name(tmp_path: Path, name: str) -> None:
    tmp_path.mkdir(exist_ok=True)
    with pytest.raises(ValueError):
        resolve_run_artifact(tmp_path, name)


def test_resolves_regular_file_under_root(tmp_path: Path) -> None:
    root = tmp_path / "run"
    root.mkdir()
    target = root / "document.json"
    target.write_text("{}", encoding="utf-8")

    assert resolve_run_artifact(root, "document.json") == target.resolve()
    assert canonical_relative_path(root, target) == "document.json"


def test_rejects_symlink_escape_when_supported(tmp_path: Path) -> None:
    root = tmp_path / "run"
    outside = tmp_path / "outside.json"
    root.mkdir()
    outside.write_text("{}", encoding="utf-8")
    link = root / "document.json"
    try:
        link.symlink_to(outside)
    except OSError:
        pytest.skip("operating system refused symlink creation")

    with pytest.raises(ValueError, match="escapes"):
        resolve_run_artifact(root, "document.json")
