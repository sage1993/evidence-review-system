from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "scripts"


def _run_script(name: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPTS / name)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )


def test_validate_workspace_is_retired_fail_closed() -> None:
    completed = _run_script("validate_workspace.py")

    assert completed.returncode == 2
    output = completed.stdout + completed.stderr
    assert "retired" in output.lower()
    assert (
        "py -3.13 scripts/validate_release.py <workspace> --run-id <RUN-ID>"
        in output
    )
    assert (
        "py -3.13 scripts/build_release.py <workspace> <output-dir> --run-id <RUN-ID>"
        in output
    )
    assert "py -3.13 scripts/validate_legacy_ansim_workspace.py" in output


def test_explicit_legacy_validator_keeps_ansim_grist_contract(tmp_path: Path) -> None:
    legacy = SCRIPTS / "validate_legacy_ansim_workspace.py"
    source = legacy.read_text(encoding="utf-8")
    assert "legacy" in source.lower()
    assert "01_database" in source
    assert "안심주택DB.grist" in source
    assert "04_visuals" in source

    copied = tmp_path / "scripts" / legacy.name
    copied.parent.mkdir()
    copied.write_text(source, encoding="utf-8")
    completed = subprocess.run(
        [sys.executable, str(copied)],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
        env={**os.environ, "PYTHONIOENCODING": "ascii"},
    )

    assert completed.returncode == 1
    payload = json.loads(completed.stdout)
    assert payload["status"] == "FAIL"
    assert any(
        "01_database/안심주택DB.grist" in error
        for error in payload["errors"]
    )


def test_current_docs_name_release_authority_and_legacy_scope() -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    policy = (ROOT / "docs" / "MANUAL_ACCEPTANCE_POLICY.md").read_text(
        encoding="utf-8"
    )
    plans_index = (ROOT / "docs" / "superpowers" / "plans" / "README.md").read_text(
        encoding="utf-8"
    )

    assert "scripts/validate_workspace.py" not in readme
    assert (
        "py -3.13 scripts/validate_release.py <workspace> --run-id <RUN-ID>"
        in policy
    )
    assert (
        "py -3.13 scripts/build_release.py <workspace> <output-dir> --run-id <RUN-ID>"
        in policy
    )
    assert "scripts/validate_legacy_ansim_workspace.py" in policy
    assert "not a current release gate" in policy.lower()
    assert "historical" in plans_index.lower()
    assert "docs/MANUAL_ACCEPTANCE_POLICY.md" in plans_index
    assert "scripts/validate_workspace.py" in plans_index
    assert "superseded" in plans_index.lower()
