from __future__ import annotations

import csv
import json
import os
import subprocess
import sys
from pathlib import Path

from ansim_review.parsing.legacy_visual_manifest import LEGACY_VISUAL_HEADER


def run_cli(*arguments: str) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(Path(__file__).parents[3] / "src")
    return subprocess.run(
        [sys.executable, "-m", "ansim_review", *arguments],
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )


def _manifest(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.writer(stream, lineterminator="\n")
        writer.writerow(LEGACY_VISUAL_HEADER)
        writer.writerow(
            [
                "VIS-1",
                "1",
                "4",
                "LAW1-1_3_1",
                "2",
                "PDF 고유 이미지",
                "xref:233",
                "0",
                "assets/image.png",
                "assets/image.png",
                "98.707",
                "474.92",
                "312.312",
                "577.168",
                "1484",
                "711",
                "a" * 64,
            ]
        )


def test_legacy_visual_inspection_cli_writes_create_only_report(
    tmp_path: Path,
) -> None:
    root = tmp_path / "workspace"
    manifest = root / "visual_manifest.csv"
    output = root / "runs/legacy-visual-inspection.json"
    _manifest(manifest)

    result = run_cli(
        "legacy",
        "inspect-visual-manifest",
        "--manifest",
        str(manifest),
        "--root",
        str(root),
        "--output",
        str(output),
    )

    assert result.returncode == 0, result.stderr
    status = json.loads(result.stdout)
    report = json.loads(output.read_text(encoding="utf-8"))
    assert status == {
        "format": "evidence-review/legacy-visual-inspection-status",
        "version": 1,
        "status": "LEGACY_NON_CANONICAL",
        "output": str(output.resolve()),
        "row_count": 1,
        "issue_count": 1,
        "conversion_supported": False,
    }
    assert report["status"] == "LEGACY_NON_CANONICAL"
    assert report["conversion_supported"] is False
    assert report["issue_counts"] == {"ASSET_MISSING": 1}

    second = run_cli(
        "legacy",
        "inspect-visual-manifest",
        "--manifest",
        str(manifest),
        "--root",
        str(root),
        "--output",
        str(output),
    )
    assert second.returncode == 1
    assert "output already exists" in second.stderr


def test_legacy_visual_inspection_cli_without_root_skips_asset_check(
    tmp_path: Path,
) -> None:
    manifest = tmp_path / "visual_manifest.csv"
    output = tmp_path / "inspection.json"
    _manifest(manifest)

    result = run_cli(
        "legacy",
        "inspect-visual-manifest",
        "--manifest",
        str(manifest),
        "--output",
        str(output),
    )

    assert result.returncode == 0, result.stderr
    report = json.loads(output.read_text(encoding="utf-8"))
    assert report["issues"] == []


def test_legacy_visual_inspection_cli_invalid_manifest_returns_two(
    tmp_path: Path,
) -> None:
    manifest = tmp_path / "invalid.csv"
    output = tmp_path / "inspection.json"
    manifest.write_text("visual_id,document_id\nVIS-1,1\n", encoding="utf-8")

    result = run_cli(
        "legacy",
        "inspect-visual-manifest",
        "--manifest",
        str(manifest),
        "--output",
        str(output),
    )

    assert result.returncode == 2
    assert "LEGACY_VISUAL_HEADER_INVALID" in result.stderr
    assert not output.exists()


def test_legacy_visual_inspection_cli_help_is_available() -> None:
    result = run_cli("legacy", "inspect-visual-manifest", "--help")

    assert result.returncode == 0
    assert "--manifest" in result.stdout
    assert "--root" in result.stdout
    assert "--output" in result.stdout
