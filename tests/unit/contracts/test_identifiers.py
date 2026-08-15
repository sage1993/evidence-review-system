from pathlib import Path

import pytest

from evidence_review.contracts.identifiers import (
    safe_direct_child,
    validate_identifier,
    validate_version,
)


def test_identifier_accepts_stable_machine_id() -> None:
    assert validate_identifier("BUILDING-HEIGHT.001", "rule_id") == "BUILDING-HEIGHT.001"


@pytest.mark.parametrize(
    "value",
    ["../RULE", "/tmp/RULE", "C:\\tmp\\RULE", "RULE/CHILD", "RULE\\CHILD", ""],
)
def test_identifier_rejects_path_syntax(value: str) -> None:
    with pytest.raises(ValueError):
        validate_identifier(value, "rule_id")


def test_version_requires_semantic_version() -> None:
    assert validate_version("1.2.3", "version") == "1.2.3"
    assert validate_version("1.2.3-rc.1", "version") == "1.2.3-rc.1"
    with pytest.raises(ValueError):
        validate_version("../1", "version")


def test_safe_direct_child_stays_directly_below_root(tmp_path: Path) -> None:
    child = safe_direct_child(tmp_path, "RULE@1.0.0.json", "approved_path")
    assert child == tmp_path.resolve() / "RULE@1.0.0.json"


@pytest.mark.parametrize("filename", ["../RULE.json", "sub/RULE.json", "C:\\RULE.json"])
def test_safe_direct_child_rejects_escape(tmp_path: Path, filename: str) -> None:
    with pytest.raises(ValueError):
        safe_direct_child(tmp_path, filename, "approved_path")
