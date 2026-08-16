from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from evidence_review.abstention.finalizer import finalize_run
from evidence_review.canonical_json import dump_bytes
from evidence_review.contracts.question_plan import decode_question_plan
from evidence_review.evidence.ingest import EvidenceSnapshot, ingest_snapshot
from evidence_review.evidence.store import EvidenceStore
from evidence_review.planned_review_question import prepare_planned_review_question
from evidence_review.retrieval.index import build_fts_index

_FIXTURE_DIR = (
    Path(__file__).parents[2] / "fixtures" / "real_review_retrieval_relevance"
)


def _load_plan_payload() -> dict[str, Any]:
    payload = json.loads(
        (_FIXTURE_DIR / "question-plan.json").read_text(encoding="utf-8")
    )
    assert isinstance(payload, dict)
    search_requests = payload["search_requests"]
    assert isinstance(search_requests, list)
    for request in search_requests:
        assert isinstance(request, dict)
        if request["id"] == "S2":
            request["text"] = "역세권 승강장 경계 300m 사업대상지 면적 기준"
        elif request["id"] == "S7":
            request["text"] = "지구단위계획 주차장 설치기준 추가 완화 요건 절차"
    return payload


def _page(page_id: str, revision_id: str) -> dict[str, object]:
    return {
        "id": page_id,
        "revision_id": revision_id,
        "page_number": 1,
        "width": 595.0,
        "height": 842.0,
    }


def _element(
    evidence_id: str,
    revision_id: str,
    page_id: str,
    order: int,
    text: str,
) -> dict[str, object]:
    return {
        "id": evidence_id,
        "revision_id": revision_id,
        "page_id": page_id,
        "page_number": 1,
        "element_type": "paragraph",
        "raw_json": {"text": text},
        "raw_text": text,
        "normalized_text": text,
        "raw_payload_hash": format(order % 16, "x") * 64,
        "bbox": [10.0, float(order * 20), 550.0, float(order * 20 + 15)],
        "parser_order": order,
    }


def _snapshot() -> EvidenceSnapshot:
    local_texts = (
        "2-1-1. 안심주택 사업대상지 면적",
        "안심주택 사업대상지 최소 면적은 1,000㎡ 이상으로 한다.",
        "2-1-2. 역세권 사업대상지",
        "역의 각 승강장 경계로부터 직각으로 250미터 이내로 한다.",
        (
            "통합심의위원회의 심의를 거쳐 역의 각 승강장 경계 및 출입구로부터 "
            "350미터 이내의 토지를 사업대상지로 지정할 수 있다."
        ),
        "제13조(주차장 설치기준 완화)",
        (
            "① 사업시행자는 임대형기숙사를 제외한 안심주택인 경우 "
            "「주택건설기준 등에 관한 규정」 제27조에 따라 주차장을 "
            "설치하여야 한다."
        ),
        (
            "② 사업시행자는 임대형기숙사인 경우 「서울특별시 주차장 설치 및 "
            "관리 조례」 제20조제1항 별표 2에 따라 주차장을 설치하여야 한다."
        ),
        (
            "③ 안심주택을 복합으로 계획하는 경우 주택용도에 따라 "
            "제1항 및 제2항을 각각 적용한다."
        ),
        (
            "④ 시장은 원활한 교통소통 또는 보행환경 조성을 위하여 "
            "「국토의 계획 및 이용에 관한 법률 시행령」 제46조제6항에 따라 "
            "지구단위계획으로 주차장 설치기준을 완화하여 적용할 수 있다."
        ),
        "제14조(준공업지역 안심주택)",
        (
            "① 준공업지역에서 안심주택을 공급하는 경우 공동주택 "
            "기본용적률을 400퍼센트까지 완화할 수 있다."
        ),
        (
            "② 준공업지역 산업부지 확보비율은 공공지원민간임대주택 "
            "통합심의위원회의 결정에 따른다."
        ),
    )
    local_elements = tuple(
        _element("E-LOCAL-%02d" % index, "REV-LOCAL", "P-LOCAL", index, text)
        for index, text in enumerate(local_texts, start=1)
    )
    external_elements = (
        _element(
            "E-KHC-27",
            "REV-KHC",
            "P-KHC",
            1,
            "제27조(주차장) 주택의 주차장 설치기준을 정한다.",
        ),
        _element(
            "E-PARKING-ANNEX-2",
            "REV-PARKING",
            "P-PARKING",
            1,
            "별표 2 부설주차장의 설치대상시설물 종류 및 설치기준",
        ),
        _element(
            "E-PLANNING-46",
            "REV-PLANNING",
            "P-PLANNING",
            1,
            (
                "제46조(도시지역 내 지구단위계획구역에서의 건폐율 등의 완화적용) "
                "⑥ 지구단위계획으로 정하는 바에 따라 관련 기준을 완화할 수 있다."
            ),
        ),
    )
    return EvidenceSnapshot(
        documents=(
            {
                "id": "DOC-LOCAL",
                "title": "서울특별시 안심주택 공급 지원에 관한 조례",
            },
            {"id": "DOC-KHC", "title": "주택건설기준 등에 관한 규정"},
            {
                "id": "DOC-PARKING",
                "title": "서울특별시 주차장 설치 및 관리 조례",
            },
            {
                "id": "DOC-PLANNING",
                "title": "국토의 계획 및 이용에 관한 법률 시행령",
            },
        ),
        revisions=(
            {
                "id": "REV-LOCAL",
                "document_id": "DOC-LOCAL",
                "source_hash": "a" * 64,
                "byte_size": 5000,
                "page_count": 1,
            },
            {
                "id": "REV-KHC",
                "document_id": "DOC-KHC",
                "source_hash": "b" * 64,
                "byte_size": 1000,
                "page_count": 1,
            },
            {
                "id": "REV-PARKING",
                "document_id": "DOC-PARKING",
                "source_hash": "c" * 64,
                "byte_size": 1000,
                "page_count": 1,
            },
            {
                "id": "REV-PLANNING",
                "document_id": "DOC-PLANNING",
                "source_hash": "d" * 64,
                "byte_size": 1000,
                "page_count": 1,
            },
        ),
        pages=(
            _page("P-LOCAL", "REV-LOCAL"),
            _page("P-KHC", "REV-KHC"),
            _page("P-PARKING", "REV-PARKING"),
            _page("P-PLANNING", "REV-PLANNING"),
        ),
        elements=(*local_elements, *external_elements),
    )


