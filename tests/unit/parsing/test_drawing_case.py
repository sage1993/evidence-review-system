from pathlib import Path

import pytest

from ansim_review.parsing.drawing_case import (
    CaseManifest,
    case_artifact_path,
    case_manifest_document,
    case_root,
    decode_case_manifest,
    validate_artifact_id,
    write_canonical_create_only,
)


def test_artifact_ids_accept_ascii_safe_tokens() -> None:
    assert validate_artifact_id("CASE-001_A", "case_id") == "CASE-001_A"


@pytest.mark.parametrize("value", ["", "../CASE", "C:/CASE", "한글", "A" * 129])
def test_artifact_ids_reject_unsafe_tokens(value: str) -> None:
    with pytest.raises(ValueError):
        validate_artifact_id(value, "case_id")


def test_case_artifact_path_rejects_escape(tmp_path: Path) -> None:
    root = case_root(tmp_path, "CASE-001")
    with pytest.raises(ValueError, match="safe relative path"):
        case_artifact_path(root, "../outside.json")


def test_write_canonical_create_only_refuses_overwrite(tmp_path: Path) -> None:
    path = tmp_path / "artifact.json"
    digest = write_canonical_create_only(path, {"b": 2, "a": 1})
    assert path.read_text(encoding="utf-8") == '{"a":1,"b":2}'
    assert len(digest) == 64
    with pytest.raises(FileExistsError):
        write_canonical_create_only(path, {"a": 1})


def test_case_manifest_round_trips_explicit_empty_collections() -> None:
    manifest = CaseManifest(
        format="ansim/case-manifest",
        version=1,
        case_id="CASE-001",
        policy_id="DRAWING-INTAKE-1",
        sources=(),
        quality_assessments=(),
        candidates=(),
        confirmations=(),
        confirmed_inputs_path=None,
        confirmed_inputs_sha256=None,
    )
    document = case_manifest_document(manifest)
    assert decode_case_manifest(document) == manifest
    assert document["sources"] == []
