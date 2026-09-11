"""Installed-wheel coverage for the ReviewMatter runtime boundary."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import zipfile
from pathlib import Path

from evidence_review.packaging.file_selection import iter_bundle_source_files
from evidence_review.packaging.runtime_packages import (
    REVIEW_MATTER_RUNTIME_PATHS,
)

ROOT = Path(__file__).resolve().parents[3]


def _runtime_source_paths() -> set[str]:
    source = ROOT / "src"
    return {
        (Path(package) / path.relative_to(source / package)).as_posix()
        for package in (
            "evidence_review/review_matter",
            "evidence_review/navigation",
            "evidence_review/workbench",
        )
        for path in iter_bundle_source_files(source / package)
    }


def _wheel(tmp_path: Path) -> Path:
    wheel_directory = tmp_path / "wheel"
    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "pip",
            "wheel",
            "--no-deps",
            "--no-build-isolation",
            "--wheel-dir",
            str(wheel_directory),
            str(ROOT),
        ],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    wheels = tuple(wheel_directory.glob("evidence_review_system-*.whl"))
    assert len(wheels) == 1
    return wheels[0]


def _resource_hashes(pythonpath: Path, cwd: Path) -> dict[str, str]:
    completed = subprocess.run(
        [
            sys.executable,
            "-c",
            """
import hashlib
import json
from importlib.resources import files

resources = {
    path: hashlib.sha256(
        files(package).joinpath(resource).read_bytes()
    ).hexdigest()
    for package, resource, path in (
        (
            "evidence_review.review_matter",
            "schema.sql",
            "evidence_review/review_matter/schema.sql",
        ),
        (
            "evidence_review.workbench",
            "assets/workbench.css",
            "evidence_review/workbench/assets/workbench.css",
        ),
        (
            "evidence_review.workbench",
            "assets/workbench.js",
            "evidence_review/workbench/assets/workbench.js",
        ),
    )
}
print(json.dumps(resources, sort_keys=True))
""",
        ],
        cwd=cwd,
        env={**os.environ, "PYTHONPATH": str(pythonpath)},
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    return json.loads(completed.stdout)


def _file_hashes(root: Path, relative_paths: set[str]) -> dict[str, str]:
    return {
        relative: hashlib.sha256((root / relative).read_bytes()).hexdigest()
        for relative in sorted(relative_paths)
    }


def test_wheel_contains_all_review_matter_runtime_modules_schema_and_assets(
    tmp_path: Path,
) -> None:
    wheel = _wheel(tmp_path)
    source_paths = _runtime_source_paths()

    assert set(REVIEW_MATTER_RUNTIME_PATHS) <= source_paths
    with zipfile.ZipFile(wheel) as archive:
        wheel_paths = set(archive.namelist())

    assert source_paths <= wheel_paths


def test_installed_wheel_resources_match_the_source_checkout(tmp_path: Path) -> None:
    wheel = _wheel(tmp_path)
    installed = tmp_path / "installed"
    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "pip",
            "install",
            "--no-deps",
            "--target",
            str(installed),
            str(wheel),
        ],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr

    source = _resource_hashes(ROOT / "src", tmp_path)
    installed_hashes = _resource_hashes(installed, tmp_path)

    assert installed_hashes == source
    assert _file_hashes(ROOT / "src", _runtime_source_paths()) == _file_hashes(
        installed,
        _runtime_source_paths(),
    )