def _track_a_output(run_directory: Path) -> dict[str, object]:
    bundle = json.loads(
        (run_directory / "track-a-bundle.json").read_text(encoding="utf-8")
    )
    by_issue: dict[str, dict[str, object]] = {}
    for item in bundle["evidence"]:
        assert isinstance(item, dict)
        issue_ids = item.get("issue_ids", [])
        assert isinstance(issue_ids, list)
        for issue_id in issue_ids:
            if isinstance(issue_id, str):
                by_issue.setdefault(issue_id, item)

    claims: list[dict[str, object]] = []
    citations: list[str] = []
    for index in range(1, 8):
        issue_id = f"I{index}"
        evidence = by_issue[issue_id]
        citation = evidence["citation"]
        assert isinstance(citation, dict)
        citation_id = citation["citation_id"]
        assert isinstance(citation_id, str)
        citations.append(citation_id)
        claims.append(
            {
                "claim_id": f"CL-{issue_id}",
                "text": f"{issue_id} 관련 권위 근거를 확인했다.",
                "issue_ids": [issue_id],
                "citation_ids": [citation_id],
                "numeric_tokens": [],
                "calculation_result_ids": [],
                "rule_references": [],
            }
        )

    return {
        "run_id": run_directory.name,
        "claims": claims,
        "citations": citations,
        "missing_inputs": [],
        "exceptions": [],
        "conflicts": [],
        "explanation": "실제 parser element에서 파생한 근거만 사용한다.",
    }


def _track_b_output(track_a: dict[str, object], run_id: str) -> dict[str, object]:
    claims = track_a["claims"]
    assert isinstance(claims, list)
    return {
        "run_id": run_id,
        "claim_audits": [
            {
                "claim_id": claim["claim_id"],
                "disposition": "ACCEPT",
                "finding_codes": [],
                "notes": "",
            }
            for claim in claims
            if isinstance(claim, dict)
        ],
        "overall_disposition": "ACCEPT",
    }


def _write_manifest_outputs(
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


def test_element_only_real_workspace_reaches_finalizer_with_all_issue_lineage(
    tmp_path: Path,
) -> None:
    plan_payload = _load_plan_payload()
    question = plan_payload["original_question"]
    assert isinstance(question, str)
    plan = decode_question_plan(plan_payload, question)

    workspace = tmp_path / "workspace"
    evidence_directory = workspace / "evidence"
    evidence_directory.mkdir(parents=True)
    with EvidenceStore(evidence_directory / "evidence.sqlite", create=True) as store:
        ingest_snapshot(store, _snapshot())
        connection = store.require_connection()
        build_fts_index(connection)
        assert connection.execute("SELECT COUNT(*) FROM clauses").fetchone() == (0,)

    prepared = prepare_planned_review_question(workspace, plan)
    assert prepared.status == "WAITING_TRACK_A"
    run_directory = workspace / "runs" / prepared.run_id

    with EvidenceStore(evidence_directory / "evidence.sqlite") as store:
        connection = store.require_connection()
        assert connection.execute("SELECT COUNT(*) FROM clauses").fetchone()[0] >= 8
        assert connection.execute("SELECT COUNT(*) FROM clause_fts").fetchone()[0] >= 8

    retrieval_trace = json.loads(
        (run_directory / "retrieval-trace.json").read_text(encoding="utf-8")
    )
    issue_rows = {item["issue_id"]: item for item in retrieval_trace["issues"]}
    assert all(
        issue_rows[f"I{index}"]["coverage"]["evidence_ids"]
        for index in range(1, 8)
    )
    assert all(
        "RETRIEVAL_MISS"
        not in issue_rows[f"I{index}"]["coverage"]["gap_codes"]
        for index in range(1, 8)
    )

    bundle = json.loads(
        (run_directory / "track-a-bundle.json").read_text(encoding="utf-8")
    )
    issue_text: dict[str, list[str]] = {f"I{index}": [] for index in range(1, 8)}
    for item in bundle["evidence"]:
        for issue_id in item.get("issue_ids", []):
            if issue_id in issue_text:
                issue_text[issue_id].append(item["text"])
    assert any(
        "250미터" in text and "350미터" in text for text in issue_text["I2"]
    )
    assert any("임대형기숙사" in text for text in issue_text["I4"])
    assert any("복합" in text for text in issue_text["I4"])

    track_a = _track_a_output(run_directory)
    track_b = _track_b_output(track_a, run_directory.name)
    _write_manifest_outputs(run_directory, track_a, track_b)

    packet = finalize_run(run_directory)

    assert packet.status == "READY_FOR_HUMAN_REVIEW"
    assert len(packet.claims) == 7
    assert {claim.issue_ids[0] for claim in packet.claims} == {
        f"I{index}" for index in range(1, 8)
    }
    assert packet.confidence is not None
    assert packet.confidence.level == "MEDIUM"
    human_factor = next(
        factor
        for factor in packet.confidence.factors
        if factor.name == "human review status"
    )
    assert human_factor.value == "0.0000"
    assert human_factor.source == "human_review:pending"
