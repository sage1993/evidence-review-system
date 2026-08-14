from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


def test_doctor_reports_current_checkout(tmp_path: Path) -> None:
    del tmp_path
    repo = Path(__file__).resolve().parents[3]
    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "evidence_review",
            "doctor",
            "--repository-root",
            str(repo),
        ],
        cwd=repo,
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode == 0
    document = json.loads(completed.stdout)
    assert document["status"] == "OK"
    assert Path(document["repository_root"]).resolve() == repo.resolve()
    assert document["package_checkout_match"] is True
