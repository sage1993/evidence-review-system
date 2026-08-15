"""Installation-free web runtime bootstrap and self-test."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sqlite3
import stat
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

_MANIFEST_FORMAT = "evidence-review/chatgpt-web-runtime"
_MANIFEST_VERSION = 1
_REPARSE_POINT = 0x400
_HASH_CHUNK_SIZE = 1024 * 1024


@dataclass(frozen=True, slots=True)
class ManifestEntry:
    path: str
    sha256: str
    size: int


def _fail(code: str) -> None:
    raise SystemExit(code)


def _validate_relative_path_text(relative: str) -> tuple[str, ...]:
    if not isinstance(relative, str) or not relative:
        _fail("UNSAFE_RUNTIME_PATH")
    if "\\" in relative or "\x00" in relative or ":" in relative:
        _fail("UNSAFE_RUNTIME_PATH")
    raw_parts = relative.split("/")
    if any(part in {"", ".", ".."} for part in raw_parts):
        _fail("UNSAFE_RUNTIME_PATH")
    pure = PurePosixPath(relative)
    if pure.is_absolute() or not pure.parts:
        _fail("UNSAFE_RUNTIME_PATH")
    if tuple(raw_parts) != pure.parts:
        _fail("UNSAFE_RUNTIME_PATH")
    return pure.parts


def safe_runtime_file(root: Path, relative: str) -> Path:
    """Resolve one untrusted manifest path below *root* without following links."""
    parts = _validate_relative_path_text(relative)
    root_resolved = root.resolve()
    current = root_resolved
    for part in parts:
        current = current / part
        try:
            info = current.lstat()
        except FileNotFoundError:
            continue
        except OSError:
            _fail("RUNTIME_FILE_NOT_REGULAR")
        if stat.S_ISLNK(info.st_mode):
            _fail("UNSAFE_RUNTIME_PATH")
        if getattr(info, "st_file_attributes", 0) & _REPARSE_POINT:
            _fail("UNSAFE_RUNTIME_PATH")
    try:
        current.resolve(strict=False).relative_to(root_resolved)
    except (OSError, ValueError):
        _fail("UNSAFE_RUNTIME_PATH")
    return current


def _require_regular_file(path: Path) -> os.stat_result:
    try:
        info = path.lstat()
    except FileNotFoundError:
        _fail("RUNTIME_FILE_MISSING")
    except OSError:
        _fail("RUNTIME_FILE_NOT_REGULAR")
    if stat.S_ISLNK(info.st_mode):
        _fail("UNSAFE_RUNTIME_PATH")
    if getattr(info, "st_file_attributes", 0) & _REPARSE_POINT:
        _fail("UNSAFE_RUNTIME_PATH")
    if not stat.S_ISREG(info.st_mode):
        _fail("RUNTIME_FILE_NOT_REGULAR")
    return info


def load_manifest(path: Path) -> tuple[ManifestEntry, ...]:
    """Decode the exact runtime-manifest v1 contract."""
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        _fail("INVALID_RUNTIME_MANIFEST")
    if not isinstance(raw, dict) or set(raw) != {"format", "version", "files"}:
        _fail("INVALID_RUNTIME_MANIFEST")
    if raw["format"] != _MANIFEST_FORMAT:
        _fail("INVALID_RUNTIME_MANIFEST")
    if type(raw["version"]) is not int or raw["version"] != _MANIFEST_VERSION:
        _fail("INVALID_RUNTIME_MANIFEST")
    files = raw["files"]
    if not isinstance(files, list):
        _fail("INVALID_RUNTIME_MANIFEST")

    entries: list[ManifestEntry] = []
    exact_paths: set[str] = set()
    folded_paths: set[str] = set()
    for item in files:
        if not isinstance(item, dict) or set(item) != {"path", "sha256", "size"}:
            _fail("INVALID_RUNTIME_MANIFEST")
        relative = item["path"]
        digest = item["sha256"]
        size = item["size"]
        if not isinstance(relative, str):
            _fail("INVALID_RUNTIME_MANIFEST")
        _validate_relative_path_text(relative)
        if (
            not isinstance(digest, str)
            or len(digest) != 64
            or any(character not in "0123456789abcdef" for character in digest)
        ):
            _fail("INVALID_RUNTIME_MANIFEST")
        if type(size) is not int or size < 0:
            _fail("INVALID_RUNTIME_MANIFEST")
        folded = relative.casefold()
        if relative in exact_paths or folded in folded_paths:
            _fail("INVALID_RUNTIME_MANIFEST")
        exact_paths.add(relative)
        folded_paths.add(folded)
        entries.append(ManifestEntry(relative, digest, size))
    return tuple(entries)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as stream:
            while chunk := stream.read(_HASH_CHUNK_SIZE):
                digest.update(chunk)
    except OSError:
        _fail("RUNTIME_FILE_NOT_REGULAR")
    return digest.hexdigest()


def validate_database(database: Path) -> None:
    """Validate the bundled database without opening it for writes."""
    try:
        uri = f"{database.resolve().as_uri()}?mode=ro"
        connection = sqlite3.connect(uri, uri=True)
        try:
            integrity = connection.execute("PRAGMA integrity_check").fetchone()
            foreign_keys = connection.execute("PRAGMA foreign_key_check").fetchall()
        finally:
            connection.close()
    except sqlite3.DatabaseError as error:
        raise SystemExit("SQLITE_INTEGRITY_FAILED") from error
    if integrity != ("ok",) or foreign_keys:
        raise SystemExit("SQLITE_INTEGRITY_FAILED")


def self_test(root: Path) -> None:
    root = root.resolve()
    required_paths = (
        "evidence/evidence.sqlite",
        "rules/manifests/active.json",
        "formulas/manifest.json",
        "examples/sample-request.json",
        "runtime-manifest.json",
    )
    required: dict[str, Path] = {}
    for relative in required_paths:
        path = safe_runtime_file(root, relative)
        _require_regular_file(path)
        required[relative] = path

    entries = load_manifest(required["runtime-manifest.json"])
    for entry in entries:
        path = safe_runtime_file(root, entry.path)
        info = _require_regular_file(path)
        if info.st_size != entry.size:
            _fail("RUNTIME_FILE_SIZE_MISMATCH")
        if sha256_file(path) != entry.sha256:
            _fail("RUNTIME_FILE_HASH_MISMATCH")

    validate_database(required["evidence/evidence.sqlite"])
    print("WEB_RUNTIME_SELF_TEST_PASS")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--self-test", action="store_true")
    arguments = parser.parse_args()
    if arguments.self_test:
        self_test(Path(__file__).resolve().parent)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
