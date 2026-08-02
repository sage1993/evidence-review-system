from __future__ import annotations

import hashlib
import json
import warnings
import zipfile
from pathlib import Path

import pytest

from ansim_review.contracts.formats import RELEASE_OUTPUT_VALIDATION_FORMAT
from ansim_review.release.output_verifier import validate_release_output

_CANDIDATE_FILES = {
    "approved-rules.zip",
    "chatgpt-web-runtime.zip",
    "codex-workspace.zip",
    "evidence.sqlite",
    "final-review-packet.json",
}


def _manifest_entry(path: str, data: bytes) -> dict[str, object]:
    return {
        "path": path,
        "sha256": hashlib.sha256(data).hexdigest(),
        "size": len(data),
    }


def _manifest(format_name: str, files: list[dict[str, object]]) -> bytes:
    return json.dumps(
        {"format": format_name, "version": 1, "files": files},
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _write_zip(path: Path, entries: list[tuple[str, bytes]]) -> None:
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", UserWarning)
        with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for name, data in entries:
                archive.writestr(name, data)


def _valid_archive(
    path: Path,
    *,
    manifest_name: str,
    format_name: str,
    member_name: str,
) -> None:
    data = f"payload:{member_name}".encode()
    _write_zip(
        path,
        [
            (member_name, data),
            (manifest_name, _manifest(format_name, [_manifest_entry(member_name, data)])),
        ],
    )


def _valid_output(tmp_path: Path) -> Path:
    output = tmp_path / "release"
    output.mkdir()
    (output / "evidence.sqlite").write_bytes(b"sqlite")
    (output / "final-review-packet.json").write_text("{}", encoding="utf-8")
    _write_zip(output / "approved-rules.zip", [("R1.json", b"{}")])
    _valid_archive(
        output / "codex-workspace.zip",
        manifest_name="bundle-manifest.json",
        format_name="evidence-review/codex-workspace",
        member_name="src/ansim_review/__init__.py",
    )
    _valid_archive(
        output / "chatgpt-web-runtime.zip",
        manifest_name="runtime-manifest.json",
        format_name="evidence-review/chatgpt-web-runtime",
        member_name="ansim_review/__init__.py",
    )
    return output


def _replace_codex(output: Path, entries: list[tuple[str, bytes]]) -> None:
    (output / "codex-workspace.zip").unlink()
    _write_zip(output / "codex-workspace.zip", entries)


def test_release_output_verifier_accepts_exact_candidate_and_both_manifests(
    tmp_path: Path,
) -> None:
    output = _valid_output(tmp_path)

    report = validate_release_output(output)

    assert report["format"] == RELEASE_OUTPUT_VALIDATION_FORMAT
    assert report["version"] == 1
    assert report["status"] == "PASS"
    assert report["errors"] == []
    output_report = report["output_directory"]
    assert isinstance(output_report, dict)
    assert output_report["status"] == "PASS"
    assert set(output_report["actual_files"]) == _CANDIDATE_FILES
    archives = report["archives"]
    assert isinstance(archives, list)
    by_name = {item["archive"]: item for item in archives}
    assert set(by_name) == {"codex-workspace.zip", "chatgpt-web-runtime.zip"}
    assert by_name["codex-workspace.zip"]["status"] == "PASS"
    assert by_name["chatgpt-web-runtime.zip"]["status"] == "PASS"
    assert by_name["codex-workspace.zip"]["verified_file_count"] == 1


def test_release_output_verifier_rejects_missing_and_unexpected_output_files(
    tmp_path: Path,
) -> None:
    output = _valid_output(tmp_path)
    (output / "evidence.sqlite").unlink()
    (output / "unexpected.bin").write_bytes(b"unexpected")

    report = validate_release_output(output)

    assert report["status"] == "FAIL"
    assert "OUTPUT_FILE_MISSING:evidence.sqlite" in report["errors"]
    assert "OUTPUT_FILE_UNEXPECTED:unexpected.bin" in report["errors"]


@pytest.mark.parametrize(
    "unsafe_path",
    [
        "/absolute.txt",
        "../escape.txt",
        "folder/../escape.txt",
        "folder/./file.txt",
        "folder//file.txt",
        "folder\\file.txt",
        "C:/drive.txt",
        "./file.txt",
    ],
)
def test_zip_member_paths_must_be_canonical_posix(
    tmp_path: Path,
    unsafe_path: str,
) -> None:
    output = _valid_output(tmp_path)
    _replace_codex(
        output,
        [
            (unsafe_path, b"unsafe"),
            (
                "bundle-manifest.json",
                _manifest("evidence-review/codex-workspace", []),
            ),
        ],
    )

    report = validate_release_output(output)

    assert any(
        error.startswith("ZIP_MEMBER_PATH_INVALID:codex-workspace.zip:")
        for error in report["errors"]
    )


def test_zip_duplicate_and_case_colliding_members_are_rejected(tmp_path: Path) -> None:
    output = _valid_output(tmp_path)
    data = b"same"
    _replace_codex(
        output,
        [
            ("README.txt", data),
            ("README.txt", data),
            ("readme.txt", data),
            (
                "bundle-manifest.json",
                _manifest(
                    "evidence-review/codex-workspace",
                    [_manifest_entry("README.txt", data), _manifest_entry("readme.txt", data)],
                ),
            ),
        ],
    )

    report = validate_release_output(output)

    assert "ZIP_MEMBER_DUPLICATE:codex-workspace.zip:README.txt" in report["errors"]
    assert any(
        error.startswith("ZIP_MEMBER_CASE_COLLISION:codex-workspace.zip:")
        for error in report["errors"]
    )


@pytest.mark.parametrize(
    ("entries", "expected_error"),
    [
        (
            [("payload.txt", b"data")],
            "MANIFEST_MISSING:codex-workspace.zip:bundle-manifest.json",
        ),
        (
            [
                ("bundle-manifest.json", b"{}"),
                ("bundle-manifest.json", b"{}"),
            ],
            "MANIFEST_DUPLICATE:codex-workspace.zip:bundle-manifest.json",
        ),
        (
            [("bundle-manifest.json", b"not-json")],
            "MANIFEST_JSON_INVALID:codex-workspace.zip:bundle-manifest.json",
        ),
        (
            [
                (
                    "bundle-manifest.json",
                    _manifest("wrong/format", []),
                )
            ],
            "MANIFEST_FORMAT_INVALID:codex-workspace.zip:bundle-manifest.json",
        ),
        (
            [
                (
                    "bundle-manifest.json",
                    b'{"files":[],"format":"evidence-review/codex-workspace","version":2}',
                )
            ],
            "MANIFEST_VERSION_INVALID:codex-workspace.zip:bundle-manifest.json",
        ),
        (
            [
                (
                    "bundle-manifest.json",
                    b'{"files":{},"format":"evidence-review/codex-workspace","version":1}',
                )
            ],
            "MANIFEST_FILES_INVALID:codex-workspace.zip:bundle-manifest.json",
        ),
    ],
)
def test_manifest_container_contract_is_strict(
    tmp_path: Path,
    entries: list[tuple[str, bytes]],
    expected_error: str,
) -> None:
    output = _valid_output(tmp_path)
    _replace_codex(output, entries)

    report = validate_release_output(output)

    assert expected_error in report["errors"]


def test_manifest_entries_reject_invalid_paths_duplicates_and_case_collisions(
    tmp_path: Path,
) -> None:
    output = _valid_output(tmp_path)
    data = b"payload"
    manifest = _manifest(
        "evidence-review/codex-workspace",
        [
            _manifest_entry("../escape.txt", data),
            _manifest_entry("A.txt", data),
            _manifest_entry("A.txt", data),
            _manifest_entry("a.txt", data),
        ],
    )
    _replace_codex(
        output,
        [
            ("A.txt", data),
            ("a.txt", data),
            ("bundle-manifest.json", manifest),
        ],
    )

    report = validate_release_output(output)

    assert "MANIFEST_ENTRY_PATH_INVALID:codex-workspace.zip:../escape.txt" in report["errors"]
    assert "MANIFEST_ENTRY_DUPLICATE:codex-workspace.zip:A.txt" in report["errors"]
    assert any(
        error.startswith("MANIFEST_ENTRY_CASE_COLLISION:codex-workspace.zip:")
        for error in report["errors"]
    )


def test_manifest_member_set_size_and_hash_must_match_actual_bytes(
    tmp_path: Path,
) -> None:
    output = _valid_output(tmp_path)
    actual = b"actual"
    entries = [
        {
            "path": "missing.txt",
            "sha256": hashlib.sha256(b"missing").hexdigest(),
            "size": len(b"missing"),
        },
        {
            "path": "size.txt",
            "sha256": hashlib.sha256(actual).hexdigest(),
            "size": len(actual) + 1,
        },
        {
            "path": "hash.txt",
            "sha256": "0" * 64,
            "size": len(actual),
        },
    ]
    _replace_codex(
        output,
        [
            ("extra.txt", actual),
            ("size.txt", actual),
            ("hash.txt", actual),
            (
                "bundle-manifest.json",
                _manifest("evidence-review/codex-workspace", entries),
            ),
        ],
    )

    report = validate_release_output(output)

    assert "MANIFEST_FILE_MISSING:codex-workspace.zip:missing.txt" in report["errors"]
    assert "ARCHIVE_FILE_UNDECLARED:codex-workspace.zip:extra.txt" in report["errors"]
    assert "MANIFEST_SIZE_MISMATCH:codex-workspace.zip:size.txt" in report["errors"]
    assert "MANIFEST_HASH_MISMATCH:codex-workspace.zip:hash.txt" in report["errors"]
    assert report["errors"] == sorted(report["errors"])
