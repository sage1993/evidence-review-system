"""Verify final release candidate files before authorization."""

from __future__ import annotations

import hashlib
import json
import re
import zipfile
from collections import Counter, defaultdict
from pathlib import Path
from typing import Final, cast

from evidence_review.contracts.formats import (
    CODEX_WORKSPACE_FORMAT,
    RELEASE_OUTPUT_VALIDATION_FORMAT,
    WEB_RUNTIME_FORMAT,
)

_EXPECTED_OUTPUT_FILES: Final[frozenset[str]] = frozenset(
    {
        "approved-rules.zip",
        "chatgpt-web-runtime.zip",
        "codex-workspace.zip",
        "evidence.sqlite",
        "final-review-packet.json",
    }
)
_ARCHIVE_POLICIES: Final[tuple[tuple[str, str, str], ...]] = (
    ("codex-workspace.zip", "bundle-manifest.json", CODEX_WORKSPACE_FORMAT),
    (
        "chatgpt-web-runtime.zip",
        "runtime-manifest.json",
        WEB_RUNTIME_FORMAT,
    ),
)
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


def _canonical_member_path(value: str) -> bool:
    if not value or "\\" in value or "\x00" in value:
        return False
    if value.startswith("/") or value.endswith("/"):
        return False
    if len(value) >= 2 and value[1] == ":":
        return False
    parts = value.split("/")
    return all(part not in {"", ".", ".."} for part in parts)


def _collision_errors(
    names: list[str],
    *,
    archive_name: str,
    duplicate_code: str,
    collision_code: str,
) -> list[str]:
    errors: list[str] = []
    counts = Counter(names)
    for name in sorted(name for name, count in counts.items() if count > 1):
        errors.append(f"{duplicate_code}:{archive_name}:{name}")
    by_fold: dict[str, set[str]] = defaultdict(set)
    for name in names:
        by_fold[name.casefold()].add(name)
    for folded in sorted(by_fold):
        variants = sorted(by_fold[folded])
        if len(variants) > 1:
            errors.append(
                f"{collision_code}:{archive_name}:{'|'.join(variants)}"
            )
    return errors


def _output_directory_report(output_directory: Path) -> dict[str, object]:
    errors: list[str] = []
    if not output_directory.is_dir():
        return {
            "status": "FAIL",
            "expected_files": sorted(_EXPECTED_OUTPUT_FILES),
            "actual_files": [],
            "errors": ["OUTPUT_DIRECTORY_MISSING"],
        }

    entries = {entry.name: entry for entry in output_directory.iterdir()}
    actual_names = sorted(entries)
    for name in sorted(_EXPECTED_OUTPUT_FILES):
        entry = entries.get(name)
        if entry is None or not entry.is_file():
            errors.append(f"OUTPUT_FILE_MISSING:{name}")
    for name in sorted(set(entries) - _EXPECTED_OUTPUT_FILES):
        errors.append(f"OUTPUT_FILE_UNEXPECTED:{name}")
    return {
        "status": "PASS" if not errors else "FAIL",
        "expected_files": sorted(_EXPECTED_OUTPUT_FILES),
        "actual_files": actual_names,
        "errors": sorted(errors),
    }


def _manifest_payload(
    archive: zipfile.ZipFile,
    manifest_info: zipfile.ZipInfo,
    *,
    archive_name: str,
    manifest_name: str,
    expected_format: str,
    errors: list[str],
) -> list[object] | None:
    try:
        with archive.open(manifest_info, "r") as stream:
            raw = stream.read()
        payload = json.loads(raw)
    except (OSError, RuntimeError, UnicodeDecodeError, json.JSONDecodeError):
        errors.append(f"MANIFEST_JSON_INVALID:{archive_name}:{manifest_name}")
        return None
    if not isinstance(payload, dict):
        errors.append(f"MANIFEST_JSON_INVALID:{archive_name}:{manifest_name}")
        return None
    if payload.get("format") != expected_format:
        errors.append(f"MANIFEST_FORMAT_INVALID:{archive_name}:{manifest_name}")
    version = payload.get("version")
    if isinstance(version, bool) or version != 1:
        errors.append(f"MANIFEST_VERSION_INVALID:{archive_name}:{manifest_name}")
    files = payload.get("files")
    if not isinstance(files, list):
        errors.append(f"MANIFEST_FILES_INVALID:{archive_name}:{manifest_name}")
        return None
    return files


