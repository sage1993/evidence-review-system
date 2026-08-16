from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from evidence_review.contracts.question_plan import decode_question_plan
from evidence_review.evidence.ingest import EvidenceSnapshot, ingest_snapshot
from evidence_review.evidence.store import EvidenceStore
from evidence_review.planned_review_question import prepare_planned_review_question
from evidence_review.retrieval.index import build_fts_index

_FIXTURE_DIR = (
    Path(__file__).parents[2] / "fixtures" / "real_review_retrieval_relevance"
)


def _load_json(name: str) -> dict[str, Any]:
    value = json.loads((_FIXTURE_DIR / name).read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def _element(record: dict[str, Any], parser_order: int) -> dict[str, object]:
    text = str(record["text"])
    evidence_id = str(record["evidence_id"])
    return {
        "id": evidence_id,
        "revision_id": "REV-ISSUE-116",
        "page_id": "REV-ISSUE-116-P1",
        "page_number": 1,
        "element_type": "paragraph",
        "raw_json": {"text": text},
        "raw_text": text,
        "normalized_text": text,
        "raw_payload_hash": format(parser_order % 16, "x") * 64,
        "bbox": [
            10.0,
            float(parser_order * 10),
            500.0,
            float(parser_order * 10 + 8),
        ],
        "parser_order": parser_order,
    }


def _snapshot(fixture: dict[str, Any]) -> EvidenceSnapshot:
    required = list(fixture["required"])
    forbidden = list(fixture["forbidden"])
    distractors = list(fixture["distractors"])
    records = [*required, *forbidden, *distractors]
    return EvidenceSnapshot(
        documents=({"id": "DOC-ISSUE-116", "title": "안심주택 회귀 자료"},),
        revisions=(
            {
                "id": "REV-ISSUE-116",
                "document_id": "DOC-ISSUE-116",
                "source_hash": "a" * 64,
                "byte_size": 4096,
                "page_count": 1,
            },
        ),
        pages=(
            {
                "id": "REV-ISSUE-116-P1",
                "revision_id": "REV-ISSUE-116",
                "page_number": 1,
                "width": 595.0,
                "height": 842.0,
            },
        ),
        elements=tuple(
            _element(record, index)
            for index, record in enumerate(records, start=1)
        ),
        clauses=tuple(
            {
                "id": str(record["clause_id"]),
                "revision_id": "REV-ISSUE-116",
                "title": str(record["title"]),
                "raw_text": str(record["text"]),
                "normalized_text": str(record["text"]),
                "review_status": "AUTOMATIC",
            }
            for record in required
        ),
        links=tuple(
            {
                "id": f"L-{record['clause_id']}-{record['evidence_id']}",
                "source_id": str(record["clause_id"]),
                "target_id": str(record["evidence_id"]),
                "relation_type": "source_element",
            }
            for record in required
        ),
    )


def _prepare(tmp_path: Path) -> tuple[dict[str, Any], Path]:
    plan_payload = _load_json("question-plan.json")
    fixture = _load_json("expected-evidence.json")
    original_question = plan_payload["original_question"]
    assert isinstance(original_question, str)
    plan = decode_question_plan(plan_payload, original_question)
    workspace = tmp_path / "workspace"
    (workspace / "evidence").mkdir(parents=True)
    with EvidenceStore(
        workspace / "evidence" / "evidence.sqlite",
        create=True,
    ) as store:
        ingest_snapshot(store, _snapshot(fixture))
        build_fts_index(store.require_connection())
    prepared = prepare_planned_review_question(workspace, plan)
    assert prepared.status == "WAITING_TRACK_A"
    return fixture, workspace / "runs" / prepared.run_id


def test_issue_116_prepare_binds_facets_comparisons_and_snapshot_provenance(
    tmp_path: Path,
) -> None:
    fixture, run_directory = _prepare(tmp_path)
    bundle = json.loads(
        (run_directory / "track-a-bundle.json").read_text(encoding="utf-8")
    )
    trace = json.loads(
        (run_directory / "retrieval-trace.json").read_text(encoding="utf-8")
    )
    compiled_plan = json.loads(
        (run_directory / "question-plan.json").read_text(encoding="utf-8")
    )

    inputs = bundle["inputs"]
    provenance = inputs["evidence_snapshot_provenance"]
    assert provenance["evidence_snapshot_hash"] == inputs["snapshot_hash"]
    assert len(provenance["evidence_db_sha256"]) == 64
    assert provenance["schema_version"] >= 4
    assert provenance["retrieval_record_count"] > 0
    assert provenance["clause_record_count"] >= 7
    assert trace["snapshot_provenance"] == provenance

    i2_searches = [
        item
        for item in compiled_plan["search_requests"]
        if "I2" in item["issue_ids"]
    ]
    assert [item["id"] for item in i2_searches] == [
        "S2",
        "FACET-I2-minimum-area-threshold",
    ]

    coverage = {item["issue_id"]: item for item in inputs["issue_coverage"]}
    assert coverage["I2"]["status"] == "CONDITIONAL"
    assert all(
        coverage[f"I{index}"]["status"] == "RESOLVED"
        for index in (1, 3, 4, 5, 6, 7)
    )

    facets = {item["issue_id"]: item for item in inputs["facet_coverage"]}
    assert all(
        not facets[f"I{index}"]["missing_facet_ids"]
        for index in range(1, 8)
    )
    assert facets["I2"]["covered_facet_ids"] == [
        "minimum-area-threshold",
        "distance-normal-threshold",
        "distance-conditional-threshold",
    ]
    assert set(facets["I4"]["covered_facet_ids"]) == {
        "dormitory-parking-standard",
        "mixed-use-parking-application",
    }
    assert set(facets["I6"]["covered_facet_ids"]) == {
        "industrial-site-ratio",
        "industrial-site-relaxation-procedure",
    }

    comparisons = {
        (item["issue_id"], item["facet_id"]): item
        for item in inputs["fact_rule_comparisons"]
    }
    assert ("I1", "minimum-area-threshold") not in comparisons

    minimum_area = comparisons[("I2", "minimum-area-threshold")]
    assert minimum_area["fact_value"] == "1500"
    assert minimum_area["threshold_value"] == "1000"
    assert minimum_area["operator"] == ">="
    assert minimum_area["satisfied"] is True

    normal_distance = comparisons[("I2", "distance-normal-threshold")]
    assert normal_distance["fact_value"] == "300"
    assert normal_distance["threshold_value"] == "250"
    assert normal_distance["operator"] == "<="
    assert normal_distance["satisfied"] is False

    conditional_distance = comparisons[("I2", "distance-conditional-threshold")]
    assert conditional_distance["fact_value"] == "300"
    assert conditional_distance["threshold_value"] == "350"
    assert conditional_distance["operator"] == "<="
    assert conditional_distance["satisfied"] is True

    far = comparisons[("I5", "semi-industrial-far-threshold")]
    assert far["fact_value"] == "400"
    assert far["threshold_value"] == "400"
    assert far["satisfied"] is True
    assert all(
        len(item["result_hash"]) == 64 for item in comparisons.values()
    )

    assert coverage["I2"]["covered_facet_ids"] == facets["I2"][
        "covered_facet_ids"
    ]
    assert coverage["I2"]["missing_facet_ids"] == []
    assert set(coverage["I2"]["comparison_ids"]) == {
        minimum_area["comparison_id"],
        normal_distance["comparison_id"],
        conditional_distance["comparison_id"],
    }

    trace_by_issue = {
        item["issue_id"]: item for item in trace["issues"]
    }
    assert trace_by_issue["I2"]["comparisons"]
    assert trace_by_issue["I2"]["facet_coverage"]

    evidence_by_id = {
        item["citation"]["evidence_id"]: item
        for item in bundle["evidence"]
    }
    assert "2분의 1까지" in evidence_by_id["E-INDUSTRIAL-SITE"]["text"]

    forbidden_ids = {
        str(item["evidence_id"])
        for item in fixture["forbidden"]
    }
    assert set(evidence_by_id).isdisjoint(forbidden_ids)
