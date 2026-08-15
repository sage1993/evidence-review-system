from __future__ import annotations

import json
from pathlib import Path

import pytest

from evidence_review.contracts.evidence import EvidenceRecord
from evidence_review.rule_engine.evaluator import evaluate_rule
from evidence_review.rule_engine.loader import load_rule

ROOT = Path(__file__).parents[3]
CANDIDATE_ROOT = ROOT / "tests" / "fixtures" / "ansim" / "rules" / "candidates"

CASES = (
    (
        "ANSIM-ZONING-CHANGE-FAR-MAX-400@1.0.0.json",
        "planned_floor_area_ratio_percent",
        "400",
        "401",
    ),
    (
        "ANSIM-ZONING-CHANGE-PUBLIC-CONTRIBUTION-MIN-15@1.0.0.json",
        "planned_public_contribution_percent",
        "15",
        "14.9999",
    ),
    (
        "ANSIM-ZONING-CHANGE-RESIDENTIAL-RATIO-MIN-85@1.0.0.json",
        "planned_residential_ratio_percent",
        "85",
        "84.9999",
    ),
)


def _load_candidate(filename: str):
    payload = json.loads((CANDIDATE_ROOT / filename).read_text(encoding="utf-8"))
    return load_rule(payload)


def _evidence_records(rule) -> tuple[EvidenceRecord, ...]:
    return tuple(
        EvidenceRecord(
            evidence_id=citation.evidence_id,
            document_id=citation.document_id,
            revision_id=citation.revision_id,
            page_number=citation.page_number,
            element_id=citation.evidence_id,
            evidence_type="clause",
            bbox=citation.bbox,
            source_hash=citation.source_hash,
            raw_text="source-backed candidate fixture",
            normalized_text="source-backed candidate fixture",
        )
        for citation in rule.source_citations
    )


@pytest.mark.parametrize(("filename", "value_key", "boundary", "failure"), CASES)
def test_zoning_change_candidates_enforce_scope_and_boundary(
    filename: str,
    value_key: str,
    boundary: str,
    failure: str,
) -> None:
    rule = _load_candidate(filename)
    evidence_records = _evidence_records(rule)
    base_inputs = {
        "current_zoning": "제2종일반주거지역",
        "proposed_zoning": "준주거지역",
        value_key: boundary,
    }

    satisfied = evaluate_rule(rule, base_inputs, evidence_records=evidence_records)
    assert satisfied.status == "SATISFIED"
    assert satisfied.reason_codes == ("EVALUATED_TRUE",)

    failed = evaluate_rule(
        rule,
        {**base_inputs, value_key: failure},
        evidence_records=evidence_records,
    )
    assert failed.status == "NOT_SATISFIED"
    assert failed.reason_codes == ("EVALUATED_FALSE",)

    wrong_scope = evaluate_rule(
        rule,
        {**base_inputs, "proposed_zoning": "근린상업지역"},
        evidence_records=evidence_records,
    )
    assert wrong_scope.status == "NOT_SATISFIED"
