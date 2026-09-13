"""Reproducible standard-library ChatGPT web runtime ZIP export."""
from __future__ import annotations

import hashlib
import shutil
import tempfile
import zipfile
from pathlib import Path

from evidence_review.canonical_json import dump_bytes
from evidence_review.contracts.formats import WEB_RUNTIME_FORMAT
from evidence_review.math_engine.formulas import DEFAULT_REGISTRY
from evidence_review.math_engine.manifest import formula_manifest_payload
from evidence_review.packaging.file_selection import iter_bundle_source_files
from evidence_review.packaging.project_instructions import render_project_instructions
from evidence_review.packaging.runtime_packages import runtime_package_roots
from evidence_review.release.config import (
    DEFAULT_RELEASE_CONFIG,
    resolve_evidence_database,
)

_FIXED_TIME = (1980, 1, 1, 0, 0, 0)
_SAMPLE_REQUEST: dict[str, object] = {
    "formula_id": "FRONTAGE_RATIO",
    "formula_version": "1.0.0",
    "inputs": {
        "frontage_length_m": "30",
        "perimeter_length_m": "320",
        "threshold_ratio": "0.125",
    },
}


def _copy_tree(source: Path, destination: Path) -> None:
    for path in iter_bundle_source_files(source):
        target = destination / path.relative_to(source)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, target)


def _copy_file(source: Path, destination: Path) -> None:
    if not source.is_file():
        raise FileNotFoundError(source)
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, destination)


def _runtime_files(root: Path) -> list[Path]:
    manifest_path = root / "runtime-manifest.json"
    return [
        path
        for path in sorted(root.rglob("*"))
        if path.is_file() and path != manifest_path
    ]


def _runtime_inventory(root: Path) -> set[str]:
    return {path.relative_to(root).as_posix() for path in _runtime_files(root)}


def _manifest(root: Path) -> dict[str, object]:
    return {
        "format": WEB_RUNTIME_FORMAT,
        "version": 1,
        "files": [
            {
                "path": path.relative_to(root).as_posix(),
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                "size": path.stat().st_size,
            }
            for path in _runtime_files(root)
        ],
    }


def _write_runtime_manifest(stage: Path) -> None:
    selected_inventory = _runtime_inventory(stage)
    manifest = _manifest(stage)
    files = manifest.get("files")
    if not isinstance(files, list):
        raise RuntimeError("runtime manifest files payload is invalid")
    manifest_inventory: set[str] = set()
    for entry in files:
        if not isinstance(entry, dict):
            raise RuntimeError("runtime manifest file entry is invalid")
        path_value = entry.get("path")
        if not isinstance(path_value, str):
            raise RuntimeError("runtime manifest file path is invalid")
        manifest_inventory.add(path_value)
    if manifest_inventory != selected_inventory:
        raise RuntimeError("runtime manifest inventory mismatch")

    manifest_path = stage / "runtime-manifest.json"
    manifest_path.write_bytes(dump_bytes(manifest))
    if _runtime_inventory(stage) != manifest_inventory:
        raise RuntimeError("runtime inventory changed while writing manifest")


def _write_generated_runtime_inputs(stage: Path) -> None:
    formulas = stage / "formulas" / "manifest.json"
    formulas.parent.mkdir(parents=True, exist_ok=True)
    formula_payload = formula_manifest_payload(DEFAULT_REGISTRY.values())
    formulas.write_bytes(dump_bytes(formula_payload))

    sample = stage / "examples" / "sample-request.json"
    sample.parent.mkdir(parents=True, exist_ok=True)
    sample.write_bytes(dump_bytes(_SAMPLE_REQUEST))


def _write_zip(source: Path, output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists():
        raise FileExistsError(output)
    with zipfile.ZipFile(
        output,
        "x",
        compression=zipfile.ZIP_DEFLATED,
        compresslevel=9,
    ) as archive:
        for path in sorted(item for item in source.rglob("*") if item.is_file()):
            relative = path.relative_to(source).as_posix()
            info = zipfile.ZipInfo(relative, _FIXED_TIME)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            info.create_system = 3
            archive.writestr(
                info,
                path.read_bytes(),
                compress_type=zipfile.ZIP_DEFLATED,
                compresslevel=9,
            )


def build_public_runtime_zip(workspace_root: Path, output_zip: Path) -> str:
    """Build a software-only runtime ZIP without user workspace artifacts."""
    with tempfile.TemporaryDirectory(
        prefix="evidence-review-public-runtime-"
    ) as temporary:
        stage = Path(temporary) / "runtime"
        stage.mkdir()
        _copy_file(
            workspace_root / "web_runtime" / "bootstrap.py",
            stage / "bootstrap.py",
        )
        (stage / "public-runtime.txt").write_text(
            "Evidence Review System public software runtime.\n",
            encoding="utf-8",
            newline="\n",
        )
        (stage / "PROJECT_INSTRUCTIONS.md").write_text(
            render_project_instructions(),
            encoding="utf-8",
            newline="\n",
        )
        for name, source in runtime_package_roots(workspace_root / "src"):
            _copy_tree(source, stage / name)
        _write_generated_runtime_inputs(stage)
        _write_runtime_manifest(stage)
        _write_zip(stage, output_zip)
    return hashlib.sha256(output_zip.read_bytes()).hexdigest()


def build_web_runtime_zip(
    workspace_root: Path,
    output_zip: Path,
    *,
    evidence_database_path: Path | None = None,
    expected_evidence_sha256: str | None = None,
) -> str:
    """Build byte-reproducible runtime ZIP without source PDFs or installation."""
    with tempfile.TemporaryDirectory(
        prefix="evidence-review-web-runtime-"
    ) as temporary:
        stage = Path(temporary) / "runtime"
        stage.mkdir()
        _copy_file(
            workspace_root / "web_runtime" / "bootstrap.py",
            stage / "bootstrap.py",
        )
        runner = workspace_root / "web_runtime" / "runtime_runner.py"
        if runner.is_file():
            _copy_file(runner, stage / "runtime_runner.py")
        (stage / "PROJECT_INSTRUCTIONS.md").write_text(
            render_project_instructions(),
            encoding="utf-8",
            newline="\n",
        )
        for name, source in runtime_package_roots(workspace_root / "src"):
            _copy_tree(source, stage / name)
        selected_evidence = evidence_database_path or resolve_evidence_database(
            workspace_root,
            DEFAULT_RELEASE_CONFIG,
        )
        copied_evidence = stage / "evidence" / "evidence.sqlite"
        _copy_file(selected_evidence, copied_evidence)
        if (
            expected_evidence_sha256 is not None
            and hashlib.sha256(copied_evidence.read_bytes()).hexdigest()
            != expected_evidence_sha256
        ):
            raise ValueError("RELEASE_EVIDENCE_COPY_HASH_MISMATCH")
        _copy_tree(
            workspace_root / "rules" / "approved",
            stage / "rules" / "approved",
        )
        _copy_tree(
            workspace_root / "rules" / "manifests",
            stage / "rules" / "manifests",
        )
        _write_generated_runtime_inputs(stage)
        golden = (
            workspace_root / "tests" / "golden" / "questions" / "ansim_cases.json"
        )
        if golden.is_file():
            _copy_file(golden, stage / "examples" / "golden-cases.json")
        _write_runtime_manifest(stage)
        _write_zip(stage, output_zip)
    return hashlib.sha256(output_zip.read_bytes()).hexdigest()
