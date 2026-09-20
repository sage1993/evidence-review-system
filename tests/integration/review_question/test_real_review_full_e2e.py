from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from evidence_review.abstention.finalizer import finalize_run
from evidence_review.canonical_json import dump_bytes
from evidence_review.contracts.question_plan import decode_question_plan
from evidence_review.evidence.finalization import finalize_evidence_database
from evidence_review.evidence.ingest import EvidenceSnapshot, ingest_snapshot
from evidence_review.evidence.store import EvidenceStore
from evidence_review.llm_layer.track_b import required_facet_completeness_status
from evidence_review.planned_review_question import prepare_planned_review_question
from evidence_review.rule_engine.operators import apply_operator, decode_input

_FIXTURE_DIR = (
    Path(__file__).parents[2] / "fixtures" / "real_review_retrieval_relevance"
)


def _load_json(name: str) -> dict[str, Any]:
    payload = json.loads((_FIXTURE_DIR / name).read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    return payload


def _element(evidence_id: str, text: str, parser_order: int) -> dict[str, object]:
    hash_char = format(parser_order % 16, "x")
    return {
        "id": evidence_id,
        "revision_id": "REV-REAL-REVIEW",
        "page_id": "REV-REAL-REVIEW-P1",
        "page_number": 1,
        "element_type": "paragraph",
        "raw_json": {"text": text},
        "raw_text": text,
        "normalized_text": text,
        "raw_payload_hash": hash_char * 64,
        "bbox": [
            10.0,
            float(parser_order * 10),
            500.0,
            float(parser_order * 10 + 8),
        ],
        "parser_order": parser_order,
    }


def _snapshot(
    evidence_fixture: dict[str, Any],
    *,
    omit_issue_ids: frozenset[str] = frozenset(),
) -> EvidenceSnapshot:
    required = [
        record
        for record in evidence_fixture["required"]
        if not set(record["issue_ids"]) & omit_issue_ids
    ]
    forbidden = evidence_fixture["forbidden"]
    distractors = evidence_fixture["distractors"]
    records = [*required, *forbidden, *distractors]
    elements = tuple(
        _element(str(record["evidence_id"]), str(record["text"]), index)
        for index, record in enumerate(records, start=1)
    )
    clauses = tuple(
        {
            "id": str(record["clause_id"]),
            "revision_id": "REV-REAL-REVIEW",
            "title": str(record["title"]),
            "raw_text": str(record["text"]),
            "normalized_text": str(record["text"]),
            "review_status": "AUTOMATIC",
        }
        for record in required
    )
    links = tuple(
        {
            "id": f"L-{record['clause_id']}-{record['evidence_id']}",
            "source_id": str(record["clause_id"]),
            "target_id": str(record["evidence_id"]),
            "relation_type": "source_element",
        }
        for record in required
    )
    return EvidenceSnapshot(
        documents=(
            {"id": "DOC-REAL-REVIEW", "title": "안심주택 실제 검토 회귀 자료"},
        ),
        revisions=(
            {
                "id": "REV-REAL-REVIEW",
                "document_id": "DOC-REAL-REVIEW",
                "source_hash": "a" * 64,
                "byte_size": 4096,
                "page_count": 1,
            },
        ),
        pages=(
            {
                "id": "REV-REAL-REVIEW-P1",
                "revision_id": "REV-REAL-REVIEW",
                "page_number": 1,
                "width": 595.0,
                "height": 842.0,
            },
        ),
        elements=elements,
        clauses=clauses,
        links=links,
    )


def _prepare_workspace(
    tmp_path: Path,
    *,
    omit_issue_ids: frozenset[str] = frozenset(),
):
    plan_payload = _load_json("question-plan.json")
    evidence_fixture = _load_json("expected-evidence.json")
    original_question = plan_payload["original_question"]
    assert isinstance(original_question, str)
    plan = decode_question_plan(plan_payload, original_question)

    workspace = tmp_path / "workspace"
    evidence_directory = workspace / "evidence"
    evidence_directory.mkdir(parents=True)
    with EvidenceStore(
        evidence_directory / "evidence.sqlite",
        create=True,
    ) as store:
        ingest_snapshot(
            store,
            _snapshot(evidence_fixture, omit_issue_ids=omit_issue_ids),
        )
        finalize_evidence_database(store)

    prepared = prepare_planned_review_question(workspace, plan)
    assert prepared.status == "WAITING_TRACK_A"
    return plan, evidence_fixture, workspace / "runs" / prepared.run_id


def _track_a_output(
    run_directory: Path,
    evidence_fixture: dict[str, Any],
) -> dict[str, object]:
    bundle = json.loads(
        (run_directory / "track-a-bundle.json").read_text(encoding="utf-8")
    )
    evidence_by_id = {
        item["citation"]["evidence_id"]: item
        for item in bundle["evidence"]
    }

    claims: list[dict[str, object]] = []
    citation_ids: list[str] = []
    for record in evidence_fixture["required"]:
        evidence_id = str(record["evidence_id"])
        evidence = evidence_by_id.get(evidence_id)
        if evidence is None:
            continue
        citation_id = str(evidence["citation"]["citation_id"])
        citation_ids.append(citation_id)
        issue_ids = [str(item) for item in record["issue_ids"]]
        claims.append(
            {
                "claim_id": f"CL-{issue_ids[0]}",
                "text": f"{record['title']} 근거 확인",
                "issue_ids": issue_ids,
                "citation_ids": [citation_id],
                "numeric_tokens": [],
                "calculation_result_ids": [],
                "rule_references": [],
            }
        )

    return {
        "run_id": run_directory.name,
        "claims": claims,
        "citations": citation_ids,
        "missing_inputs": [],
        "exceptions": [],
        "conflicts": [],
        "explanation": "질문과 직접 관련된 parser-shaped 근거만 사용한다.",
    }


def _track_b_output(track_a: dict[str, object], run_directory: Path) -> dict[str, object]:
    claims = track_a["claims"]
    assert isinstance(claims, list)
    bundle = json.loads((run_directory / "track-a-bundle.json").read_text(encoding="utf-8"))
    facet_status = required_facet_completeness_status(bundle["inputs"].get("facet_coverage"))
    return {
        "run_id": run_directory.name,
        "audited_question": bundle["question"],
        "question_responsiveness": "PASS",
        "required_facet_completeness": facet_status,
        "claim_audits": [
            {
                "claim_id": str(claim["claim_id"]),
                "disposition": "ACCEPT",
                "finding_codes": [],
                "notes": "",
            }
            for claim in claims
            if isinstance(claim, dict)
        ],
        "overall_disposition": "ACCEPT",
    }


def _write_manifest_bound_outputs(
    run_directory: Path,
    track_a: dict[str, object],
    track_b: dict[str, object],
) -> None:
    (run_directory / "track-a-output.json").write_bytes(dump_bytes(track_a))
    (run_directory / "track-b-output.json").write_bytes(dump_bytes(track_b))
    artifacts = {
        name: hashlib.sha256((run_directory / name).read_bytes()).hexdigest()
        for name in (
            "track-a-bundle.json",
            "track-a-output.json",
            "track-b-output.json",
            "confidence-input.json",
        )
    }
    (run_directory / "run-manifest.json").write_bytes(
        dump_bytes({"run_id": run_directory.name, "artifacts": artifacts})
    )


def _assert_claim_issue_lineage(run_directory: Path, packet) -> None:
    bundle = json.loads(
        (run_directory / "track-a-bundle.json").read_text(encoding="utf-8")
    )
    evidence_by_citation = {
        item["citation"]["citation_id"]: item
        for item in bundle["evidence"]
    }
    for claim in packet.claims:
        assert claim.issue_ids
        for citation_id in claim.citation_ids:
            evidence = evidence_by_citation[citation_id]
            assert set(claim.issue_ids) & set(evidence["issue_ids"])


def test_real_review_full_pipeline_reaches_finalizer_with_issue_safe_claims(
    tmp_path: Path,
) -> None:
    plan, evidence_fixture, run_directory = _prepare_workspace(tmp_path)
    track_a = _track_a_output(run_directory, evidence_fixture)
    track_b = _track_b_output(track_a, run_directory)
    _write_manifest_bound_outputs(run_directory, track_a, track_b)

    packet = finalize_run(run_directory)

    assert packet.status == "READY_FOR_HUMAN_REVIEW"
    assert len(packet.claims) == 7
    by_issue = {item.issue_id: item for item in packet.issue_results}
    assert by_issue["I2"].status == "CONDITIONAL"
    assert by_issue["I2"].covered_facet_ids == (
        "minimum-area-threshold",
        "distance-normal-threshold",
        "distance-conditional-threshold",
    )
    assert by_issue["I2"].missing_facet_ids == ()
    assert len(by_issue["I2"].comparison_ids) == 3
    assert all(
        by_issue[f"I{index}"].status == "RESOLVED"
        for index in (1, 3, 4, 5, 6, 7)
    )
    assert {claim.issue_ids[0] for claim in packet.claims} == {
        issue.id for issue in plan.issues
    }
    _assert_claim_issue_lineage(run_directory, packet)

    stored = json.loads(
        (run_directory / "final-review-packet.json").read_text(encoding="utf-8")
    )
    stored_by_issue = {
        item["issue_id"]: item for item in stored["issue_results"]
    }
    assert stored_by_issue["I2"]["covered_facet_ids"] == list(
        by_issue["I2"].covered_facet_ids
    )
    assert stored_by_issue["I2"]["missing_facet_ids"] == []
    assert stored_by_issue["I2"]["comparison_ids"] == list(
        by_issue["I2"].comparison_ids
    )

    forbidden_ids = {
        str(item["evidence_id"])
        for item in evidence_fixture["forbidden"]
    }
    bundle = json.loads(
        (run_directory / "track-a-bundle.json").read_text(encoding="utf-8")
    )
    cited_ids = {
        citation
        for claim in packet.claims
        for citation in claim.citation_ids
    }
    cited_evidence_ids = {
        item["citation"]["evidence_id"]
        for item in bundle["evidence"]
        if item["citation"]["citation_id"] in cited_ids
    }
    assert cited_evidence_ids.isdisjoint(forbidden_ids)

    area = decode_input("1500", "decimal", "site_area")
    minimum_area = decode_input("1000", "decimal", "minimum_area")
    distance = decode_input("300", "decimal", "distance")
    ordinary_limit = decode_input("250", "decimal", "ordinary_limit")
    conditional_limit = decode_input("350", "decimal", "conditional_limit")
    assert apply_operator("gte", area, minimum_area)
    assert not apply_operator("lte", distance, ordinary_limit)
    assert apply_operator("lte", distance, conditional_limit)


def test_real_review_partial_issue_gap_preserves_resolved_claims(
    tmp_path: Path,
) -> None:
    _, evidence_fixture, run_directory = _prepare_workspace(
        tmp_path,
        omit_issue_ids=frozenset({"I7"}),
    )
    track_a = _track_a_output(run_directory, evidence_fixture)
    track_b = _track_b_output(track_a, run_directory)
    _write_manifest_bound_outputs(run_directory, track_a, track_b)

    packet = finalize_run(run_directory)

    # An unresolved required facet is a Track B semantic gate failure; it must
    # not be presented as a review-ready partial result.
    assert packet.status == "ABSTAIN"
    assert "TRACK_B_REJECTION" in packet.abstention_reasons
    assert len(packet.claims) == 6
    by_issue = {item.issue_id: item for item in packet.issue_results}
    assert by_issue["I7"].status == "UNRESOLVED"
    assert "RETRIEVAL_MISS" in by_issue["I7"].gap_codes
    assert by_issue["I2"].status == "CONDITIONAL"
    assert all(
        by_issue[f"I{index}"].status == "RESOLVED"
        for index in (1, 3, 4, 5, 6)
    )
    assert all("I7" not in claim.issue_ids for claim in packet.claims)
    _assert_claim_issue_lineage(run_directory, packet)
