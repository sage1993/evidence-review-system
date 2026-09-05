from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from evidence_review.abstention import finalizer as finalizer_module
from evidence_review.abstention.finalizer import finalize_run
from evidence_review.abstention.verified_artifacts import verify_run_snapshot
from evidence_review.canonical_json import dump_bytes
from evidence_review.confidence.policy import FACTOR_WEIGHTS
from evidence_review.contracts.codecs import decode_review_packet
from evidence_review.contracts.common import BBox, Citation
from evidence_review.contracts.engines import CalculationResult, RuleResult
from evidence_review.contracts.review import IssueResult
from evidence_review.llm_layer.track_a import (
    EvidenceExcerpt,
    build_track_a_bundle,
    track_a_bundle_document,
)

RUN_ID = "RUN-0123456789ABCDEF0123"


def _write_run(
    tmp_path: Path,
    disposition: str = "ACCEPT",
    *,
    snapshot_hash: str | None = None,
    missing_inputs: tuple[str, ...] = (),
    rule_missing_inputs: tuple[str, ...] = (),
    issue_results: tuple[IssueResult, ...] = (),
) -> Path:
    run_dir = tmp_path / RUN_ID
    run_dir.mkdir(parents=True)
    citation = Citation(
        "C1", "DOC1", "REV1", 1, "E1", BBox(0, 0, 10, 10), "a" * 64
    )
    calculation = CalculationResult(
        "CALC1",
        "SUCCESS",
        "F1",
        "1.0.0",
        display_result="9.375%",
        result_hash="b" * 64,
    )
    rule = RuleResult(
        "RULE1",
        "R1",
        "1.0.0",
        "SATISFIED",
        citations=(citation,),
        missing_inputs=rule_missing_inputs,
        calculation_result_ids=("CALC1",),
        result_hash="c" * 64,
    )
    inputs = {"frontage": "30", "perimeter": "320"}
    if issue_results:
        inputs["issue_coverage"] = [
            {
                "issue_id": item.issue_id,
                "status": item.status,
                "evidence_ids": list(item.evidence_ids),
                "covered_roles": list(item.covered_roles),
                "missing_roles": list(item.missing_roles),
                "gap_codes": list(item.gap_codes),
            }
            for item in issue_results
        ]
    if snapshot_hash is not None:
        inputs["snapshot_hash"] = snapshot_hash
    bundle = build_track_a_bundle(
        run_id=RUN_ID,
        question="접면 기준 충족 여부",
        inputs=inputs,
        evidence=(
            EvidenceExcerpt(
                citation,
                "접면 비율은 9.375%이다.",
                issue_ids=("I1",) if issue_results else (),
                role="rule" if issue_results else None,
            ),
        ),
        rules=(rule,),
        calculations=(calculation,),
        approved_rule_result_ids=("RULE1",),
    )
    track_a = {
        "run_id": RUN_ID,
        "claims": [{
            "claim_id": "CL1",
            "text": "접면 비율은 9.375%이다.",
            "citation_ids": ["C1"],
            "numeric_tokens": ["9.375%"],
            "issue_ids": ["I1"] if issue_results else [],
            "calculation_result_ids": ["CALC1"],
            "rule_references": [
                {
                    "rule_result_id": "RULE1",
                    "result_hash": "c" * 64,
                    "status": "SATISFIED",
                }
            ],
        }],
        "citations": ["C1"],
        "missing_inputs": list(missing_inputs),
        "exceptions": [],
        "conflicts": [],
        "explanation": "근거를 정리한다.",
    }
    findings = [] if disposition == "ACCEPT" else ["UNSUPPORTED_CLAIM"]
    track_b = {
        "run_id": RUN_ID,
        "claim_audits": [
            {
                "claim_id": "CL1",
                "disposition": disposition,
                "finding_codes": findings,
                "notes": "",
            }
        ],
        "overall_disposition": disposition,
    }
    confidence = {
        "factors": {
            name: {"value": "1.0", "source": f"metric:{name}"}
            for name in FACTOR_WEIGHTS
        }
    }
    artifacts = {
        "track-a-bundle.json": track_a_bundle_document(bundle),
        "track-a-output.json": track_a,
        "track-b-output.json": track_b,
        "confidence-input.json": confidence,
    }
    hashes = {}
    for name, document in artifacts.items():
        data = dump_bytes(document)
        (run_dir / name).write_bytes(data)
        hashes[name] = hashlib.sha256(data).hexdigest()
    (run_dir / "run-manifest.json").write_bytes(
        dump_bytes({"run_id": RUN_ID, "artifacts": hashes})
    )
    return run_dir


def _mixed_issue_results() -> tuple[IssueResult, ...]:
    return (
        IssueResult(
            "I1",
            "RESOLVED",
            evidence_ids=("E1",),
            covered_roles=("rule",),
        ),
        IssueResult(
            "I2",
            "SOURCE_MISSING",
            missing_roles=("rule",),
            gap_codes=("SOURCE_NOT_INGESTED",),
        ),
    )


def test_complete_run_yields_ready_packet_without_human_decision(tmp_path: Path) -> None:
    run_dir = _write_run(tmp_path)
    packet = finalize_run(run_dir)
    assert packet.status == "READY_FOR_HUMAN_REVIEW"
    assert packet.human_decision is None
    assert packet.confidence is not None and packet.confidence.level == "HIGH"
    output = json.loads(
        (run_dir / "final-review-packet.json").read_text(encoding="utf-8")
    )
    assert output["human_decision"] is None


