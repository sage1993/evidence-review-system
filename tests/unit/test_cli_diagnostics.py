from __future__ import annotations

from pathlib import Path

import evidence_review.diagnostics as diagnostics
from evidence_review.diagnostics import DependencyDiagnostic, RuntimeDiagnostics


def test_runtime_diagnostics_to_document_is_stable() -> None:
    diagnostic = RuntimeDiagnostics(
        status="OK",
        executable=Path("C:/Python313/python.exe"),
        command_path=Path("C:/venv/Scripts/evidence-review.exe"),
        distribution_version="0.1.0",
        working_directory=Path("C:/repo"),
        repository_root=Path("C:/repo"),
        repository_head="a" * 40,
        package_root=Path("C:/repo/src/evidence_review"),
        package_checkout_match=True,
        dependencies=(
            DependencyDiagnostic("pypdf", "pypdf", "OK", "5.9.0"),
            DependencyDiagnostic("pypdfium2", "pypdfium2", "OK", "5.12.0"),
            DependencyDiagnostic("Pillow", "PIL", "OK", "12.0.0"),
        ),
    )

    document = diagnostic.to_document()

    assert document["status"] == "OK"
    assert document["repository_head"] == "a" * 40
    assert document["package_checkout_match"] is True
    assert [item["distribution"] for item in document["dependencies"]] == [
        "pypdf",
        "pypdfium2",
        "Pillow",
    ]


def test_source_mismatch_has_priority(monkeypatch, tmp_path: Path) -> None:
    checkout = tmp_path / "checkout-a"
    expected_package = checkout / "src" / "evidence_review"
    actual_package = tmp_path / "checkout-b" / "src" / "evidence_review"
    expected_package.mkdir(parents=True)
    (checkout / "pyproject.toml").write_text("[project]\nname='x'\n", encoding="utf-8")
    actual_package.mkdir(parents=True)

    monkeypatch.setattr(diagnostics, "_package_root", lambda _name: actual_package)
    monkeypatch.setattr(diagnostics, "_dependency_diagnostics", lambda: ())

    result = diagnostics.collect_runtime_diagnostics(checkout)

    assert result.status == "SOURCE_MISMATCH"


def test_missing_dependency_is_structured(monkeypatch, tmp_path: Path) -> None:
    checkout = tmp_path / "checkout"
    (checkout / "src" / "evidence_review").mkdir(parents=True)
    (checkout / "pyproject.toml").write_text("[project]\nname='x'\n", encoding="utf-8")
    monkeypatch.setattr(
        diagnostics,
        "_package_root",
        lambda _name: checkout / "src" / "evidence_review",
    )
    monkeypatch.setattr(
        diagnostics,
        "_dependency_diagnostics",
        lambda: (DependencyDiagnostic("pypdfium2", "pypdfium2", "MISSING", None),),
    )

    result = diagnostics.collect_runtime_diagnostics(checkout)

    assert result.status == "DEPENDENCY_MISSING"