def _verify_archive(
    archive_path: Path,
    *,
    manifest_name: str,
    expected_format: str,
) -> dict[str, object]:
    archive_name = archive_path.name
    errors: list[str] = []
    verified_file_count = 0
    member_count = 0
    if not archive_path.is_file():
        errors.append(f"ARCHIVE_MISSING:{archive_name}")
        return {
            "archive": archive_name,
            "manifest": manifest_name,
            "status": "FAIL",
            "member_count": 0,
            "verified_file_count": 0,
            "errors": errors,
        }

    try:
        with zipfile.ZipFile(archive_path, "r") as archive:
            infos = archive.infolist()
            member_count = len(infos)
            member_names = [info.orig_filename for info in infos]
            for name in member_names:
                if not _canonical_member_path(name):
                    errors.append(f"ZIP_MEMBER_PATH_INVALID:{archive_name}:{name}")
            errors.extend(
                _collision_errors(
                    member_names,
                    archive_name=archive_name,
                    duplicate_code="ZIP_MEMBER_DUPLICATE",
                    collision_code="ZIP_MEMBER_CASE_COLLISION",
                )
            )

            manifest_infos = [info for info in infos if info.filename == manifest_name]
            if not manifest_infos:
                errors.append(f"MANIFEST_MISSING:{archive_name}:{manifest_name}")
                return _archive_report(
                    archive_name,
                    manifest_name,
                    member_count,
                    verified_file_count,
                    errors,
                )
            if len(manifest_infos) > 1:
                errors.append(f"MANIFEST_DUPLICATE:{archive_name}:{manifest_name}")
                return _archive_report(
                    archive_name,
                    manifest_name,
                    member_count,
                    verified_file_count,
                    errors,
                )

            files = _manifest_payload(
                archive,
                manifest_infos[0],
                archive_name=archive_name,
                manifest_name=manifest_name,
                expected_format=expected_format,
                errors=errors,
            )
            if files is None:
                return _archive_report(
                    archive_name,
                    manifest_name,
                    member_count,
                    verified_file_count,
                    errors,
                )

            declared_names: list[str] = []
            valid_records: dict[str, tuple[int, str]] = {}
            for index, item in enumerate(files):
                if not isinstance(item, dict):
                    errors.append(f"MANIFEST_ENTRY_INVALID:{archive_name}:{index}")
                    continue
                path = item.get("path")
                digest = item.get("sha256")
                size = item.get("size")
                if not isinstance(path, str):
                    errors.append(f"MANIFEST_ENTRY_INVALID:{archive_name}:{index}")
                    continue
                declared_names.append(path)
                path_is_valid = _canonical_member_path(path)
                if not path_is_valid:
                    errors.append(f"MANIFEST_ENTRY_PATH_INVALID:{archive_name}:{path}")
                digest_is_valid = isinstance(digest, str) and bool(
                    _SHA256.fullmatch(digest)
                )
                if not digest_is_valid:
                    errors.append(f"MANIFEST_ENTRY_HASH_INVALID:{archive_name}:{path}")
                size_is_valid = (
                    isinstance(size, int) and not isinstance(size, bool) and size >= 0
                )
                if not size_is_valid:
                    errors.append(f"MANIFEST_ENTRY_SIZE_INVALID:{archive_name}:{path}")
                if (
                    path_is_valid
                    and digest_is_valid
                    and size_is_valid
                    and path not in valid_records
                ):
                    valid_records[path] = (cast(int, size), cast(str, digest))

            errors.extend(
                _collision_errors(
                    declared_names,
                    archive_name=archive_name,
                    duplicate_code="MANIFEST_ENTRY_DUPLICATE",
                    collision_code="MANIFEST_ENTRY_CASE_COLLISION",
                )
            )

            counts = Counter(member_names)
            actual_infos: dict[str, zipfile.ZipInfo] = {
                info.orig_filename: info
                for info in infos
                if info.filename != manifest_name
                and counts[info.filename] == 1
                and _canonical_member_path(info.filename)
            }
            actual_names = set(actual_infos)
            declared = set(valid_records)
            for name in sorted(declared - actual_names):
                errors.append(f"MANIFEST_FILE_MISSING:{archive_name}:{name}")
            for name in sorted(actual_names - declared):
                errors.append(f"ARCHIVE_FILE_UNDECLARED:{archive_name}:{name}")

            for name in sorted(actual_names & declared):
                expected_size, expected_hash = valid_records[name]
                try:
                    with archive.open(actual_infos[name], "r") as stream:
                        data = stream.read()
                except (OSError, RuntimeError, zipfile.BadZipFile, EOFError):
                    errors.append(f"ZIP_MEMBER_READ_FAILED:{archive_name}:{name}")
                    continue
                matched = True
                if len(data) != expected_size:
                    errors.append(f"MANIFEST_SIZE_MISMATCH:{archive_name}:{name}")
                    matched = False
                if hashlib.sha256(data).hexdigest() != expected_hash:
                    errors.append(f"MANIFEST_HASH_MISMATCH:{archive_name}:{name}")
                    matched = False
                if matched:
                    verified_file_count += 1
    except (OSError, zipfile.BadZipFile):
        errors.append(f"ARCHIVE_INVALID:{archive_name}")

    return _archive_report(
        archive_name,
        manifest_name,
        member_count,
        verified_file_count,
        errors,
    )


