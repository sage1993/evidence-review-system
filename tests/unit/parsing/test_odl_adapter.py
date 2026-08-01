from pathlib import Path

from ansim_review.canonical_json import sha256_json
from ansim_review.parsing.odl_adapter import load_raw_elements


def test_load_raw_elements_assigns_stable_page_ordered_ids() -> None:
    fixture = Path("tests/golden/fixtures/minimal-parser-output.json")

    first = load_raw_elements(fixture, document_id="LAW1", revision_id="LAW1-abc123")
    second = load_raw_elements(fixture, document_id="LAW1", revision_id="LAW1-abc123")

    assert first == second
    assert [item.page_number for item in first] == [1, 1, 2]
    assert [item.element_id for item in first] == [
        "LAW1-LAW1-abc123-P0001-E00001",
        "LAW1-LAW1-abc123-P0001-E00002",
        "LAW1-LAW1-abc123-P0002-E00001",
    ]
    assert [item.parser_order for item in first] == [1, 2, 0]
    assert [item.element_type for item in first] == ["list", "list item", "paragraph"]
    assert first[1].raw_payload_hash == sha256_json(first[1].raw_payload)
    assert first[1].source_path == ("kids", 1, "list items", 0)
