from __future__ import annotations

import base64
import hashlib
import importlib.metadata
from pathlib import Path

import pytest

import evidence_review.diagnostics as diagnostics


def _wheel_install(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    site = tmp_path / "site-packages"
    package = site / "evidence_review"
    package.mkdir(parents=True)
    content = b'__version__ = "0.2.1"\n'
    (package / "__init__.py").write_bytes(content)
    info = site / "evidence_review_system-0.2.1.dist-info"
    info.mkdir()
    (info / "METADATA").write_text(
        "Metadata-Version: 2.1\nName: evidence-review-system\nVersion: 0.2.1\n",
        encoding="utf-8",
    )
    digest = base64.urlsafe_b64encode(hashlib.sha256(content).digest()).decode().rstrip("=")
    (info / "RECORD").write_text(
        f"evidence_review/__init__.py,sha256={digest},{len(content)}\n", encoding="utf-8"
    )
    distribution = importlib.metadata.PathDistribution(info)
    monkeypatch.setattr(diagnostics.importlib.metadata, "distribution", lambda _: distribution)
    monkeypatch.setattr(diagnostics, "_package_root", lambda _: package)
    monkeypatch.setattr(diagnostics, "_dependency_diagnostics", lambda: ())
    monkeypatch.delenv("PYTHONPATH", raising=False)
    monkeypatch.chdir(tmp_path)
    return package


@pytest.mark.parametrize("nearby_checkout", [False, True])
def test_installed_wheel_is_authority_independent_of_checkout(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, nearby_checkout: bool,
) -> None:
    package = _wheel_install(tmp_path, monkeypatch)
    checkout = tmp_path / "governance"
    if nearby_checkout:
        (checkout / "src" / "evidence_review").mkdir(parents=True)
        (checkout / "pyproject.toml").write_text("[project]\n", encoding="utf-8")
        monkeypatch.chdir(checkout)
    result = diagnostics.collect_runtime_diagnostics()
    assert result.status == "OK"
    document = result.to_document()
    assert document["runtime_mode"] == "installed"
    assert document["package_root"] == str(package)
    assert document["distribution_package_root"] == str(package)
    assert len(document["package_source_sha256"]) == 64


def test_installed_runtime_detects_pythonpath_bypass(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    _wheel_install(tmp_path, monkeypatch)
    monkeypatch.setenv("PYTHONPATH", str(tmp_path / "other-checkout" / "src"))
    assert diagnostics.collect_runtime_diagnostics().status == "BYPASS_DETECTED"


def test_installed_runtime_rejects_modified_package(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    package = _wheel_install(tmp_path, monkeypatch)
    (package / "__init__.py").write_text("# post-install patch\n", encoding="utf-8")
    assert diagnostics.collect_runtime_diagnostics().status == "SOURCE_MISMATCH"


def test_production_mode_rejects_source_checkout_shadowing_wheel(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    _wheel_install(tmp_path, monkeypatch)
    checkout = tmp_path / "shadow"
    source = checkout / "src" / "evidence_review"
    source.mkdir(parents=True)
    (checkout / "pyproject.toml").write_text("[project]\n", encoding="utf-8")
    monkeypatch.setattr(diagnostics, "_package_root", lambda _: source)
    monkeypatch.chdir(checkout)
    monkeypatch.setenv("PYTHONPATH", str(source.parent))
    result = diagnostics.collect_runtime_diagnostics(runtime_mode="installed")
    assert result.status == "BYPASS_DETECTED"


def test_cli_blocks_bypass_before_command_dispatch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str],
) -> None:
    from evidence_review.cli import main

    _wheel_install(tmp_path, monkeypatch)
    monkeypatch.setenv("PYTHONPATH", str(tmp_path / "shadow"))
    assert main(["workspace", "active", "--repository-root", str(tmp_path)]) == 2
    assert '"status": "BYPASS_DETECTED"' in capsys.readouterr().out


def test_cli_exposes_installed_acceptance_mode(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str],
) -> None:
    from evidence_review.cli import main

    _wheel_install(tmp_path, monkeypatch)
    assert main(["--runtime-mode", "installed", "doctor"]) == 0
    assert '"runtime_mode": "installed"' in capsys.readouterr().out


def test_expected_candidate_rejects_stale_wheel(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    _wheel_install(tmp_path, monkeypatch)
    result = diagnostics.collect_runtime_diagnostics(expected_package_sha256="a" * 64)
    assert result.status == "SOURCE_MISMATCH"


def test_unrecorded_importable_file_is_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    package = _wheel_install(tmp_path, monkeypatch)
    (package / "shadow.py").write_text("# unexpected\n", encoding="utf-8")
    assert diagnostics.collect_runtime_diagnostics().status == "SOURCE_MISMATCH"


def test_installed_wheel_does_not_require_git_for_nearby_checkout(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    _wheel_install(tmp_path, monkeypatch)
    checkout = tmp_path / "checkout"
    checkout.mkdir()

    def missing_git(*args, **kwargs):
        raise FileNotFoundError("git unavailable")

    monkeypatch.setattr(diagnostics.subprocess, "run", missing_git)
    result = diagnostics.collect_runtime_diagnostics(checkout)
    assert result.status == "OK"
    assert result.repository_head is None
