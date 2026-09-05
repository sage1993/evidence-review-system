from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path

import pytest

from web_runtime.bootstrap import self_test

_MANIFEST_FORMAT = "evidence-review/chatgpt-web-runtime"
_PRIVATE_REQUIRED = (
    "evidence/evidence.sqlite",
    "rules/manifests/active.json",
    "formulas/manifest.json",
    "examples/sample-request.json",
)
_PUBLIC_REQUIRED = (
    "formulas/manifest.json",
    "examples/sample-request.json",
)


def _write_file(root: Path, relative: str, payload: bytes) -> Path:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)
    return path


def _write_runtime(
    root: Path,
    *,
    public: bool = False,
    omitted_manifest_paths: frozenset[str] = frozenset(),
) -> None:
    required = _PUBLIC_REQUIRED if public else _PRIVATE_REQUIRED
    inventory = list(required)
    if public:
        _write_file(root, "public-runtime.txt", b"public runtime\n")
        inventory.append("public-runtime.txt")
    else:
        database = root / "evidence" / "evidence.sqlite"
        database.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(database)
        connection.execute("CREATE TABLE probe(id INTEGER PRIMARY KEY)")
        connection.commit()
        connection.close()
        _write_file(root, "rules/manifests/active.json", b"{}")

    _write_file(root, "formulas/manifest.json", b"{}")
    _write_file(root, "examples/sample-request.json", b"{}")

    entries: list[dict[str, object]] = []
    for relative in inventory:
        if relative in omitted_manifest_paths:
            continue
        path = root / relative
        payload = path.read_bytes()
        entries.append(
            {
                "path": relative,
                "sha256": hashlib.sha256(payload).hexdigest(),
                "size": len(payload),
            }
        )
    manifest = {
        "format": _MANIFEST_FORMAT,
        "version": 1,
        "files": entries,
    }
    _write_file(
        root,
        "runtime-manifest.json",
        json.dumps(manifest, sort_keys=True).encode("utf-8"),
    )


def test_empty_runtime_manifest_is_incomplete(tmp_path: Path) -> None:
    _write_runtime(tmp_path, omitted_manifest_paths=frozenset(_PRIVATE_REQUIRED))

    with pytest.raises(SystemExit, match="RUNTIME_MANIFEST_INCOMPLETE"):
        self_test(tmp_path)


@pytest.mark.parametrize(
    "omitted",
    ["evidence/evidence.sqlite", "rules/manifests/active.json"],
)
def test_private_required_file_must_be_manifest_bound(
    tmp_path: Path,
    omitted: str,
) -> None:
    _write_runtime(tmp_path, omitted_manifest_paths=frozenset({omitted}))

    with pytest.raises(SystemExit, match="RUNTIME_MANIFEST_INCOMPLETE"):
        self_test(tmp_path)


def test_public_required_file_must_be_manifest_bound(tmp_path: Path) -> None:
    _write_runtime(
        tmp_path,
        public=True,
        omitted_manifest_paths=frozenset({"formulas/manifest.json"}),
    )

    with pytest.raises(SystemExit, match="RUNTIME_MANIFEST_INCOMPLETE"):
        self_test(tmp_path)


def test_unlisted_runtime_cache_does_not_invalidate_manifest(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _write_runtime(tmp_path)
    _write_file(tmp_path, "evidence_review/__pycache__/module.cpython-313.pyc", b"cache")

    self_test(tmp_path)

    assert capsys.readouterr().out.strip() == "WEB_RUNTIME_SELF_TEST_PASS"


def test_complete_required_manifest_passes(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _write_runtime(tmp_path)

    self_test(tmp_path)

    assert capsys.readouterr().out.strip() == "WEB_RUNTIME_SELF_TEST_PASS"


def test_complete_public_manifest_passes(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _write_runtime(tmp_path, public=True)

    self_test(tmp_path)

    assert capsys.readouterr().out.strip() == "WEB_RUNTIME_PUBLIC_SELF_TEST_PASS"
