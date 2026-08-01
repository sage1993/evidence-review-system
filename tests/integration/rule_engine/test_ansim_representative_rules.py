import json
from dataclasses import asdict, replace
from pathlib import Path

from ansim_review.canonical_json import dump_bytes, sha256_json
from ansim_review.contracts.engines import CalculationResult
from ansim_review.contracts.evidence import EvidenceRecord
from ansim_review.math_engine.manifest import calculation_result_payload
from ansim_review.rule_engine.evaluator import evaluate_rule
from ansim_review.rule_engine.manifest import load_active_rules

ROOT = Path(__file__).parents[3]
MANIFEST = ROOT / "rules" / "manifests" / "active.json"
GOLDEN = ROOT / "tests" / "golden" / "rules" / "ansim_representative_cases.json"
FORMULA_MANIFEST_HASH = "b" * 64


def _frontage_calculation() -> CalculationResult:
    result = CalculationResult(
        calculation_result_id="CALC-FRONTAGE-30-320",
        status="SUCCESS",
        formula_id="FRONTAGE_RATIO",
        formula_version="1.0.0",
        inputs={
            "frontage_length_m": "30",
            "perimeter_length_m": "320",
            "threshold_ratio": "0.125",
        },
        substitution="30 / 320",
        raw_result="0.09375",
        display_result="9.375%",
        comparison="BELOW_THRESHOLD",
        formula_manifest_hash=FORMULA_MANIFEST_HASH,
    )
    return replace(result, result_hash=sha256_json(calculation_result_payload(result)))


def _evidence(rule):
    return [
        EvidenceRecord(
            evidence_id=citation.evidence_id,
            document_id=citation.document_id,
            revision_id=citation.revision_id,
            page_number=citation.page_number,
            element_id=f"EL-{index + 1}",
            evidence_type="text",
            bbox=citation.bbox,
            source_hash=citation.source_hash,
        )
        for index, citation in enumerate(rule.source_citations)
    ]


def _execute_cases() -> tuple[bytes, ...]:
    rules = {rule.rule_id: rule for rule in load_active_rules(ROOT, MANIFEST)}
    payload = json.loads(GOLDEN.read_text(encoding="utf-8"))
    outputs: list[bytes] = []
    for case in payload["cases"]:
        rule = rules[case["rule_id"]]
        calculations = []
        expected_manifest = None
        if case.get("calculation_fixture") == "frontage_30_320":
            calculations = [_frontage_calculation()]
            expected_manifest = FORMULA_MANIFEST_HASH
        result = evaluate_rule(
            rule,
            case["inputs"],
            calculations=calculations,
            expected_formula_manifest_hash=expected_manifest,
            evidence_records=_evidence(rule),
        )
        assert result.status == case["expected_status"]
        assert list(result.missing_inputs) == case["expected_missing_inputs"]
        outputs.append(dump_bytes(asdict(result)))
    return tuple(outputs)


def test_ansim_representative_cases_are_byte_reproducible() -> None:
    assert _execute_cases() == _execute_cases()