def test_final_packet_preserves_snapshot_and_missing_input_lineage(tmp_path: Path) -> None:
    run_dir = _write_run(
        tmp_path,
        snapshot_hash="d" * 64,
        missing_inputs=("청소년문화의집 적용대상 확인",),
    )

    packet = finalize_run(run_dir)

    assert packet.snapshot_sha256 == "d" * 64
    assert packet.missing_inputs == ("청소년문화의집 적용대상 확인",)
    assert "MISSING_REQUIRED_INPUT" in packet.abstention_reasons
    output = json.loads(
        (run_dir / "final-review-packet.json").read_text(encoding="utf-8")
    )
    assert output["snapshot_sha256"] == "d" * 64
    assert output["missing_inputs"] == ["청소년문화의집 적용대상 확인"]


def test_partial_issue_coverage_yields_partial_status_and_preserves_issue_results(
    tmp_path: Path,
) -> None:
    packet = finalize_run(
        _write_run(
            tmp_path,
            issue_results=_mixed_issue_results(),
        )
    )

    assert packet.status == "PARTIALLY_RESOLVED"
    assert packet.human_decision is None
    assert packet.claims[0].issue_ids == ("I1",)
    assert [item.status for item in packet.issue_results] == [
        "RESOLVED",
        "SOURCE_MISSING",
    ]
    assert packet.issue_results[1].gap_codes == ("SOURCE_NOT_INGESTED",)
    document = json.loads(
        (tmp_path / RUN_ID / "final-review-packet.json").read_text(encoding="utf-8")
    )
    assert document["status"] == "PARTIALLY_RESOLVED"
    assert document["issue_results"][1]["issue_id"] == "I2"


def test_partial_issue_coverage_does_not_preserve_track_b_unsupported_resolved_claim(
    tmp_path: Path,
) -> None:
    packet = finalize_run(
        _write_run(
            tmp_path,
            disposition="INCOMPLETE",
            issue_results=_mixed_issue_results(),
        )
    )

    by_issue = {item.issue_id: item for item in packet.issue_results}
    assert by_issue["I1"].status == "UNRESOLVED"
    assert by_issue["I2"].status == "SOURCE_MISSING"
    assert packet.status == "ABSTAIN"
    assert "UNCITED_OR_UNRESOLVED_CLAIM" in packet.abstention_reasons


def test_partial_issue_coverage_does_not_suppress_rule_missing_input_hard_gate(
    tmp_path: Path,
) -> None:
    packet = finalize_run(
        _write_run(
            tmp_path,
            rule_missing_inputs=("법정 필수 입력",),
            issue_results=_mixed_issue_results(),
        )
    )

    assert packet.status == "ABSTAIN"
    assert packet.missing_inputs == ("법정 필수 입력",)
    assert "MISSING_REQUIRED_INPUT" in packet.abstention_reasons


def test_legacy_packet_decode_defaults_lineage_fields(tmp_path: Path) -> None:
    run_dir = _write_run(tmp_path)
    finalize_run(run_dir)
    document = json.loads(
        (run_dir / "final-review-packet.json").read_text(encoding="utf-8")
    )
    document.pop("snapshot_sha256", None)
    document.pop("missing_inputs", None)

    packet = decode_review_packet(document)

    assert packet.snapshot_sha256 is None
    assert packet.missing_inputs == ()


def test_review_packet_rejects_invalid_snapshot_sha256(tmp_path: Path) -> None:
    run_dir = _write_run(tmp_path)
    finalize_run(run_dir)
    document = json.loads(
        (run_dir / "final-review-packet.json").read_text(encoding="utf-8")
    )
    document["snapshot_sha256"] = "NOT-A-SHA256"
    document["missing_inputs"] = []

    with pytest.raises(
        ValueError,
        match="snapshot_sha256 must be a lowercase SHA-256 digest",
    ):
        decode_review_packet(document)


def test_track_b_rejection_yields_abstain(tmp_path: Path) -> None:
    packet = finalize_run(_write_run(tmp_path, disposition="REJECT"))
    assert packet.status == "ABSTAIN"
    assert "TRACK_B_REJECTION" in packet.abstention_reasons
    assert packet.human_decision is None


def test_finalizer_refuses_overwrite_and_tampered_artifacts(tmp_path: Path) -> None:
    run_dir = _write_run(tmp_path)
    finalize_run(run_dir)
    with pytest.raises(FileExistsError):
        finalize_run(run_dir)

    tampered_dir = _write_run(tmp_path / "other")
    (tampered_dir / "track-a-output.json").write_text("{}", encoding="utf-8")
    with pytest.raises(ValueError, match="artifact hash mismatch"):
        finalize_run(tampered_dir)
    assert not (tampered_dir / "final-review-packet.json").exists()


def test_verified_snapshot_remains_authority_after_artifact_path_mutation(
    tmp_path: Path,
) -> None:
    run_dir = _write_run(tmp_path)
    snapshot = verify_run_snapshot(
        run_dir,
        required_artifacts=finalizer_module._REQUIRED_ARTIFACTS,
    )
    helper = getattr(finalizer_module, "expected_final_review_packet_from_snapshot", None)
    assert helper is not None, "snapshot-only finalizer derivation helper is missing"

    track_a_path = run_dir / "track-a-output.json"
    mutated = json.loads(track_a_path.read_text(encoding="utf-8"))
    mutated["missing_inputs"] = ["MUTATED AFTER VERIFICATION"]
    track_a_path.write_bytes(dump_bytes(mutated))

    packet = helper(snapshot)

    assert packet.missing_inputs == ()
    assert packet.status == "READY_FOR_HUMAN_REVIEW"
    with pytest.raises(ValueError, match="artifact hash mismatch: track-a-output.json"):
        verify_run_snapshot(
            run_dir,
            required_artifacts=finalizer_module._REQUIRED_ARTIFACTS,
        )
