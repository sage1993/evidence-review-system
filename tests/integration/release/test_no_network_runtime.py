import hashlib
import json
import os
import shutil
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest
from helpers.rule_governance import build_valid_governance_tree

from evidence_review.canonical_json import dump_bytes
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
    build_valid_governance_tree(root)
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


def test_release_validation_reports_governed_rule_provenance(tmp_path: Path) -> None:
    root = tmp_path / "workspace"
    run_id = _workspace(root)

    report = validate_release_workspace(root, run_id=run_id)

    governed_rules = report["governed_rules"]
    assert governed_rules["status"] == "ABSTAIN"
    assert governed_rules["manifest_path"] == "rules/manifests/active.json"
    assert governed_rules["validator"] == (
        "evidence_review.rule_engine.manifest.load_governed_active_rules"
    )
    assert len(governed_rules["manifest_sha256"]) == 64
    assert governed_rules["context"] == {
        "document_family": None,
        "document_kind": None,
        "jurisdiction": None,
        "program": None,
    }
    assert governed_rules["reasons"] == ["NO_APPLICABLE_ACTIVE_RULE"]
    assert governed_rules["selected_rules"] == []
    assert governed_rules["excluded_rules"] == [
        {
            "rule_id": "TEST-RULE-001",
            "rule_version": "1.0.0",
            "code": "MISSING_SCOPE_VALUE",
        }
    ]


def test_release_validation_rejects_missing_active_rule_manifest(tmp_path: Path) -> None:
    root = tmp_path / "workspace"
    run_id = _workspace(root)
    (root / "rules/manifests/active.json").unlink()

    report = validate_release_workspace(root, run_id=run_id)

    assert report["status"] == "FAIL"
    assert "GOVERNED_RULE_VALIDATION_FAILED" in report["errors"]
    assert report["governed_rules"]["status"] == "BLOCKED"
    assert report["governed_rules"]["reasons"] == ["ACTIVE_RULE_MANIFEST_MISSING"]


def test_release_validation_rejects_non_passing_governed_golden_report(
    tmp_path: Path,
) -> None:
    root = tmp_path / "workspace"
    run_id = _workspace(root)
    report_path = root / "rules/golden/reports/TEST-RULE-001@1.0.0.json"
    report_payload = json.loads(report_path.read_text(encoding="utf-8"))
    report_payload["status"] = "FAIL"
    report_payload["passed_count"] = 0
    report_payload["failed_count"] = 1
    report_payload["cases"][0]["status"] = "FAIL"
    report_path.write_bytes(dump_bytes(report_payload))

    approval_path = root / "rules/activation/approvals/TEST-RULE-001@1.0.0.json"
    approval_payload = json.loads(approval_path.read_text(encoding="utf-8"))
    report_sha256 = hashlib.sha256(report_path.read_bytes()).hexdigest()
    approval_payload["golden_report_sha256"] = report_sha256
    approval_path.write_bytes(dump_bytes(approval_payload))

    manifest_path = root / "rules/manifests/active.json"
    manifest_payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    entry = manifest_payload["rules"][0]
    entry["golden_report_sha256"] = report_sha256
    entry["approval_sha256"] = hashlib.sha256(approval_path.read_bytes()).hexdigest()
    manifest_path.write_bytes(dump_bytes(manifest_payload))

    release_report = validate_release_workspace(root, run_id=run_id)

    assert release_report["status"] == "FAIL"
    assert "GOVERNED_RULE_VALIDATION_FAILED" in release_report["errors"]
    assert release_report["governed_rules"]["status"] == "BLOCKED"
    assert release_report["governed_rules"]["reasons"] == ["GOLDEN_REPORT_NOT_PASSING"]


@pytest.mark.parametrize(
    ("mutation", "expected_reason"),
    [
        ("malformed", "ACTIVE_MANIFEST_INVALID"),
        ("version", "ACTIVE_MANIFEST_INVALID"),
        ("candidate_hash", "CANDIDATE_HASH_MISMATCH"),
        ("approved_tamper", "ACTIVE_RULE_HASH_MISMATCH"),
        ("approved_missing", "ARTIFACT_MISSING"),
    ],
)
def test_release_validation_rejects_invalid_governed_rule_authority(
    tmp_path: Path,
    mutation: str,
    expected_reason: str,
) -> None:
    root = tmp_path / "workspace"
    run_id = _workspace(root)
    manifest_path = root / "rules/manifests/active.json"
    candidate_path = root / "rules/candidates/TEST-RULE-001@1.0.0.json"
    approved_rule_path = root / "rules/approved/TEST-RULE-001@1.0.0.json"
    if mutation == "malformed":
        manifest_path.write_bytes(b"{}")
    elif mutation == "version":
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["version"] = 1
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    elif mutation == "candidate_hash":
        candidate_path.write_bytes(candidate_path.read_bytes() + b" ")
    elif mutation == "approved_tamper":
        approved_rule_path.write_bytes(approved_rule_path.read_bytes() + b" ")
    elif mutation == "approved_missing":
        approved_rule_path.unlink()
    else:
        raise AssertionError(f"unexpected mutation: {mutation}")

    report = validate_release_workspace(root, run_id=run_id)

    assert report["status"] == "FAIL"
    assert "GOVERNED_RULE_VALIDATION_FAILED" in report["errors"]
    assert report["governed_rules"]["status"] == "BLOCKED"
    assert expected_reason in report["governed_rules"]["reasons"]


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
