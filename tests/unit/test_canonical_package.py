from __future__ import annotations

import importlib
import subprocess
import sys
from pathlib import Path


def test_evidence_review_is_importable_as_canonical_package() -> None:
    package = importlib.import_module("evidence_review")
    cli = importlib.import_module("evidence_review.cli")
    contracts = importlib.import_module("evidence_review.contracts.source_batch")

    assert package.CANONICAL_PACKAGE == "evidence_review"
    assert callable(cli.main)
    assert contracts.decode_source_batch is not None


def test_canonical_and_legacy_submodules_share_identity() -> None:
    canonical = importlib.import_module("evidence_review.contracts.source_batch")
    legacy = importlib.import_module("ansim_review.contracts.source_batch")

    assert canonical is legacy
    assert canonical.SourceBatch is legacy.SourceBatch


def test_python_module_entrypoint_uses_generic_program_name() -> None:
    completed = subprocess.run(
        [sys.executable, "-m", "evidence_review", "--help"],
        text=True,
        capture_output=True,
        check=True,
    )

    assert completed.stdout.startswith("usage: evidence-review")


def test_console_scripts_target_canonical_package() -> None:
    pyproject = Path("pyproject.toml").read_text(encoding="utf-8")

    assert 'evidence-review = "evidence_review.cli:main"' in pyproject
    assert 'ansim-review = "evidence_review.cli:main"' in pyproject
    assert 'packages = ["evidence_review", "ansim_review"]' in pyproject


def test_legacy_module_entrypoint_remains_compatible() -> None:
    completed = subprocess.run(
        [sys.executable, "-m", "ansim_review", "--help"],
        text=True,
        capture_output=True,
        check=True,
    )

    assert completed.stdout.startswith("usage: evidence-review")
