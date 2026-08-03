from __future__ import annotations

import json

import pytest

from ansim_review.parser_reproducibility.contract import (
    decode_parser_run_metadata,
    decode_reproducibility_config,
)

_SOURCE_SHA = "0" * 64
_DOCUMENT_ID = "DOC-0123456789ABCDEF0123"
_REVISION_ID = f"{_DOCUMENT_ID}-{_SOURCE_SHA[:12]}"


def config_payload() -> dict[str, object]:
    return {
        "format": "evidence-review/parser-reproducibility-config",
        "version": 1,
        "parser_kind": "opendataloader",
        "adapter_version": 1,
        "json_artifact_names": ["document.json"],
        "markdown_artifact_names": ["document.md"],
        "warning_sources": ["document.json", "parser.log"],
        "normalization_profile": "opendataloader-v1",
        "allowed_nondeterministic_fields": [
            "$.metadata.parsed_at",
            "$.metadata.output_directory",
        ],
    }


def run_payload() -> dict[str, object]:
    return {
        "format": "evidence-review/opendataloader-parser-run",
        "version": 1,
        "source_relative_path": "inputs/original/reference.pdf",
        "source_sha256": _SOURCE_SHA,
        "source_size": 12345,
        "source_page_count": 10,
        "document_id": _DOCUMENT_ID,
        "revision_id": _REVISION_ID,
        "parser_kind": "opendataloader",
        "parser_version": "1.2.3",
        "adapter_version": 1,
        "parser_configuration": {"markdown_with_html": True},
        "platform_family": "windows",
    }


def encode(value: dict[str, object]) -> bytes:
    return json.dumps(value, separators=(",", ":")).encode("utf-8")


def test_decodes_exact_config_and_run_authority() -> None:
    config = decode_reproducibility_config(encode(config_payload()))
    run = decode_parser_run_metadata(encode(run_payload()))

    assert config.parser_kind == "opendataloader"
    assert config.json_artifact_names == ("document.json",)
    assert config.markdown_artifact_names == ("document.md",)
    assert config.warning_sources == ("document.json", "parser.log")
    assert config.allowed_nondeterministic_fields == (
        "$.metadata.parsed_at",
        "$.metadata.output_directory",
    )
    assert run.source_relative_path == "inputs/original/reference.pdf"
    assert run.source_sha256 == _SOURCE_SHA
    assert run.source_page_count == 10
    assert run.parser_version == "1.2.3"
    assert run.parser_configuration == {"markdown_with_html": True}


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("parser_kind", "other", "unsupported parser kind"),
        (
            "normalization_profile",
            "other-v1",
            "unsupported normalization profile",
        ),
        ("json_artifact_names", ["a\\b.json"], "backslash"),
        ("json_artifact_names", ["other.json"], "unsupported JSON"),
        ("markdown_artifact_names", ["other.md"], "unsupported Markdown"),
        ("warning_sources", ["../parser.log"], "unsafe path"),
        ("warning_sources", ["document.json"], "unsupported warning sources"),
        (
            "allowed_nondeterministic_fields",
            ["$..parsed_at"],
            "recursive",
        ),
        (
            "allowed_nondeterministic_fields",
            ["$.pages[*].id"],
            "wildcard",
        ),
        ("adapter_version", 2, "unsupported adapter version"),
    ],
)
def test_config_rejects_invalid_values(
    field: str,
    value: object,
    message: str,
) -> None:
    payload = config_payload()
    payload[field] = value
    with pytest.raises(ValueError, match=message):
        decode_reproducibility_config(encode(payload))


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("source_relative_path", "C:/absolute.pdf", "drive"),
        ("source_relative_path", "../reference.pdf", "unsafe path"),
        ("source_sha256", "A" * 64, "lowercase"),
        ("source_size", True, "positive integer"),
        ("source_page_count", 0, "positive integer"),
        ("revision_id", "DOC-WRONG-000000000000", "does not match"),
        ("parser_version", "latest", "semantic version"),
        ("adapter_version", 2, "unsupported adapter version"),
        ("platform_family", "unknown", "unsupported platform_family"),
    ],
)
def test_run_authority_rejects_invalid_values(
    field: str,
    value: object,
    message: str,
) -> None:
    payload = run_payload()
    payload[field] = value
    with pytest.raises(ValueError, match=message):
        decode_parser_run_metadata(encode(payload))


def test_rejects_duplicate_json_keys() -> None:
    duplicate = (
        b'{"format":"evidence-review/parser-reproducibility-config",'
        b'"format":"evidence-review/parser-reproducibility-config"}'
    )
    with pytest.raises(ValueError, match="duplicate JSON key"):
        decode_reproducibility_config(duplicate)


def test_rejects_unknown_and_missing_fields() -> None:
    config = config_payload()
    config["extra"] = True
    with pytest.raises(ValueError, match="unknown field"):
        decode_reproducibility_config(encode(config))

    run = run_payload()
    del run["parser_version"]
    with pytest.raises(ValueError, match="missing field"):
        decode_parser_run_metadata(encode(run))


def test_rejects_duplicate_list_entries_and_unapproved_fields() -> None:
    config = config_payload()
    config["warning_sources"] = ["parser.log", "parser.log"]
    with pytest.raises(ValueError, match="duplicate entry"):
        decode_reproducibility_config(encode(config))

    config = config_payload()
    config["allowed_nondeterministic_fields"] = ["$.metadata.title"]
    with pytest.raises(ValueError, match="unsupported normalization field"):
        decode_reproducibility_config(encode(config))


def test_parser_configuration_must_be_an_object() -> None:
    run = run_payload()
    run["parser_configuration"] = []
    with pytest.raises(ValueError, match="must be an object"):
        decode_parser_run_metadata(encode(run))
