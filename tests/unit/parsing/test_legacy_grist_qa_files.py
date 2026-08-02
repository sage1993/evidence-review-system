from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from ansim_review.canonical_json import dump_bytes
from ansim_review.parsing.legacy_grist_qa import (
    REQUIRED_SAMPLE_KINDS,
    REQUIRED_VIEW_IDS,
    decode_grist_qa,
    load_and_validate_grist_qa,
    validate_grist_qa_files,
)


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _write(root: Path, relative: str, content: bytes) -> str:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return _sha256(content)


def _workspace_payload(root: Path) -> dict[str, object]:
    grist_hash = _write(root, "legacy/workspace.grist", b"grist-sqlite-bytes")
    manifest_bytes = b"visual_id,document_id,page\nV1,D1,1\n"
    manifest_hash = _write(
        root,
        "04_visuals/manifests/visual_manifest.csv",
        manifest_bytes,
    )
    inspection = {
        "format": "evidence-review/legacy-visual-inspection",
        "version": 1,
        "status": "LEGACY_NON_CANONICAL",
        "source_sha256": manifest_hash,
        "conversion_supported": False,
    }
    inspection_bytes = dump_bytes(inspection)
    inspection_hash = _write(
        root,
        "runs/legacy-visual-inspection.json",
        inspection_bytes,
    )
    screenshot_hash = _write(
        root,
        "qa/screenshots/grist-overview.png",
        b"screenshot-bytes",
    )

    samples: list[dict[str, object]] = []
    for index, content_kind in enumerate(REQUIRED_SAMPLE_KINDS, start=1):
        asset_path = f"04_visuals/assets/{index}.png"
        asset_hash = _write(root, asset_path, f"asset-{index}".encode())
        samples.append(
            {
                "sample_id": f"S-{index}",
                "content_kind": content_kind,
                "row_id": f"ROW-{index}",
                "asset_path": asset_path,
                "asset_sha256": asset_hash,
                "result": "PASS",
                "evidence_ids": ["E-1"],
                "notes": f"checked {content_kind}",
            }
        )

    return {
        "format": "evidence-review/grist-desktop-qa",
        "version": 1,
        "scope": "LEGACY_UI_QA",
        "identity_claim": "LEGACY_NON_CANONICAL",
        "review": {
            "reviewer_id": "reviewer@example.com",
            "reviewed_at": "2026-08-02T15:30:00+09:00",
        },
        "environment": {
            "grist_desktop_version": "0.3.1",
            "os": "Windows 11 24H2",
        },
        "sources": {
            "grist_file": {
                "path": "legacy/workspace.grist",
                "sha256": grist_hash,
            },
            "visual_manifest": {
                "path": "04_visuals/manifests/visual_manifest.csv",
                "sha256": manifest_hash,
            },
            "inspection_report": {
                "path": "runs/legacy-visual-inspection.json",
                "sha256": inspection_hash,
            },
        },
        "evidence_files": [
            {
                "evidence_id": "E-1",
                "path": "qa/screenshots/grist-overview.png",
                "sha256": screenshot_hash,
            }
        ],
        "views": [
            {
                "view_id": view_id,
                "status": "PASS",
                "evidence_ids": ["E-1"],
                "notes": f"checked {view_id}",
            }
            for view_id in REQUIRED_VIEW_IDS
        ],
        "samples": samples,
        "findings": [],
    }


def _binding(payload: dict[str, object], name: str) -> dict[str, object]:
    sources = payload["sources"]
    assert isinstance(sources, dict)
    binding = sources[name]
    assert isinstance(binding, dict)
    return binding


def test_all_bound_files_and_inspection_semantics_validate(tmp_path: Path) -> None:
    payload = _workspace_payload(tmp_path)
    artifact = decode_grist_qa(payload)

    validate_grist_qa_files(artifact, tmp_path)

    artifact_path = tmp_path / "qa/grist-desktop-qa.json"
    artifact_path.parent.mkdir(parents=True, exist_ok=True)
    artifact_bytes = dump_bytes(payload)
    artifact_path.write_bytes(artifact_bytes)
    loaded, artifact_hash = load_and_validate_grist_qa(artifact_path, tmp_path)
    assert loaded == artifact
    assert artifact_hash == _sha256(artifact_bytes)


