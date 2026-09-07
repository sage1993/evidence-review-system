from __future__ import annotations

import json
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
    assert "scripts/validate_release.py" in output
    assert "scripts/build_release.py" in output
    assert "scripts/validate_legacy_ansim_workspace.py" in output


def test_explicit_legacy_validator_keeps_ansim_grist_contract() -> None:
    legacy = SCRIPTS / "validate_legacy_ansim_workspace.py"
    assert legacy.is_file()
    assert "legacy" in legacy.read_text(encoding="utf-8").lower()

    completed = _run_script("validate_legacy_ansim_workspace.py")

    assert completed.returncode == 1
    payload = json.loads(completed.stdout)
    assert payload["status"] == "FAIL"
    assert any(
        "01_database/안심주택DB.grist" in error
        for error in payload["errors"]
    )
