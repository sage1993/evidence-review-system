import pytest

from evidence_review.rule_engine.loader import load_rule


def _base_rule() -> dict[str, object]:
    return {
        "rule_id": "RULE-TEST",
        "version": "1.0.0",
        "title": "테스트 규칙",
        "input_schema": {"site_area_m2": {"type": "decimal", "required": True}},
        "source_citations": [
            {
                "citation_id": "C-1",
                "document_id": "LAW1",
                "revision_id": "REV-1",
                "page_number": 1,
                "evidence_id": "E-1",
                "bbox": [0, 0, 10, 10],
                "source_hash": "a" * 64,
            }
        ],
        "human_decision_required": True,
        "expression": {"exists": {"input": "site_area_m2"}},
    }


def test_loader_rejects_python_node() -> None:
    payload = _base_rule()
    payload["expression"] = {"python": "__import__('os')"}
    with pytest.raises(ValueError, match="unsupported rule node"):
        load_rule(payload)


def test_loader_requires_human_decision_and_source_identity() -> None:
    payload = _base_rule()
    payload["human_decision_required"] = False
    with pytest.raises(ValueError, match="human_decision_required"):
        load_rule(payload)


@pytest.mark.parametrize(
    "rule_id",
    ["../RULE", "/tmp/RULE", "C:\\tmp\\RULE", "RULE/CHILD", "RULE\\CHILD"],
)
def test_loader_rejects_rule_ids_with_path_syntax(rule_id: str) -> None:
    payload = _base_rule()
    payload["rule_id"] = rule_id
    with pytest.raises(ValueError, match="rule_id"):
        load_rule(payload)


def test_loader_rejects_undeclared_input_reference() -> None:
    payload = _base_rule()
    payload["expression"] = {"exists": {"input": "road_width_m"}}
    with pytest.raises(ValueError, match="undeclared input reference: road_width_m"):
        load_rule(payload)
