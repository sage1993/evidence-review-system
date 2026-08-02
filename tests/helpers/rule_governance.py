"""Deterministic complete governance trees for rule-engine tests."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Final

from ansim_review.canonical_json import dump_bytes
from ansim_review.contracts.common import BBox
from ansim_review.contracts.evidence import EvidenceRecord
from ansim_review.rule_engine.evaluator import evaluate_rule
from ansim_review.rule_engine.governance_contract import (
    ActiveRuleEntry,
    ActiveRuleManifest,
    GoldenCaseRecord,
    RuleActivationApproval,
    RuleGoldenReport,
    RuleScope,
    active_rule_manifest_bytes,
    rule_activation_approval_bytes,
    rule_golden_report_bytes,
)
from ansim_review.rule_engine.loader import load_rule

GOVERNANCE_MUTATIONS: Final[tuple[str, ...]] = (
    "active_manifest_bytes",
    "approval_bytes",
    "golden_report_bytes",
    "candidate_bytes",
    "approved_rule_bytes",
    "fixture_manifest_bytes",
    "fixture_bytes",
    "expected_bytes",
    "path_traversal",
    "duplicate_rule_id",
)


@dataclass(frozen=True, slots=True)
class GovernanceTree:
    root: Path
    manifest_path: Path
    approval_paths: tuple[Path, ...]
    golden_report_paths: tuple[Path, ...]
    candidate_paths: tuple[Path, ...]
    approved_rule_paths: tuple[Path, ...]
    fixture_manifest_paths: tuple[Path, ...]
    fixture_paths: tuple[Path, ...]
    expected_paths: tuple[Path, ...]
    actual_paths: tuple[Path, ...]


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


def _relative(root: Path, path: Path) -> str:
    return path.relative_to(root).as_posix()


def _rule_payload(index: int) -> dict[str, object]:
    suffix = f"{index:03d}"
    return {
        "rule_id": f"TEST-RULE-{suffix}",
        "version": "1.0.0",
        "title": f"Governance test rule {suffix}",
        "input_schema": {"value": {"type": "integer", "required": True}},
        "source_citations": [
            {
                "citation_id": f"CITATION-{suffix}",
                "document_id": f"DOC-{suffix}",
                "revision_id": f"REV-{suffix}",
                "page_number": 1,
                "evidence_id": f"EVIDENCE-{suffix}",
                "bbox": [0, 0, 10, 10],
                "source_hash": f"{index:x}"[-1] * 64,
            }
        ],
        "human_decision_required": True,
        "expression": {
            "compare": {
                "operator": "gte",
                "left": {"input": "value"},
                "right": {"literal": 1},
            }
        },
    }


def _approved_payload(candidate: dict[str, object], candidate_sha256: str) -> dict[str, object]:
    payload = dict(candidate)
    payload["approval"] = {
        "reviewer_id": "fixture-reviewer",
        "review_date": "2026-08-02",
        "candidate_sha256": candidate_sha256,
    }
    return payload


def _evidence(index: int) -> EvidenceRecord:
    suffix = f"{index:03d}"
    return EvidenceRecord(
        evidence_id=f"EVIDENCE-{suffix}",
        document_id=f"DOC-{suffix}",
        revision_id=f"REV-{suffix}",
        page_number=1,
        element_id=f"ELEMENT-{suffix}",
        evidence_type="text",
        bbox=BBox(0, 0, 10, 10),
        source_hash=f"{index:x}"[-1] * 64,
        raw_text="value must be at least one",
        normalized_text="value must be at least one",
    )


def _fixture_case_payload(index: int) -> dict[str, object]:
    return {
        "format": "evidence-review/rule-golden-case",
        "version": 1,
        "inputs": {"value": 1},
        "calculations": [],
        "expected_formula_manifest_hash": None,
        "evidence_records": [asdict(_evidence(index))],
    }


def _fixture_manifest_payload(
    rule_id: str,
    candidate_path: str,
    approved_rule_path: str,
    case_id: str,
    fixture_path: str,
    expected_path: str,
    actual_path: str,
) -> dict[str, object]:
    return {
        "format": "evidence-review/rule-golden-fixture",
        "version": 1,
        "rule_id": rule_id,
        "rule_version": "1.0.0",
        "candidate_path": candidate_path,
        "approved_rule_path": approved_rule_path,
        "cases": [
            {
                "case_id": case_id,
                "fixture_path": fixture_path,
                "expected_path": expected_path,
                "actual_path": actual_path,
            }
        ],
    }


def build_valid_governance_tree(
    root: Path,
    *,
    rule_count: int = 1,
) -> GovernanceTree:
    """Create one complete deterministic governance graph below ``root``."""
    if rule_count < 1:
        raise ValueError("rule_count must be positive")
    root.mkdir(parents=True, exist_ok=True)

    approval_paths: list[Path] = []
    report_paths: list[Path] = []
    candidate_paths: list[Path] = []
    approved_paths: list[Path] = []
    fixture_manifest_paths: list[Path] = []
    fixture_paths: list[Path] = []
    expected_paths: list[Path] = []
    actual_paths: list[Path] = []
    entries: list[ActiveRuleEntry] = []

    for index in range(1, rule_count + 1):
        suffix = f"{index:03d}"
        rule_id = f"TEST-RULE-{suffix}"
        basename = f"{rule_id}@1.0.0.json"
        case_id = f"CASE-{suffix}"

        candidate_path = root / "rules" / "candidates" / basename
        approved_path = root / "rules" / "approved" / basename
        fixture_manifest_path = root / "rules" / "golden" / "fixtures" / basename
        fixture_path = root / "rules" / "golden" / "cases" / rule_id / f"{case_id}.json"
        expected_path = root / "rules" / "golden" / "expected" / rule_id / f"{case_id}.json"
        actual_path = root / "build" / "rules" / "golden" / "actual" / rule_id / f"{case_id}.json"
        report_path = root / "rules" / "golden" / "reports" / basename
        approval_path = root / "rules" / "activation" / "approvals" / basename

        candidate = _rule_payload(index)
        _write(candidate_path, dump_bytes(candidate))
        candidate_hash = _sha256(candidate_path)
        _write(approved_path, dump_bytes(_approved_payload(candidate, candidate_hash)))
        approved_hash = _sha256(approved_path)

        fixture_payload = _fixture_case_payload(index)
        _write(fixture_path, dump_bytes(fixture_payload))
        rule = load_rule(candidate)
        result = evaluate_rule(
            rule,
            {"value": 1},
            evidence_records=[_evidence(index)],
        )
        result_bytes = dump_bytes(asdict(result))
        _write(expected_path, result_bytes)
        _write(actual_path, result_bytes)

        fixture_manifest = _fixture_manifest_payload(
            rule_id,
            _relative(root, candidate_path),
            _relative(root, approved_path),
            case_id,
            _relative(root, fixture_path),
            _relative(root, expected_path),
            _relative(root, actual_path),
        )
        _write(fixture_manifest_path, dump_bytes(fixture_manifest))

        report = RuleGoldenReport(
            rule_id=rule_id,
            rule_version="1.0.0",
            candidate_path=_relative(root, candidate_path),
            candidate_sha256=candidate_hash,
            approved_rule_path=_relative(root, approved_path),
            approved_rule_sha256=approved_hash,
            runner_version="1",
            source_commit="c" * 40,
            command="python -m ansim_review rules run-golden",
            fixture_manifest_path=_relative(root, fixture_manifest_path),
            fixture_manifest_sha256=_sha256(fixture_manifest_path),
            case_count=1,
            passed_count=1,
            failed_count=0,
            status="PASS",
            cases=(
                GoldenCaseRecord(
                    case_id=case_id,
                    fixture_path=_relative(root, fixture_path),
                    fixture_sha256=_sha256(fixture_path),
                    expected_path=_relative(root, expected_path),
                    expected_sha256=_sha256(expected_path),
                    actual_path=_relative(root, actual_path),
                    actual_sha256=_sha256(actual_path),
                    status="PASS",
                ),
            ),
        )
        _write(report_path, rule_golden_report_bytes(report))

        scope = RuleScope(document_family="ANSIM")
        approval = RuleActivationApproval(
            rule_id=rule_id,
            rule_version="1.0.0",
            candidate_path=_relative(root, candidate_path),
            candidate_sha256=candidate_hash,
            approved_rule_path=_relative(root, approved_path),
            approved_rule_sha256=approved_hash,
            golden_report_path=_relative(root, report_path),
            golden_report_sha256=_sha256(report_path),
            scope=scope,
            reviewer_id="fixture-reviewer",
            reviewed_at="2026-08-02T21:52:00+09:00",
            decision="APPROVED",
            reason="Deterministic test golden evidence reviewed.",
        )
        _write(approval_path, rule_activation_approval_bytes(approval))

        entries.append(
            ActiveRuleEntry(
                rule_id=rule_id,
                rule_version="1.0.0",
                candidate_path=approval.candidate_path,
                candidate_sha256=approval.candidate_sha256,
                approved_rule_path=approval.approved_rule_path,
                approved_rule_sha256=approval.approved_rule_sha256,
                golden_report_path=approval.golden_report_path,
                golden_report_sha256=approval.golden_report_sha256,
                approval_path=_relative(root, approval_path),
                approval_sha256=_sha256(approval_path),
                scope=scope,
                reviewer_id=approval.reviewer_id,
                reviewed_at=approval.reviewed_at,
                reason=approval.reason,
            )
        )
        candidate_paths.append(candidate_path)
        approved_paths.append(approved_path)
        fixture_manifest_paths.append(fixture_manifest_path)
        fixture_paths.append(fixture_path)
        expected_paths.append(expected_path)
        actual_paths.append(actual_path)
        report_paths.append(report_path)
        approval_paths.append(approval_path)

    manifest_path = root / "rules" / "manifests" / "active.json"
    _write(
        manifest_path,
        active_rule_manifest_bytes(ActiveRuleManifest(rules=tuple(entries))),
    )
    return GovernanceTree(
        root=root,
        manifest_path=manifest_path,
        approval_paths=tuple(approval_paths),
        golden_report_paths=tuple(report_paths),
        candidate_paths=tuple(candidate_paths),
        approved_rule_paths=tuple(approved_paths),
        fixture_manifest_paths=tuple(fixture_manifest_paths),
        fixture_paths=tuple(fixture_paths),
        expected_paths=tuple(expected_paths),
        actual_paths=tuple(actual_paths),
    )


def _load_json(path: Path) -> dict[str, object]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise AssertionError(f"expected object fixture: {path}")
    return value


def _rewrite(path: Path, payload: dict[str, object]) -> None:
    path.write_bytes(dump_bytes(payload))


def _active_manifest_bytes(tree: GovernanceTree) -> None:
    payload = _load_json(tree.manifest_path)
    payload["format"] = "invalid/active-rule-manifest"
    _rewrite(tree.manifest_path, payload)


def _approval_bytes(tree: GovernanceTree) -> None:
    payload = _load_json(tree.approval_paths[0])
    payload["reviewer_id"] = "tampered-reviewer"
    _rewrite(tree.approval_paths[0], payload)


def _golden_report_bytes(tree: GovernanceTree) -> None:
    payload = _load_json(tree.golden_report_paths[0])
    payload["command"] = "tampered command"
    _rewrite(tree.golden_report_paths[0], payload)


def _append_space(path: Path) -> None:
    path.write_bytes(path.read_bytes() + b" ")


def _candidate_bytes(tree: GovernanceTree) -> None:
    _append_space(tree.candidate_paths[0])


def _approved_rule_bytes(tree: GovernanceTree) -> None:
    _append_space(tree.approved_rule_paths[0])


def _fixture_manifest_bytes(tree: GovernanceTree) -> None:
    _append_space(tree.fixture_manifest_paths[0])


def _fixture_bytes(tree: GovernanceTree) -> None:
    _append_space(tree.fixture_paths[0])


def _expected_bytes(tree: GovernanceTree) -> None:
    _append_space(tree.expected_paths[0])


def _path_traversal(tree: GovernanceTree) -> None:
    payload = _load_json(tree.approval_paths[0])
    payload["candidate_path"] = "../outside.json"
    _rewrite(tree.approval_paths[0], payload)


def _duplicate_rule_id(tree: GovernanceTree) -> None:
    if len(tree.approval_paths) < 2:
        raise ValueError("duplicate_rule_id mutation requires at least two rules")
    payload = _load_json(tree.manifest_path)
    rules = payload.get("rules")
    if not isinstance(rules, list) or len(rules) < 2:
        raise AssertionError("manifest does not contain two rules")
    first = rules[0]
    second = rules[1]
    if not isinstance(first, dict) or not isinstance(second, dict):
        raise AssertionError("manifest rule entry must be an object")
    second["rule_id"] = first["rule_id"]
    _rewrite(tree.manifest_path, payload)


_MUTATIONS = {
    "active_manifest_bytes": _active_manifest_bytes,
    "approval_bytes": _approval_bytes,
    "golden_report_bytes": _golden_report_bytes,
    "candidate_bytes": _candidate_bytes,
    "approved_rule_bytes": _approved_rule_bytes,
    "fixture_manifest_bytes": _fixture_manifest_bytes,
    "fixture_bytes": _fixture_bytes,
    "expected_bytes": _expected_bytes,
    "path_traversal": _path_traversal,
    "duplicate_rule_id": _duplicate_rule_id,
}


def apply_governance_mutation(tree: GovernanceTree, mutation: str) -> None:
    """Apply one exact mutation to a valid governance tree."""
    try:
        mutate = _MUTATIONS[mutation]
    except KeyError as error:
        raise ValueError(f"unsupported governance mutation: {mutation}") from error
    mutate(tree)
