from __future__ import annotations

import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

SCHEMA_PATH = Path(__file__).parents[3] / "schemas" / "immutable-attachment.schema.json"


def _schema() -> Draft202012Validator:
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    return Draft202012Validator(schema)


def _attachment(**overrides: object) -> dict[str, object]:
    value: dict[str, object] = {
        "attachment_id": "ATT-1",
        "original_name": "plan.pdf",
        "stored_path": "inputs/original/plan.pdf",
        "sha256": "a" * 64,
        "byte_size": 1,
        "mime": "application/pdf",
        "role": "REFERENCE_DOCUMENT",
    }
    value.update(overrides)
    return value


def test_attachment_schema_accepts_legacy_reference_storage() -> None:
    assert not list(_schema().iter_errors(_attachment()))


def test_attachment_schema_accepts_case_visual_storage() -> None:
    value = _attachment(
        case_id="CASE-1",
        stored_path="cases/CASE-1/sources/drawings/ATT-1.pdf",
        role="CASE_DRAWING",
    )

    assert not list(_schema().iter_errors(value))


@pytest.mark.parametrize(
    "overrides",
    [
        {"stored_path": "cases/CASE-1/sources/drawings/ATT-1.pdf"},
        {
            "case_id": "CASE-1",
            "stored_path": "cases/CASE-1/sources/drawings/ATT-1.pdf",
            "role": "REFERENCE_DOCUMENT",
        },
        {"case_id": "CASE-1"},
        {"stored_path": "inputs/original/plan.pdf", "role": "CASE_DRAWING"},
    ],
)
def test_attachment_schema_rejects_mixed_case_and_legacy_bindings(
    overrides: dict[str, object],
) -> None:
    assert list(_schema().iter_errors(_attachment(**overrides)))
