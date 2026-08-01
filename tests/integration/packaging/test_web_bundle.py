import hashlib
import subprocess
import sys
import zipfile
from pathlib import Path

from ansim_review.packaging.web_bundle import build_web_runtime_zip


def _workspace(root: Path) -> None:
    package = root / "src" / "ansim_review"
    package.mkdir(parents=True)
    (package / "__init__.py").write_text("", encoding="utf-8")
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
    (root / "formulas").mkdir()
    (root / "formulas" / "manifest.json").write_text("{}", encoding="utf-8")
    (root / "examples").mkdir()
    (root / "examples" / "sample-request.json").write_text(
        '{"question":"test"}',
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
    assert (extracted / "evidence" / "ansim-evidence.sqlite").is_file()
    assert (extracted / "rules" / "approved" / "R1.json").is_file()
    assert (extracted / "formulas" / "manifest.json").is_file()
    assert (extracted / "examples" / "sample-request.json").is_file()
    assert not (extracted / "02_source_pdf").exists()