def _archive_report(
    archive_name: str,
    manifest_name: str,
    member_count: int,
    verified_file_count: int,
    errors: list[str],
) -> dict[str, object]:
    ordered = sorted(set(errors))
    return {
        "archive": archive_name,
        "manifest": manifest_name,
        "status": "PASS" if not ordered else "FAIL",
        "member_count": member_count,
        "verified_file_count": verified_file_count,
        "errors": ordered,
    }


def _release_evidence_report(
    output_directory: Path,
    expected_sha256: str | None,
) -> tuple[dict[str, object], list[str]]:
    if expected_sha256 is None:
        return {"status": "NOT_CHECKED"}, []
    errors: list[str] = []
    if not _SHA256.fullmatch(expected_sha256):
        return (
            {
                "status": "FAIL",
                "expected_sha256": expected_sha256,
                "errors": ["EXPECTED_EVIDENCE_HASH_INVALID"],
            },
            ["EXPECTED_EVIDENCE_HASH_INVALID"],
        )

    root_path = output_directory / "evidence.sqlite"
    root_hash: str | None = None
    try:
        root_hash = hashlib.sha256(root_path.read_bytes()).hexdigest()
    except OSError:
        errors.append("RELEASE_EVIDENCE_MISSING:evidence.sqlite")
    if root_hash is not None and root_hash != expected_sha256:
        errors.append("RELEASE_EVIDENCE_HASH_MISMATCH:evidence.sqlite")

    archive_hashes: dict[str, str | None] = {}
    members = (
        ("codex-workspace.zip", "evidence/evidence.sqlite"),
        ("chatgpt-web-runtime.zip", "evidence/evidence.sqlite"),
    )
    for archive_name, member_name in members:
        archive_path = output_directory / archive_name
        try:
            with zipfile.ZipFile(archive_path, "r") as archive:
                member_infos = [
                    info for info in archive.infolist()
                    if info.filename == member_name
                ]
                if len(member_infos) != 1:
                    errors.append(
                        f"RELEASE_EVIDENCE_MEMBER_INVALID:{archive_name}:{member_name}"
                    )
                    archive_hashes[archive_name] = None
                    continue
                archive_hash = hashlib.sha256(
                    archive.read(member_infos[0])
                ).hexdigest()
                archive_hashes[archive_name] = archive_hash
                if archive_hash != expected_sha256:
                    errors.append(
                        f"RELEASE_EVIDENCE_HASH_MISMATCH:{archive_name}:{member_name}"
                    )
        except (OSError, zipfile.BadZipFile, KeyError, RuntimeError):
            errors.append(f"RELEASE_EVIDENCE_ARCHIVE_INVALID:{archive_name}")
            archive_hashes[archive_name] = None

    ordered = sorted(set(errors))
    return (
        {
            "status": "PASS" if not ordered else "FAIL",
            "expected_sha256": expected_sha256,
            "root_sha256": root_hash,
            "codex_bundle_sha256": archive_hashes.get("codex-workspace.zip"),
            "web_runtime_sha256": archive_hashes.get("chatgpt-web-runtime.zip"),
            "errors": ordered,
        },
        ordered,
    )


def validate_release_output(
    output_directory: Path,
    *,
    expected_evidence_sha256: str | None = None,
) -> dict[str, object]:
    """Reopen final ZIPs and verify exact manifests, paths, sizes, and hashes."""
    output_report = _output_directory_report(output_directory)
    archives = [
        _verify_archive(
            output_directory / archive_name,
            manifest_name=manifest_name,
            expected_format=expected_format,
        )
        for archive_name, manifest_name, expected_format in _ARCHIVE_POLICIES
    ]
    errors = list(cast(list[str], output_report["errors"]))
    for archive in archives:
        errors.extend(cast(list[str], archive["errors"]))
    evidence_report, evidence_errors = _release_evidence_report(
        output_directory,
        expected_evidence_sha256,
    )
    errors.extend(evidence_errors)
    ordered = sorted(set(errors))
    return {
        "format": RELEASE_OUTPUT_VALIDATION_FORMAT,
        "version": 1,
        "status": "PASS" if not ordered else "FAIL",
        "errors": ordered,
        "output_directory": output_report,
        "archives": archives,
        "evidence_database": evidence_report,
    }
