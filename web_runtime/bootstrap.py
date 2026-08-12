"""Installation-free web runtime bootstrap and self-test."""
from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
from pathlib import Path


def validate_database(database: Path) -> None:
    """Validate the bundled database without opening it for writes."""
    try:
        uri = f"{database.resolve().as_uri()}?mode=ro"
        connection = sqlite3.connect(uri, uri=True)
        try:
            integrity = connection.execute(
                "PRAGMA integrity_check"
            ).fetchone()
            foreign_keys = connection.execute(
                "PRAGMA foreign_key_check"
            ).fetchall()
        finally:
            connection.close()
    except sqlite3.DatabaseError as error:
        raise SystemExit("SQLITE_INTEGRITY_FAILED") from error
    if integrity != ("ok",) or foreign_keys:
        raise SystemExit("SQLITE_INTEGRITY_FAILED")


def self_test(root: Path) -> None:
    database = root / "evidence/evidence.sqlite"
    required = [
        database,
        root / "rules/manifests/active.json",
        root / "formulas/manifest.json",
        root / "examples/sample-request.json",
        root / "runtime-manifest.json",
    ]
    for path in required:
        if not path.is_file():
            raise SystemExit(f"missing runtime file: {path.relative_to(root)}")
    manifest = json.loads(
        (root / "runtime-manifest.json").read_text(encoding="utf-8")
    )
    for item in manifest["files"]:
        path = root / item["path"]
        if hashlib.sha256(path.read_bytes()).hexdigest() != item["sha256"]:
            raise SystemExit(f"hash mismatch: {item['path']}")
    validate_database(database)
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
