import hashlib
import json
import shutil
import sqlite3
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest

from ansim_review.packaging.web_bundle import build_web_runtime_zip


def _workspace(root: Path) -> None:
    repository_root = Path(__file__).parents[3]
    shutil.copytree(
        repository_root / "src" / "evidence_review",
        root / "src" / "evidence_review",
    )
    shutil.copytree(
        repository_root / "src" / "ansim_review",
        root / "src" / "ansim_review",
    )
    package = root / "src" / "ansim_review"
    cache = package / "__pycache__"
    cache.mkdir(exist_ok=True)
    (cache / "generated.cpython-313.pyc").write_bytes(b"generated")
    egg_info = package / "noise.egg-info"
    egg_info.mkdir()
    (egg_info / "PKG-INFO").write_text("generated", encoding="utf-8")
    (root / "evidence").mkdir()
    connection = sqlite3.connect(root / "evidence" / "evidence.sqlite")
    connection.execute("CREATE TABLE probe(id INTEGER PRIMARY KEY)")
    connection.execute("INSERT INTO probe(id) VALUES(1)")
    connection.commit()
    connection.close()
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
    for filename in ("bootstrap.py", "runtime_runner.py"):
        source = repository_root / "web_runtime" / filename
        (root / "web_runtime" / filename).write_text(
            source.read_text(encoding="utf-8"),
            encoding="utf-8",
        )
    (root / "tests/golden/questions").mkdir(parents=True)
    (root / "tests/golden/questions/ansim_cases.json").write_text(
        "[]",
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
    assert (extracted / "evidence" / "evidence.sqlite").is_file()
    assert (extracted / "evidence_review" / "__main__.py").is_file()
    assert (extracted / "ansim_review" / "__main__.py").is_file()
    assert (extracted / "examples" / "golden-cases.json").is_file()
    assert (extracted / "rules" / "approved" / "R1.json").is_file()

    runtime_manifest = json.loads(
        (extracted / "runtime-manifest.json").read_text(encoding="utf-8")
    )
    assert runtime_manifest["format"] == "evidence-review/chatgpt-web-runtime"

    formula_manifest = json.loads(
        (extracted / "formulas" / "manifest.json").read_text(
            encoding="utf-8"
        )
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

    for module in ("evidence_review", "ansim_review"):
        completed = subprocess.run(
            [sys.executable, "-m", module, "--help"],
            cwd=extracted,
            text=True,
            capture_output=True,
            check=True,
        )
        assert completed.stdout.startswith("usage: evidence-review")


def _extract_runtime(root: Path, tmp_path: Path) -> Path:
    archive = tmp_path / "runtime.zip"
    build_web_runtime_zip(root, archive)
    extracted = tmp_path / "extracted"
    with zipfile.ZipFile(archive) as bundle:
        bundle.extractall(extracted)
    return extracted


def _run_self_test(extracted: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "bootstrap.py", "--self-test"],
        cwd=extracted,
        text=True,
        capture_output=True,
    )


def _runtime_manifest(extracted: Path) -> tuple[Path, dict[str, object]]:
    manifest_path = extracted / "runtime-manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    return manifest_path, manifest


def _write_runtime_manifest(path: Path, manifest: dict[str, object]) -> None:
    path.write_text(
        json.dumps(manifest, ensure_ascii=False, sort_keys=True),
        encoding="utf-8",
    )


def _refresh_database_manifest(extracted: Path) -> None:
    manifest_path, manifest = _runtime_manifest(extracted)
    digest = hashlib.sha256(
        (extracted / "evidence" / "evidence.sqlite").read_bytes()
    ).hexdigest()
    files = manifest["files"]
    assert isinstance(files, list)
    for item in files:
        assert isinstance(item, dict)
        if item["path"] == "evidence/evidence.sqlite":
            item["sha256"] = digest
            item["size"] = (extracted / "evidence" / "evidence.sqlite").stat().st_size
    _write_runtime_manifest(manifest_path, manifest)


def test_web_runtime_self_test_rejects_corrupt_sqlite(tmp_path: Path) -> None:
    root = tmp_path / "workspace"
    _workspace(root)
    extracted = _extract_runtime(root, tmp_path)
    database = extracted / "evidence" / "evidence.sqlite"
    database.write_bytes(b"not-a-sqlite-database")
    _refresh_database_manifest(extracted)

    completed = _run_self_test(extracted)

    assert completed.returncode != 0
    assert "WEB_RUNTIME_SELF_TEST_PASS" not in completed.stdout
    assert "SQLITE_INTEGRITY_FAILED" in completed.stderr


def test_web_runtime_self_test_rejects_foreign_key_errors(tmp_path: Path) -> None:
    root = tmp_path / "workspace"
    _workspace(root)
    extracted = _extract_runtime(root, tmp_path)
    database = extracted / "evidence" / "evidence.sqlite"
    connection = sqlite3.connect(database)
    connection.execute("PRAGMA foreign_keys = OFF")
    connection.execute("CREATE TABLE parent(id INTEGER PRIMARY KEY)")
    connection.execute(
        "CREATE TABLE child(parent_id INTEGER REFERENCES parent(id))"
    )
    connection.execute("INSERT INTO child(parent_id) VALUES(99)")
    connection.commit()
    connection.close()
    _refresh_database_manifest(extracted)

    completed = _run_self_test(extracted)

    assert completed.returncode != 0
    assert "WEB_RUNTIME_SELF_TEST_PASS" not in completed.stdout
    assert "SQLITE_INTEGRITY_FAILED" in completed.stderr


@pytest.mark.parametrize(
    "unsafe_path",
    [
        "../outside.txt",
        "rules/../../outside.txt",
        "/absolute/path",
        "C:/Windows/System32/file",
        r"C:\Windows\System32\file",
        r"\\server\share\file",
        r"rules\approved\R1.json",
        ".",
        "..",
    ],
)
def test_web_runtime_self_test_rejects_unsafe_manifest_paths(
    tmp_path: Path,
    unsafe_path: str,
) -> None:
    root = tmp_path / "workspace"
    _workspace(root)
    extracted = _extract_runtime(root, tmp_path)
    manifest_path, manifest = _runtime_manifest(extracted)
    files = manifest["files"]
    assert isinstance(files, list)
    files.append(
        {
            "path": unsafe_path,
            "sha256": "0" * 64,
            "size": 0,
        }
    )
    _write_runtime_manifest(manifest_path, manifest)

    completed = _run_self_test(extracted)

    assert completed.returncode != 0
    assert "UNSAFE_RUNTIME_PATH" in completed.stderr


@pytest.mark.parametrize(
    "manifest",
    [
        {},
        {"format": "wrong", "version": 1, "files": []},
        {
            "format": "evidence-review/chatgpt-web-runtime",
            "version": 2,
            "files": [],
        },
        {
            "format": "evidence-review/chatgpt-web-runtime",
            "version": 1,
            "files": [],
            "extra": True,
        },
        {
            "format": "evidence-review/chatgpt-web-runtime",
            "version": 1,
            "files": "not-a-list",
        },
    ],
)
def test_web_runtime_self_test_rejects_invalid_manifest_schema(
    tmp_path: Path,
    manifest: dict[str, object],
) -> None:
    root = tmp_path / "workspace"
    _workspace(root)
    extracted = _extract_runtime(root, tmp_path)
    manifest_path = extracted / "runtime-manifest.json"
    _write_runtime_manifest(manifest_path, manifest)

    completed = _run_self_test(extracted)

    assert completed.returncode != 0
    assert "INVALID_RUNTIME_MANIFEST" in completed.stderr


def test_web_runtime_self_test_rejects_duplicate_and_casefold_paths(
    tmp_path: Path,
) -> None:
    root = tmp_path / "workspace"
    _workspace(root)
    extracted = _extract_runtime(root, tmp_path)
    manifest_path, manifest = _runtime_manifest(extracted)
    files = manifest["files"]
    assert isinstance(files, list)
    first = dict(files[0])
    first["path"] = str(first["path"]).upper()
    files.append(first)
    _write_runtime_manifest(manifest_path, manifest)

    completed = _run_self_test(extracted)

    assert completed.returncode != 0
    assert "INVALID_RUNTIME_MANIFEST" in completed.stderr


def test_web_runtime_self_test_checks_size_before_hash(tmp_path: Path) -> None:
    root = tmp_path / "workspace"
    _workspace(root)
    extracted = _extract_runtime(root, tmp_path)
    manifest_path, manifest = _runtime_manifest(extracted)
    files = manifest["files"]
    assert isinstance(files, list)
    item = files[0]
    assert isinstance(item, dict)
    item["size"] = int(item["size"]) + 1
    item["sha256"] = "0" * 64
    _write_runtime_manifest(manifest_path, manifest)

    completed = _run_self_test(extracted)

    assert completed.returncode != 0
    assert "RUNTIME_FILE_SIZE_MISMATCH" in completed.stderr
    assert "RUNTIME_FILE_HASH_MISMATCH" not in completed.stderr


def test_web_runtime_self_test_rejects_hash_mismatch(tmp_path: Path) -> None:
    root = tmp_path / "workspace"
    _workspace(root)
    extracted = _extract_runtime(root, tmp_path)
    manifest_path, manifest = _runtime_manifest(extracted)
    files = manifest["files"]
    assert isinstance(files, list)
    item = files[0]
    assert isinstance(item, dict)
    item["sha256"] = "0" * 64
    _write_runtime_manifest(manifest_path, manifest)

    completed = _run_self_test(extracted)

    assert completed.returncode != 0
    assert "RUNTIME_FILE_HASH_MISMATCH" in completed.stderr