@pytest.mark.parametrize(
    "unsafe_path",
    [
        "../workspace.grist",
        "/workspace.grist",
        "C:/workspace.grist",
        "legacy\\workspace.grist",
        "legacy/./workspace.grist",
        "legacy//workspace.grist",
        "legacy/workspace.grist/",
    ],
)
def test_workspace_paths_must_be_safe_posix(
    tmp_path: Path,
    unsafe_path: str,
) -> None:
    payload = _workspace_payload(tmp_path)
    _binding(payload, "grist_file")["path"] = unsafe_path
    artifact = decode_grist_qa(payload)

    with pytest.raises(ValueError, match="UNSAFE_GRIST_QA_PATH"):
        validate_grist_qa_files(artifact, tmp_path)


def test_grist_source_requires_grist_suffix(tmp_path: Path) -> None:
    payload = _workspace_payload(tmp_path)
    original = tmp_path / "legacy/workspace.grist"
    replacement = tmp_path / "legacy/workspace.sqlite"
    replacement.write_bytes(original.read_bytes())
    binding = _binding(payload, "grist_file")
    binding["path"] = "legacy/workspace.sqlite"
    artifact = decode_grist_qa(payload)

    with pytest.raises(ValueError, match="GRIST_FILE_SUFFIX_INVALID"):
        validate_grist_qa_files(artifact, tmp_path)


def test_missing_file_and_hash_mismatch_are_rejected(tmp_path: Path) -> None:
    payload = _workspace_payload(tmp_path)
    screenshot = tmp_path / "qa/screenshots/grist-overview.png"
    screenshot.unlink()

    with pytest.raises(ValueError, match="GRIST_QA_FILE_MISSING"):
        validate_grist_qa_files(decode_grist_qa(payload), tmp_path)

    payload = _workspace_payload(tmp_path)
    screenshot.write_bytes(b"tampered")
    with pytest.raises(ValueError, match="GRIST_QA_HASH_MISMATCH"):
        validate_grist_qa_files(decode_grist_qa(payload), tmp_path)


@pytest.mark.parametrize(
    ("field", "value", "error"),
    [
        ("format", "other/format", "LEGACY_INSPECTION_FORMAT_INVALID"),
        ("version", 2, "LEGACY_INSPECTION_VERSION_INVALID"),
        ("status", "CANONICAL", "LEGACY_INSPECTION_STATUS_INVALID"),
        ("conversion_supported", True, "LEGACY_CONVERSION_CLAIM_INVALID"),
        ("source_sha256", "f" * 64, "LEGACY_INSPECTION_SOURCE_MISMATCH"),
    ],
)
def test_inspection_report_must_preserve_issue37_boundary(
    tmp_path: Path,
    field: str,
    value: object,
    error: str,
) -> None:
    payload = _workspace_payload(tmp_path)
    inspection_path = tmp_path / "runs/legacy-visual-inspection.json"
    inspection = json.loads(inspection_path.read_text(encoding="utf-8"))
    inspection[field] = value
    inspection_bytes = dump_bytes(inspection)
    inspection_path.write_bytes(inspection_bytes)
    _binding(payload, "inspection_report")["sha256"] = _sha256(inspection_bytes)

    with pytest.raises(ValueError, match=error):
        validate_grist_qa_files(decode_grist_qa(payload), tmp_path)


def test_finding_path_is_checked_but_missing_target_is_allowed(tmp_path: Path) -> None:
    payload = _workspace_payload(tmp_path)
    payload["findings"] = [
        {
            "finding_id": "F-1",
            "view_id": "MISSING_BROKEN_LINK_SCAN",
            "status": "RESOLVED",
            "row_id": "ROW-404",
            "file_path": "04_visuals/assets/missing.png",
            "description": "recorded missing legacy file",
            "evidence_ids": [],
        }
    ]
    validate_grist_qa_files(decode_grist_qa(payload), tmp_path)

    findings = payload["findings"]
    assert isinstance(findings, list)
    finding = findings[0]
    assert isinstance(finding, dict)
    finding["file_path"] = "../outside.png"
    with pytest.raises(ValueError, match="UNSAFE_GRIST_QA_PATH"):
        validate_grist_qa_files(decode_grist_qa(payload), tmp_path)
