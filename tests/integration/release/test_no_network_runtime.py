import json
import os
import shutil
import sqlite3
import subprocess
import sys
from pathlib import Path

from evidence_review.release.validator import blocked_network, validate_release_workspace

from ._fixtures import write_valid_finalized_run


def _workspace(root: Path) -> str:
    repository_root = Path(__file__).parents[3]
    shutil.copytree(
        repository_root / "src/evidence_review",
        root / "src/evidence_review",
    )
    shutil.copytree(
        repository_root / "src/ansim_review",
        root / "src/ansim_review",
    )
    (root / "evidence").mkdir()
    connection = sqlite3.connect(root / "evidence/ansim-evidence.sqlite")
    connection.execute("CREATE TABLE evidence(id TEXT PRIMARY KEY)")
    connection.commit()
    connection.close()
    (root / "rules/approved").mkdir(parents=True)
    (root / "rules/approved/R1.json").write_text("{}", encoding="utf-8")
    (root / "rules/manifests").mkdir()
    (root / "rules/manifests/active.json").write_text("{}", encoding="utf-8")
    (root / "formulas").mkdir()
    (root / "formulas/manifest.json").write_text("{}", encoding="utf-8")
    (root / "examples").mkdir()
    (root / "examples/sample-request.json").write_text("{}", encoding="utf-8")
    (root / "README.md").write_text("# Release fixture\n", encoding="utf-8")
    (root / "documentation-integrity.json").write_text(
        json.dumps(
            {
                "format": "evidence-review/documentation-integrity-config",
                "version": 1,
                "current_roots": ["README.md"],
                "historical_roots": [],
                "current_overrides": [],
                "historical_overrides": [],
                "generated_documents": [],
            }
        ),
        encoding="utf-8",
    )
    shutil.copytree(repository_root / "web_runtime", root / "web_runtime")
    (root / "tests/golden/questions").mkdir(parents=True)
    shutil.copy2(
        repository_root / "tests/golden/questions/ansim_cases.json",
        root / "tests/golden/questions/ansim_cases.json",
    )
    return write_valid_finalized_run(root)


def test_release_validation_blocks_network_and_checks_reproducibility(
    tmp_path: Path,
) -> None:
    root = tmp_path / "workspace"
    run_id = _workspace(root)
    output = tmp_path / "release-validation.json"
    with blocked_network():
        report = validate_release_workspace(root, output, run_id=run_id)
    assert report["status"] == "PASS"
    assert report["forbidden_imports"] == []
    sqlite_result = report["sqlite"]
    web_zip = report["web_zip"]
    assert isinstance(sqlite_result, dict)
    assert isinstance(web_zip, dict)
    assert sqlite_result["integrity_check"] == "ok"
    assert web_zip["byte_identical"] is True
    assert json.loads(output.read_text(encoding="utf-8")) == report


def test_release_validation_requires_explicit_run_id(tmp_path: Path) -> None:
    root = tmp_path / "workspace"
    _workspace(root)

    report = validate_release_workspace(root)

    assert report["status"] == "FAIL"
    assert "FINAL_REVIEW_PACKET_VALIDATION_FAILED" in report["errors"]
    assert report["final_packet"]["status"] == "FAIL"


def test_release_validation_rejects_tampered_final_packet(tmp_path: Path) -> None:
    root = tmp_path / "workspace"
    run_id = _workspace(root)
    packet = root / "runs" / run_id / "final-review-packet.json"
    document = json.loads(packet.read_text(encoding="utf-8"))
    document["human_decision"] = "SATISFIED"
    packet.write_bytes(json.dumps(document).encode("utf-8"))

    report = validate_release_workspace(root, run_id=run_id)

    assert report["status"] == "FAIL"
    assert "FINAL_REVIEW_PACKET_VALIDATION_FAILED" in report["errors"]
    assert report["final_packet"]["status"] == "FAIL"


def test_release_validation_cli_requires_run_id_option() -> None:
    repository_root = Path(__file__).parents[3]
    environment = os.environ.copy()
    environment["PYTHONPATH"] = str(repository_root / "src")

    completed = subprocess.run(
        [
            sys.executable,
            str(repository_root / "scripts" / "validate_release.py"),
            "--help",
        ],
        cwd=repository_root,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0
    assert "--run-id" in completed.stdout
