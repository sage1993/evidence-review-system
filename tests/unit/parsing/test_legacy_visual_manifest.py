from __future__ import annotations

import csv
import json
from pathlib import Path

from ansim_review.canonical_json import dump_bytes
from ansim_review.parsing.legacy_visual_manifest import (
    LEGACY_VISUAL_HEADER,
    inspect_legacy_visual_manifest,
)
from ansim_review.parsing.source_manifest import sha256_file

GOLDEN = Path("tests/golden/legacy_visual/inspection.json")


def _write_csv(path: Path, rows: list[list[str]], *, bom: bool = True) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    encoding = "utf-8-sig" if bom else "utf-8"
    with path.open("w", encoding=encoding, newline="") as stream:
        writer = csv.writer(stream, lineterminator="\n")
        writer.writerow(LEGACY_VISUAL_HEADER)
        writer.writerows(rows)


def _row(
    *,
    visual_id: str = "VIS-1",
    document_id: str = "1",
    page: str = "2",
    source_path: str = "assets/image.png",
    crop_path: str = "assets/image.png",
    sha256: str = "a" * 64,
) -> list[str]:
    return [
        visual_id,
        document_id,
        "4",
        "LAW1-1_3_1",
        page,
        "PDF 고유 이미지",
        "xref:233",
        "0",
        source_path,
        crop_path,
        "98.707",
        "474.92",
        "312.312",
        "577.168",
        "1484",
        "711",
        sha256,
    ]


def test_valid_bom_csv_is_inspected_without_canonical_conversion(tmp_path: Path) -> None:
    root = tmp_path / "workspace"
    asset = root / "assets/image.png"
    asset.parent.mkdir(parents=True)
    asset.write_bytes(b"image")
    manifest = root / "visual_manifest.csv"
    _write_csv(manifest, [_row(sha256=sha256_file(asset))])

    report = inspect_legacy_visual_manifest(manifest, root=root)

    assert report["format"] == "evidence-review/legacy-visual-inspection"
    assert report["version"] == 1
    assert report["status"] == "LEGACY_NON_CANONICAL"
    assert report["source_path"] == "visual_manifest.csv"
    assert report["row_count"] == 1
    assert report["identity_gaps"] == ["page_id", "revision_id"]
    assert report["document_ids"] == ["1"]
    assert report["issues"] == []
    assert report["issue_counts"] == {}
    assert report["conversion_supported"] is False
    assert report["conversion_requirements"] == [
        "ASSET_SHA256_MATCH",
        "DB_RESOLVED_PAGE_ID",
        "EXPLICIT_ASSET_PATH_POLICY",
        "EXPLICIT_DOCUMENT_ALIAS",
        "EXPLICIT_REVISION_ID",
        "EXPLICIT_VISUAL_KIND_MAP",
    ]
    assert "records" not in report


def test_inspection_is_byte_deterministic_and_matches_golden(tmp_path: Path) -> None:
    root = tmp_path / "workspace"
    asset = root / "assets/image.png"
    asset.parent.mkdir(parents=True)
    asset.write_bytes(b"image")
    manifest = root / "visual_manifest.csv"
    _write_csv(manifest, [_row(sha256=sha256_file(asset))])

    first = inspect_legacy_visual_manifest(manifest, root=root)
    second = inspect_legacy_visual_manifest(manifest, root=root)

    assert dump_bytes(first) == dump_bytes(second)
    assert first == json.loads(GOLDEN.read_text(encoding="utf-8"))


def test_row_issues_are_reported_without_identity_inference(tmp_path: Path) -> None:
    manifest = tmp_path / "visual_manifest.csv"
    _write_csv(
        manifest,
        [
            _row(
                visual_id="VIS-1",
                document_id="",
                page="0",
                source_path="../source.png",
                crop_path="folder\\crop.png",
                sha256="INVALID",
            ),
            _row(visual_id="VIS-1"),
        ],
    )

    report = inspect_legacy_visual_manifest(manifest)

    assert report["status"] == "LEGACY_NON_CANONICAL"
    assert report["document_ids"] == ["1"]
    assert report["issue_counts"] == {
        "CROP_PATH_INVALID": 1,
        "DOCUMENT_ID_MISSING": 1,
        "DUPLICATE_VISUAL_ID": 1,
        "PAGE_INVALID": 1,
        "SHA256_INVALID": 1,
        "SOURCE_PATH_INVALID": 1,
    }
    assert [issue["code"] for issue in report["issues"]] == [
        "CROP_PATH_INVALID",
        "DOCUMENT_ID_MISSING",
        "PAGE_INVALID",
        "SHA256_INVALID",
        "SOURCE_PATH_INVALID",
        "DUPLICATE_VISUAL_ID",
    ]
    assert all("document_id" not in issue for issue in report["issues"])
    assert "records" not in report


def test_asset_missing_and_hash_mismatch_are_reported(tmp_path: Path) -> None:
    root = tmp_path / "workspace"
    existing = root / "assets/existing.png"
    existing.parent.mkdir(parents=True)
    existing.write_bytes(b"actual")
    manifest = root / "visual_manifest.csv"
    _write_csv(
        manifest,
        [
            _row(visual_id="VIS-MISSING", crop_path="assets/missing.png"),
            _row(visual_id="VIS-HASH", crop_path="assets/existing.png"),
        ],
    )

    report = inspect_legacy_visual_manifest(manifest, root=root)

    assert report["issue_counts"] == {
        "ASSET_HASH_MISMATCH": 1,
        "ASSET_MISSING": 1,
    }
    assert [issue["code"] for issue in report["issues"]] == [
        "ASSET_MISSING",
        "ASSET_HASH_MISMATCH",
    ]


def test_header_must_match_exact_legacy_schema(tmp_path: Path) -> None:
    manifest = tmp_path / "visual_manifest.csv"
    manifest.write_text("visual_id,document_id\nVIS-1,1\n", encoding="utf-8")

    try:
        inspect_legacy_visual_manifest(manifest)
    except ValueError as error:
        assert str(error) == "LEGACY_VISUAL_HEADER_INVALID"
    else:
        raise AssertionError("invalid header must be rejected")
