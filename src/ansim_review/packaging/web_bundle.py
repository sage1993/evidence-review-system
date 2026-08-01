"""Reproducible standard-library ChatGPT web runtime ZIP export."""
from __future__ import annotations

import hashlib
import shutil
import tempfile
import zipfile
from pathlib import Path

from ansim_review.canonical_json import dump_bytes
from ansim_review.packaging.project_instructions import render_project_instructions

_FIXED_TIME = (1980, 1, 1, 0, 0, 0)


def _copy_tree(source: Path, destination: Path) -> None:
    if not source.is_dir():
        raise FileNotFoundError(source)
    for path in sorted(source.rglob("*")):
        if path.is_file():
            target = destination / path.relative_to(source)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(path, target)


def _copy_file(source: Path, destination: Path) -> None:
    if not source.is_file():
        raise FileNotFoundError(source)
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, destination)


def _runtime_files(root: Path) -> list[Path]:
    return [
        path
        for path in sorted(root.rglob("*"))
        if path.is_file() and path.name != "runtime-manifest.json"
    ]


def _manifest(root: Path) -> dict[str, object]:
    return {
        "format": "ansim/chatgpt-web-runtime",
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


def build_web_runtime_zip(workspace_root: Path, output_zip: Path) -> str:
    """Build byte-reproducible runtime ZIP without source PDFs or installation."""
    with tempfile.TemporaryDirectory(prefix="ansim-web-runtime-") as temporary:
        stage = Path(temporary) / "runtime"
        stage.mkdir()
        _copy_file(
            workspace_root / "web_runtime" / "bootstrap.py",
            stage / "bootstrap.py",
        )
        (stage / "PROJECT_INSTRUCTIONS.md").write_text(
            render_project_instructions(),
            encoding="utf-8",
            newline="\n",
        )
        _copy_tree(
            workspace_root / "src" / "ansim_review",
            stage / "ansim_review",
        )
        _copy_file(
            workspace_root / "evidence" / "ansim-evidence.sqlite",
            stage / "evidence" / "ansim-evidence.sqlite",
        )
        _copy_tree(
            workspace_root / "rules" / "approved",
            stage / "rules" / "approved",
        )
        _copy_tree(
            workspace_root / "rules" / "manifests",
            stage / "rules" / "manifests",
        )
        _copy_file(
            workspace_root / "formulas" / "manifest.json",
            stage / "formulas" / "manifest.json",
        )
        _copy_file(
            workspace_root / "examples" / "sample-request.json",
            stage / "examples" / "sample-request.json",
        )
        (stage / "runtime-manifest.json").write_bytes(dump_bytes(_manifest(stage)))
        _write_zip(stage, output_zip)
    return hashlib.sha256(output_zip.read_bytes()).hexdigest()
