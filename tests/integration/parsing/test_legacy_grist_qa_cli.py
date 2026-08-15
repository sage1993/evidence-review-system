from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

from evidence_review.canonical_json import dump_bytes
from evidence_review.parsing.legacy_grist_qa import (
    REQUIRED_SAMPLE_KINDS,
    REQUIRED_VIEW_IDS,
)


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _write(root: Path, relative: str, content: bytes) -> str:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return _sha256(content)


def _artifact(root: Path, status: str) -> Path:
    grist_hash = _write(root, "legacy/workspace.grist", b"grist")
    manifest_hash = _write(
        root,
        "04_visuals/manifests/visual_manifest.csv",
        b"legacy,csv\n",
    )
    inspection_bytes = dump_bytes(
        {
            "format": "evidence-review/legacy-visual-inspection",
            "version": 1,
            "status": "LEGACY_NON_CANONICAL",
            "source_sha256": manifest_hash,
            "conversion_supported": False,
        }
    )
    inspection_hash = _write(
        root,
        "runs/legacy-visual-inspection.json",
        inspection_bytes,
    )
    screenshot_hash = _write(root, "qa/screen.png", b"screen")
    samples: list[dict[str, object]] = []
    for index, content_kind in enumerate(REQUIRED_SAMPLE_KINDS, start=1):
        relative = f"04_visuals/assets/{index}.png"
        asset_hash = _write(root, relative, f"asset-{index}".encode())
        samples.append(
            {
                "sample_id": f"S-{index}",
                "content_kind": content_kind,
                "row_id": f"ROW-{index}",
                "asset_path": relative,
                "asset_sha256": asset_hash,
                "result": "PASS",
                "evidence_ids": ["E-1"],
                "notes": "checked",
            }
        )

    views = [
        {
            "view_id": view_id,
            "status": "PASS",
            "evidence_ids": ["E-1"],
            "notes": "checked",
        }
        for view_id in REQUIRED_VIEW_IDS
    ]
    findings: list[dict[str, object]] = []
    if status == "INCOMPLETE":
        views[0]["status"] = "NOT_RUN"
    elif status == "FAIL":
        views[0]["status"] = "FAIL"
        findings.append(
            {
                "finding_id": "F-1",
                "view_id": views[0]["view_id"],
                "status": "OPEN",
                "row_id": "ROW-FAIL",
                "file_path": None,
                "description": "broken preview",
                "evidence_ids": ["E-1"],
            }
        )

    payload = {
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
                "path": "qa/screen.png",
                "sha256": screenshot_hash,
            }
        ],
        "views": views,
        "samples": samples,
        "findings": findings,
    }
    artifact_path = root / "qa/grist-desktop-qa.json"
    artifact_path.write_bytes(dump_bytes(payload))
    return artifact_path


def _run_cli(*arguments: str) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(Path(__file__).parents[3] / "src")
    return subprocess.run(
        [sys.executable, "-m", "evidence_review", *arguments],
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )


def test_grist_qa_cli_pass_is_accepted_and_deterministic(tmp_path: Path) -> None:
    artifact = _artifact(tmp_path, "PASS")
    arguments = (
        "legacy",
        "validate-grist-qa",
        "--artifact",
        str(artifact),
        "--root",
        str(tmp_path),
    )

    first = _run_cli(*arguments)
    second = _run_cli(*arguments)

    assert first.returncode == 0, first.stderr
    assert first.stdout == second.stdout
    payload = json.loads(first.stdout)
    assert payload["format"] == "evidence-review/grist-desktop-qa-status"
    assert payload["status"] == "PASS"
    assert payload["accepted"] is True
    assert payload["reviewer_id"] == "reviewer@example.com"


def test_grist_qa_cli_fail_and_incomplete_return_one(tmp_path: Path) -> None:
    for status in ("FAIL", "INCOMPLETE"):
        root = tmp_path / status.lower()
        root.mkdir()
        artifact = _artifact(root, status)
        result = _run_cli(
            "legacy",
            "validate-grist-qa",
            "--artifact",
            str(artifact),
            "--root",
            str(root),
        )

        assert result.returncode == 1, result.stderr
        payload = json.loads(result.stdout)
        assert payload["status"] == status
        assert payload["accepted"] is False


def test_grist_qa_cli_tampering_returns_two(tmp_path: Path) -> None:
    artifact = _artifact(tmp_path, "PASS")
    (tmp_path / "qa/screen.png").write_bytes(b"tampered")

    result = _run_cli(
        "legacy",
        "validate-grist-qa",
        "--artifact",
        str(artifact),
        "--root",
        str(tmp_path),
    )

    assert result.returncode == 2
    assert "GRIST_QA_HASH_MISMATCH" in result.stderr
    assert result.stdout == ""


def test_grist_qa_cli_help_is_available() -> None:
    result = _run_cli("legacy", "validate-grist-qa", "--help")

    assert result.returncode == 0
    assert "--artifact" in result.stdout
    assert "--root" in result.stdout
