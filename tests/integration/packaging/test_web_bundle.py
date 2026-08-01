import hashlib
import json
import subprocess
import sys
import zipfile
from pathlib import Path

from ansim_review.packaging.web_bundle import build_web_runtime_zip


def _workspace(root: Path) -> None:
    package = root / "src" / "ansim_review"
    package.mkdir(parents=True)
    (package / "__init__.py").write_text("", encoding="utf-8")
    cache = package / "__pycache__"
    cache.mkdir()
    (cache / "generated.cpython-313.pyc").write_bytes(b"generated")
    egg_info = package / "noise.egg-info"
    egg_info.mkdir()
    (egg_info / "PKG-INFO").write_text("generated", encoding="utf-8")
    (root / "evidence").mkdir()
    (root / "evidence" / "ansim-evidence.sqlite").write_bytes(
        b"SQLite format 3\0fixture"
    )
    (root / "rules" / "approved").mkdir(parents=True)
    (root / "rules" / "approved" / "R1.json").write_text(
        "{}",
        encoding="utf-8",
    )
    (root / "rules" / "manifests").mkdir()
    (root / "rules" / "manifests" / "active.json").write_text(
        "{}",
        encoding="utf-8",
    )
    (root / "web_runtime").mkdir()
    repository_root = Path(__file__).parents[3]
    bootstrap = repository_root / "web_runtime" / "bootstrap.py"
    (root / "web_runtime" / "bootstrap.py").write_text(
        bootstrap.read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    (root / "web_runtime" / "PROJECT_INSTRUCTIONS.md").write_text(
        "# instructions",
        encoding="utf-8",
    )
    (root / "02_source_pdf").mkdir()
    (root / "02_source_pdf" / "source.pdf").write_bytes(b"PDF")


def test_web_runtime_zip_is_install_free_offline_and_reproducible(
    tmp_path: Path,
) -> None:
    root = tmp_path / "workspace"
    _workspace(root)
    first = tmp_path / "first.zip"
    second = tmp_path / "second.zip"
    hash_one = build_web_runtime_zip(root, first)
    hash_two = build_web_runtime_zip(root, second)
    assert hash_one == hash_two == hashlib.sha256(first.read_bytes()).hexdigest()
    assert first.read_bytes() == second.read_bytes()

    extracted = tmp_path / "extracted"
    with zipfile.ZipFile(first) as archive:
        archive.extractall(extracted)
    completed = subprocess.run(
        [sys.executable, "bootstrap.py", "--self-test"],
        cwd=extracted,
        text=True,
        capture_output=True,
        check=True,
    )
    assert completed.stdout.strip() == "WEB_RUNTIME_SELF_TEST_PASS"
    assert not (
        extracted
        / "ansim_review"
        / "__pycache__"
        / "generated.cpython-313.pyc"
    ).exists()
    assert not (
        extracted
        / "ansim_review"
        / "noise.egg-info"
    ).exists()
    assert (extracted / "evidence" / "ansim-evidence.sqlite").is_file()
    assert (extracted / "rules" / "approved" / "R1.json").is_file()

    formula_manifest = json.loads(
        (extracted / "formulas" / "manifest.json").read_text(encoding="utf-8")
    )
    assert [item["formula_id"] for item in formula_manifest["formulas"]] == [
        "FRONTAGE_RATIO"
    ]

    sample_request = json.loads(
        (extracted / "examples" / "sample-request.json").read_text(
            encoding="utf-8"
        )
    )
    assert sample_request == {
        "formula_id": "FRONTAGE_RATIO",
        "formula_version": "1.0.0",
        "inputs": {
            "frontage_length_m": "30",
            "perimeter_length_m": "320",
            "threshold_ratio": "0.125",
        },
    }
    assert not (extracted / "02_source_pdf").exists()
