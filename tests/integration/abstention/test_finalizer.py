from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from ansim_review.abstention.finalizer import finalize_run
from ansim_review.canonical_json import dump_bytes
from ansim_review.confidence.policy import FACTOR_WEIGHTS
from ansim_review.contracts.common import BBox, Citation
from ansim_review.contracts.engines import CalculationResult, RuleResult
from ansim_review.llm_layer.track_a import (
    EvidenceExcerpt,
    build_track_a_bundle,
    track_a_bundle_document,
)

RUN_ID = "RUN-0123456789ABCDEF0123"


def _write_run(tmp_path: Path, disposition: str = "ACCEPT") -> Path:
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
        calculation_result_ids=("CALC1",),
        result_hash="c" * 64,
    )
    bundle = build_track_a_bundle(
        run_id=RUN_ID,
        question="접면 기준 충족 여부",
        inputs={"frontage": "30", "perimeter": "320"},
        evidence=(EvidenceExcerpt(citation, "접면 비율은 9.375%이다."),),
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
        "missing_inputs": [],
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


def test_complete_run_yields_ready_packet_without_human_decision(tmp_path: Path) -> None:
    run_dir = _write_run(tmp_path)
    packet = finalize_run(run_dir)
    assert packet.status == "READY_FOR_HUMAN_REVIEW"
    assert packet.human_decision is None
    assert packet.confidence is not None and packet.confidence.level == "HIGH"
    output = json.loads((run_dir / "final-review-packet.json").read_text())
    assert output["human_decision"] is None


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
