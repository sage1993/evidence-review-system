import json
from pathlib import Path

from ansim_review.canonical_json import dump_bytes
from ansim_review.golden_cases import run_golden_case


def test_ansim_golden_cases_match_outputs_and_are_byte_reproducible() -> None:
    root = Path(__file__).parents[2]
    cases = json.loads(
        (root / "golden/questions/ansim_cases.json").read_text(encoding="utf-8")
    )
    first = [run_golden_case(case) for case in cases]
    second = [run_golden_case(case) for case in cases]
    assert dump_bytes(first) == dump_bytes(second)
    assert len(first) == 10
    for case, result in zip(cases, first, strict=True):
        expected = case["expected"]
        assert result["final_status"] == expected["final_status"]
        assert result["abstention_reasons"] == expected["abstention_reasons"]
        assert result["human_decision"] is None
        if "comparison" in expected:
            calculation = result["calculation"]
            assert isinstance(calculation, dict)
            assert calculation["comparison"] == expected["comparison"]
