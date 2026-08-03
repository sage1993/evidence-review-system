from __future__ import annotations

from pathlib import Path

from ansim_review.parser_reproducibility.opendataloader import (
    OpenDataLoaderArtifact,
)
from ansim_review.parser_reproducibility.warnings import (
    WarningContext,
    extract_opendataloader_warnings,
)


def context(tmp_path: Path) -> WarningContext:
    return WarningContext(
        source_sha256="0" * 64,
        document_id="DOC-TEST",
        revision_id="DOC-TEST-000000000000",
        parser_kind="opendataloader",
        parser_version="1.2.3",
        configuration_sha256="A" * 64,
        run_id="PRUN-" + "A" * 24,
        run_root=tmp_path / "run-a",
        parser_page_count=4,
    )


def minimal_artifact(warnings: object = None) -> OpenDataLoaderArtifact:
    payload: dict[str, object] = {"number of pages": 4, "kids": []}
    if warnings is not None:
        payload["warnings"] = warnings
    return OpenDataLoaderArtifact(
        raw_payload=payload,
        page_numbers=(),
        page_count=4,
    )


def test_unknown_warning_preserves_exact_message(tmp_path: Path) -> None:
    message = "page 4: strange condition at C:\\tmp\\run-a\\image.png"
    warnings = extract_opendataloader_warnings(
        minimal_artifact(),
        message,
        context(tmp_path),
    )

    assert warnings[0].code == "PARSER_WARNING_UNKNOWN"
    assert warnings[0].raw_message == message
    assert warnings[0].page_number == 4


def test_explicit_warning_taxonomy(tmp_path: Path) -> None:
    warnings = extract_opendataloader_warnings(
        minimal_artifact(
            [
                {
                    "code": "TABLE_EXTRACTION_FAILED",
                    "message": "table failed",
                    "page_number": 2,
                },
                {
                    "code": "LAYOUT_WARNING",
                    "message": "layout differs",
                    "page number": 3,
                },
            ]
        ),
        "[IMAGE_EXTRACTION_FAILED] page=4 image failed",
        context(tmp_path),
    )

    assert {warning.code for warning in warnings} == {
        "PARSER_WARNING_TABLE_EXTRACTION",
        "PARSER_WARNING_LAYOUT",
        "PARSER_WARNING_IMAGE_EXTRACTION",
    }
    assert {warning.page_number for warning in warnings} == {2, 3, 4}


def test_same_warning_is_deduplicated_by_stable_identity(tmp_path: Path) -> None:
    warnings = extract_opendataloader_warnings(
        minimal_artifact(["page 1: warning", "page 1: warning"]),
        None,
        context(tmp_path),
    )
    assert len(warnings) == 1
    assert warnings[0].warning_id.startswith("PWRN-")
