from __future__ import annotations

import json
import zipfile
from collections.abc import Callable
from pathlib import Path

import pytest

from evidence_review.packaging.web_bundle import (
    build_public_runtime_zip,
    build_web_runtime_zip,
)
from tests.integration.packaging.test_web_bundle import _workspace


@pytest.mark.parametrize(
    "builder",
    [build_web_runtime_zip, build_public_runtime_zip],
)
def test_generated_manifest_exactly_matches_bundled_file_inventory(
    tmp_path: Path,
    builder: Callable[[Path, Path], str],
) -> None:
    workspace = tmp_path / "workspace"
    _workspace(workspace)
    archive_path = tmp_path / "runtime.zip"

    builder(workspace, archive_path)

    with zipfile.ZipFile(archive_path) as archive:
        archive_files = {
            name
            for name in archive.namelist()
            if not name.endswith("/") and name != "runtime-manifest.json"
        }
        manifest = json.loads(archive.read("runtime-manifest.json"))

    manifest_files = {entry["path"] for entry in manifest["files"]}
    assert manifest_files == archive_files
