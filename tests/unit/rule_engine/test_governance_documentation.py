from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

from evidence_review.cli import build_parser
from evidence_review.rule_engine.governance_contract import (
    load_active_rule_manifest_bytes,
    load_rule_activation_approval_bytes,
    load_rule_golden_report_bytes,
)

ROOT = Path(__file__).parents[3]
DOC = ROOT / "docs" / "RULE_ACTIVATION_GOVERNANCE.md"
ACCEPTANCE = ROOT / "docs" / "acceptance" / "issue-48"
MANIFEST = ROOT / "tests" / "fixtures" / "ansim" / "rules" / "manifests" / "active.json"
EXPECTED_IDS = (
    "ANSIM-ARTERIAL-FRONTAGE-ONE-EIGHTH",
    "ANSIM-MINIMUM-SITE-AREA-1500",
    "ANSIM-TWO-ROAD-SIDES-6M",
    "ANSIM-ZONING-CHANGE-FAR-MAX-400",
    "ANSIM-ZONING-CHANGE-PUBLIC-CONTRIBUTION-MIN-15",
    "ANSIM-ZONING-CHANGE-RESIDENTIAL-RATIO-MIN-85",
)


def _duplicate_free_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _load_strict(path: Path) -> dict[str, object]:
    value = json.loads(
        path.read_text(encoding="utf-8"),
        object_pairs_hook=_duplicate_free_object,
    )
    assert isinstance(value, dict)
    return value


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _normalized_markdown(path: Path) -> str:
    return re.sub(r"\s+", " ", path.read_text(encoding="utf-8")).strip()


def test_real_cli_parsers_expose_governance_commands() -> None:
    parser = build_parser()

    golden = parser.parse_args(
        [
            "rules",
            "run-golden",
            "--repository-root",
            ".",
            "--fixture-manifest",
            "fixture.json",
            "--actual-root",
            "actual",
            "--report",
            "report.json",
            "--source-commit",
            "a" * 40,
            "--command",
            "python -m evidence_review rules run-golden",
        ]
    )
    activate = parser.parse_args(
        [
            "rules",
            "build-active-manifest",
            "--repository-root",
            ".",
            "--approvals",
            "rules/activation/approvals",
            "--output",
            "rules/manifests/active.json",
            "--report",
            "activation-report.json",
        ]
    )
    select = parser.parse_args(
        [
            "rules",
            "select",
            "--repository-root",
            ".",
            "--manifest",
            "rules/manifests/active.json",
            "--context",
            "context.json",
        ]
    )

    assert golden.rules_stage == "run-golden"
    assert activate.rules_stage == "build-active-manifest"
    assert select.rules_stage == "select"


def test_governance_documentation_is_explicit_and_fail_closed() -> None:
    text = _normalized_markdown(DOC)

    required = (
        "candidate rule",
        "approved copy",
        "run-golden",
        "Human activation approval",
        "build-active-manifest",
        "Runtime selection",
        "ABSTAIN / NO_APPLICABLE_ACTIVE_RULE",
        "BLOCKED",
        "human_decision",
        "암호학적 증명이 아니다",
        "GitHub Actions PASS",
    )
    for phrase in required:
        assert phrase in text
    assert "일부 정상 entry만 실행" in text
    assert "Candidate 디렉터리의 파일은 런타임에서 스캔하지 않는다" in text


def test_all_acceptance_references_exist_and_decode() -> None:
    manifest = load_active_rule_manifest_bytes(MANIFEST.read_bytes())
    assert tuple(item.rule_id for item in manifest.rules) == EXPECTED_IDS

    for entry in manifest.rules:
        approval_path = ROOT / entry.approval_path
        report_path = ROOT / entry.golden_report_path
        approved_path = ROOT / entry.approved_rule_path
        candidate_path = ROOT / entry.candidate_path

        assert approval_path.is_file()
        assert report_path.is_file()
        assert approved_path.is_file()
        assert candidate_path.is_file()
        assert _sha256(approval_path) == entry.approval_sha256
        assert _sha256(report_path) == entry.golden_report_sha256
        assert _sha256(approved_path) == entry.approved_rule_sha256
        assert _sha256(candidate_path) == entry.candidate_sha256

        approval = load_rule_activation_approval_bytes(approval_path.read_bytes())
        report = load_rule_golden_report_bytes(report_path.read_bytes())
        assert approval.rule_id == entry.rule_id
        assert approval.scope.document_family == "ANSIM"
        assert report.rule_id == entry.rule_id
        assert report.status == "PASS"
        assert report.case_count >= 2
        assert (ROOT / report.fixture_manifest_path).is_file()
        for case in report.cases:
            assert (ROOT / case.fixture_path).is_file()
            assert (ROOT / case.expected_path).is_file()
