from __future__ import annotations

from pathlib import Path

import pytest

from evidence_review.parser_reproducibility.opendataloader import (
    OpenDataLoaderArtifact,
)
from evidence_review.parser_reproducibility.warnings import (
    WarningContext,
    _normalized_message,
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
    log_line = f"WARNING: {message}"
    warnings = extract_opendataloader_warnings(
        minimal_artifact(),
        log_line,
        context(tmp_path),
    )

    assert warnings[0].code == "PARSER_WARNING_UNKNOWN"
    assert warnings[0].raw_message == log_line
    assert warnings[0].page_number == 4


def test_info_progress_line_is_not_collected_as_a_warning(tmp_path: Path) -> None:
    warnings = extract_opendataloader_warnings(
        minimal_artifact(),
        "INFO: Processing page 4",
        context(tmp_path),
    )

    assert warnings == ()


def test_warning_log_line_is_collected_and_preserved(tmp_path: Path) -> None:
    log_line = "WARN: page 4: table extraction failed"

    warnings = extract_opendataloader_warnings(
        minimal_artifact(),
        log_line,
        context(tmp_path),
    )

    assert len(warnings) == 1
    assert warnings[0].raw_message == log_line
    assert warnings[0].page_number == 4


@pytest.mark.parametrize("severity", ["WARN", "WARNING", "ERROR", "SEVERE", "FATAL"])
def test_warning_and_error_severities_are_collected(
    tmp_path: Path,
    severity: str,
) -> None:
    warnings = extract_opendataloader_warnings(
        minimal_artifact(),
        f"{severity}: page 4: parser event",
        context(tmp_path),
    )

    assert len(warnings) == 1


def test_python_timestamp_changes_do_not_change_warning_identity(tmp_path: Path) -> None:
    first_line = "2026-09-20 12:34:56,789 - WARNING - page 4: table extraction failed"
    second_line = "2026-09-20 12:35:06,012 - WARNING - page 4: table extraction failed"

    first = extract_opendataloader_warnings(
        minimal_artifact(),
        first_line,
        context(tmp_path),
    )[0]
    second = extract_opendataloader_warnings(
        minimal_artifact(),
        second_line,
        context(tmp_path),
    )[0]

    assert first.raw_message == first_line
    assert second.raw_message == second_line
    assert first.normalized_message_sha256 == second.normalized_message_sha256
    assert first.warning_id == second.warning_id


def test_changed_warning_message_changes_warning_identity(tmp_path: Path) -> None:
    first = extract_opendataloader_warnings(
        minimal_artifact(),
        "2026-09-20 12:34:56,789 - WARNING - page 4: table extraction failed",
        context(tmp_path),
    )[0]
    second = extract_opendataloader_warnings(
        minimal_artifact(),
        "2026-09-20 12:34:56,789 - WARNING - page 4: image extraction failed",
        context(tmp_path),
    )[0]

    assert first.normalized_message_sha256 != second.normalized_message_sha256
    assert first.warning_id != second.warning_id


def test_explicit_warning_taxonomy_preserves_log_prefix(tmp_path: Path) -> None:
    log_line = "WARN: [IMAGE_EXTRACTION_FAILED] page=4 image failed"
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
        log_line,
        context(tmp_path),
    )

    assert {warning.code for warning in warnings} == {
        "PARSER_WARNING_TABLE_EXTRACTION",
        "PARSER_WARNING_LAYOUT",
        "PARSER_WARNING_IMAGE_EXTRACTION",
    }
    assert {warning.page_number for warning in warnings} == {2, 3, 4}
    image_warning = next(
        warning
        for warning in warnings
        if warning.code == "PARSER_WARNING_IMAGE_EXTRACTION"
    )
    assert image_warning.raw_message == log_line


def test_same_warning_is_deduplicated_by_stable_identity(tmp_path: Path) -> None:
    warnings = extract_opendataloader_warnings(
        minimal_artifact(["page 1: warning", "page 1: warning"]),
        None,
        context(tmp_path),
    )
    assert len(warnings) == 1
    assert warnings[0].warning_id.startswith("PWRN-")


def test_warning_normalization_does_not_match_sibling_prefix(tmp_path: Path) -> None:
    run_root = tmp_path / "run-a"
    sibling = str(tmp_path / "run-a-cache" / "parser.log")
    local = str(run_root / "parser.log")

    assert _normalized_message(sibling, run_root) == sibling
    assert _normalized_message(local, run_root) == "<RUN_ROOT>/parser.log"


def test_korean_java_levels_are_classified_and_timestamp_headers_ignored(
    tmp_path: Path,
) -> None:
    from dataclasses import replace

    warning_context = replace(context(tmp_path), parser_page_count=118)
    first_log = (
        "9\uC6D4 20, 2026 3:06:54 \uC624\uD6C4 org.opendataloader.DocumentProcessor run\n"
        "\uC815\uBCF4: Processing 118 pages with 1 threads\n"
        "\uACBD\uACE0: Detected background on page 59"
    )
    second_log = (
        "9\uC6D4 20, 2026 3:08:12 \uC624\uD6C4 org.opendataloader.DocumentProcessor run\n"
        "\uC815\uBCF4: Processing 118 pages with 1 threads\n"
        "\uACBD\uACE0: Detected background on page 59"
    )

    first = extract_opendataloader_warnings(
        minimal_artifact(), first_log, warning_context
    )
    second = extract_opendataloader_warnings(
        minimal_artifact(), second_log, warning_context
    )
    english = extract_opendataloader_warnings(
        minimal_artifact(),
        "WARNING: Detected background on page 59",
        warning_context,
    )

    assert len(first) == 1
    assert first[0].raw_message == "\uACBD\uACE0: Detected background on page 59"
    assert first[0].page_number == 59
    assert first[0].warning_id == second[0].warning_id == english[0].warning_id


def test_korean_java_severe_level_matches_severe_identity(tmp_path: Path) -> None:
    korean = extract_opendataloader_warnings(
        minimal_artifact(),
        "\uC2EC\uAC01: page 4: parser process failed",
        context(tmp_path),
    )
    english = extract_opendataloader_warnings(
        minimal_artifact(),
        "SEVERE: page 4: parser process failed",
        context(tmp_path),
    )

    assert len(korean) == len(english) == 1
    assert korean[0].raw_message == "\uC2EC\uAC01: page 4: parser process failed"
    assert korean[0].warning_id == english[0].warning_id
