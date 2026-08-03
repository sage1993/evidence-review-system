from pathlib import Path

from ansim_review.packaging.codex_bundle import render_validation_document

README = Path("README.md")
OFFLINE = Path("docs/OFFLINE_EXECUTION.md")


def test_final_release_output_verification_is_documented() -> None:
    combined = "\n".join(
        path.read_text(encoding="utf-8") for path in (README, OFFLINE)
    )

    for required in (
        "bundle-manifest.json",
        "runtime-manifest.json",
        "RELEASE_OUTPUT_VALIDATION_FAILED",
        "without extracting",
        "case-fold collisions",
        "SHA-256",
    ):
        assert required in combined


def test_codex_validation_document_uses_full_offline_sequence() -> None:
    validation = render_validation_document()
    assert validation.startswith("# Offline validation\n")
    assert "python -m ansim_review documentation validate --help" in validation
    assert "python -m compileall -q src" in validation
    assert "pytest -q" in validation
    assert "ruff check src tests" in validation
    assert "mypy src" in validation
    assert "\r" not in validation
