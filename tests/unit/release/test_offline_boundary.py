import json
from pathlib import Path

import pytest

from evidence_review.offline_policy import APPLICATION_OFFLINE_GUARD, POLICY_VERSION
from evidence_review.release.offline_boundary import (
    resolve_manifest_member,
    source_policy_checks,
    validate_manifest_path_containment,
)


@pytest.mark.parametrize(
    "value",
    [
        "../outside.txt",
        "/tmp/outside.txt",
        "C:/outside.txt",
        "C:\\outside.txt",
        "nested\\file.txt",
    ],
)
def test_manifest_member_rejects_path_escape(tmp_path: Path, value: str) -> None:
    with pytest.raises(ValueError, match="manifest path"):
        resolve_manifest_member(tmp_path, value)


def test_manifest_member_resolves_safe_relative_path(tmp_path: Path) -> None:
    assert resolve_manifest_member(tmp_path, "nested/file.txt") == (
        tmp_path / "nested" / "file.txt"
    ).resolve(strict=False)


def test_manifest_containment_walks_nested_path_fields(tmp_path: Path) -> None:
    manifest = tmp_path / "manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "files": [
                    {"path": "safe/a.txt"},
                    {"nested": {"path": "safe/b.txt"}},
                ]
            }
        ),
        encoding="utf-8",
    )

    assert validate_manifest_path_containment(manifest) == (
        (tmp_path / "safe" / "a.txt").resolve(strict=False),
        (tmp_path / "safe" / "b.txt").resolve(strict=False),
    )


def test_manifest_containment_rejects_escape_before_member_read(tmp_path: Path) -> None:
    manifest = tmp_path / "manifest.json"
    manifest.write_text(
        json.dumps({"files": [{"path": "../outside.txt"}]}),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="escapes root"):
        validate_manifest_path_containment(manifest)


def test_source_policy_checks_report_shared_policy(tmp_path: Path) -> None:
    source = tmp_path / "src" / "evidence_review"
    source.mkdir(parents=True)
    (source / "safe.py").write_text("value = 1\n", encoding="utf-8")

    assert source_policy_checks(tmp_path) == (
        f"offline_policy_version:{POLICY_VERSION}",
        f"offline_assurance:{APPLICATION_OFFLINE_GUARD}",
        "offline_source_scan:pass",
    )


def test_source_policy_checks_report_process_capability(tmp_path: Path) -> None:
    source = tmp_path / "src" / "evidence_review"
    source.mkdir(parents=True)
    (source / "unsafe.py").write_text(
        "import os\nos.system('whoami')\n",
        encoding="utf-8",
    )

    checks = source_policy_checks(tmp_path)

    assert any("FORBIDDEN_PROCESS_CALL:os.system" in check for check in checks)
