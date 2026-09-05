from __future__ import annotations

import json
from pathlib import Path

SCHEMAS = Path(__file__).parents[3] / "schemas"
EXPECTED = {
    "confirmed-input.schema.json",
    "drawing-candidate.schema.json",
    "drawing-confirmation.schema.json",
    "drawing-geometry.schema.json",
    "human-attestation.schema.json",
    "immutable-attachment.schema.json",
    "next-action.schema.json",
    "parser-reproducibility-config.schema.json",
    "parser-reproducibility-report.schema.json",
    "parser-review-queue.schema.json",
    "parser-run-manifest.schema.json",
    "parser-run-metadata.schema.json",
    "parser-warning-report.schema.json",
    "reason-code.schema.json",
    "reference-ingestion-receipt.schema.json",
    "review-packet-v2.schema.json",
    "review-request.schema.json",
    "source-batch.schema.json",
    "source-batch-v2.schema.json",
    "visual-manifest.schema.json",
    "workflow-event.schema.json",
    "workflow-state.schema.json",
}


def test_shared_contract_schemas_are_valid_versioned_json_documents() -> None:
    for name in sorted(EXPECTED):
        document = json.loads((SCHEMAS / name).read_text(encoding="utf-8"))
        assert document["$schema"] == "https://json-schema.org/draft/2020-12/schema"
        assert document["$id"].endswith(f"/schemas/{name}")
        assert isinstance(document["title"], str) and document["title"]


def test_object_contract_schemas_reject_additional_properties() -> None:
    excluded = {"reason-code.schema.json", "drawing-geometry.schema.json"}
    for name in sorted(EXPECTED - excluded):
        document = json.loads((SCHEMAS / name).read_text(encoding="utf-8"))
        assert document["type"] == "object"
        assert document["additionalProperties"] is False


def test_review_packet_v2_claim_schema_requires_unique_issue_lineage() -> None:
    document = json.loads(
        (SCHEMAS / "review-packet-v2.schema.json").read_text(encoding="utf-8")
    )
    claim_schema = document["properties"]["claims"]["items"]

    assert "issue_ids" in claim_schema["required"]
    issue_ids = claim_schema["properties"]["issue_ids"]
    assert issue_ids["type"] == "array"
    assert issue_ids["uniqueItems"] is True
    assert issue_ids["items"] == {"type": "string", "minLength": 1}
