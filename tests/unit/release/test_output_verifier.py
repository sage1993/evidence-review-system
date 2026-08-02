from __future__ import annotations

import importlib


def test_release_output_verifier_exposes_canonical_report_contract() -> None:
    verifier = importlib.import_module("ansim_review.release.output_verifier")
    formats = importlib.import_module("ansim_review.contracts.formats")

    assert callable(verifier.validate_release_output)
    assert (
        formats.RELEASE_OUTPUT_VALIDATION_FORMAT
        == "evidence-review/release-output-validation"
    )
