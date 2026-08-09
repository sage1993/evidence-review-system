import hashlib
import json
from pathlib import Path

import pytest

from ansim_review.evidence.store import EvidenceStore
from ansim_review.review_packet.builder import build_review_view_model

FIXTURES = Path(__file__).parents[2] / "golden" / "contracts"


def _evidence_db(path: Path) -> None:
    with EvidenceStore(path, create=True) as store:
        connection = store.require_connection()
        connection.execute("INSERT INTO documents(id, title) VALUES('DOC1', 'Document')")
        connection.execute(
            """
            INSERT INTO revisions(id, document_id, source_hash, byte_size, page_count)
            VALUES('REV1', 'DOC1', ?, 10, 3)
            """,
            ("a" * 64,),
        )
        connection.execute(
            """
            INSERT INTO pages(id, revision_id, page_number, width, height)
            VALUES('REV1-P3', 'REV1', 3, 120, 200)
            """
        )
        connection.execute(
            """
            INSERT INTO retrieval_records(
                evidence_id, evidence_type, document_id, revision_id, page_id,
                page_number, bbox_json, source_hash, title, raw_text,
                normalized_text
            ) VALUES('E1', 'clause', 'DOC1', 'REV1', 'REV1-P3', 3, ?, ?,
                     'Document', 'Verified fixture quote', 'Verified fixture quote')
            """,
            (json.dumps([10, 20, 110, 40]), "a" * 64),
        )
        connection.commit()


def _packet(name: str) -> tuple[bytes, dict[str, object]]:
    raw = (FIXTURES / name).read_bytes()
    document = json.loads(raw)
    assert isinstance(document, dict)
    return raw, document


@pytest.mark.parametrize(
    "fixture_name",
    (
        "review-packet-v1-ready.json",
        "review-packet-v2-from-v1-ready.json",
    ),
)
def test_view_model_projects_real_v1_and_v2_packets_with_verified_evidence(
    tmp_path: Path, fixture_name: str
) -> None:
    evidence_db = tmp_path / "evidence.sqlite"
    _evidence_db(evidence_db)
    packet_bytes, packet = _packet(fixture_name)

    model = build_review_view_model(packet, evidence_db)

    assert model["metadata"]["packet_sha256"] == hashlib.sha256(packet_bytes).hexdigest()
    assert model["summary"]["citation_count"] == 1
    assert model["review_items"][0]["claim_id"] == "C1"
    assert model["decision"]["human_decision"] is None
    assert model["display_status"] == model["status"]
    if fixture_name.startswith("review-packet-v2"):
        assert model["case_id"] == "CASE-LEGACY"
        assert model["finalizer_status"] == "READY_FOR_HUMAN_REVIEW"
        assert model["evidence"] == []
        assert model["drawing_evidence"] == []
        assert model["confirmed_inputs"] == []
        assert model["rule_evaluations"] == []


def test_view_model_rejects_non_null_machine_decision(tmp_path: Path) -> None:
    evidence_db = tmp_path / "evidence.sqlite"
    _evidence_db(evidence_db)
    _, packet = _packet("review-packet-v1-ready.json")
    packet["human_decision"] = "SATISFIED"

    with pytest.raises(ValueError, match="human_decision"):
        build_review_view_model(packet, evidence_db)


def test_view_model_rejects_conflicting_v2_citation_identity(tmp_path: Path) -> None:
    evidence_db = tmp_path / "evidence.sqlite"
    _evidence_db(evidence_db)
    _, packet = _packet("review-packet-v2-from-v1-ready.json")
    packet["compatibility_source_version"] = None
    packet["evidence"] = [
        {
            "evidence_id": "E1",
            "citation": {
                "citation_id": "CIT-E1",
                "document_id": "DOC-CONFLICT",
                "revision_id": "REV1",
                "page_number": 3,
                "evidence_id": "E1",
                "bbox": [10, 20, 110, 40],
                "source_hash": "a" * 64,
            },
            "quote": "Verified fixture quote",
            "numeric_tokens": [],
        }
    ]

    with pytest.raises(ValueError, match="citation identity"):
        build_review_view_model(packet, evidence_db)


def test_view_model_rejects_unresolved_cited_evidence(tmp_path: Path) -> None:
    evidence_db = tmp_path / "evidence.sqlite"
    _evidence_db(evidence_db)
    _, packet = _packet("review-packet-v1-ready.json")
    claims = packet["claims"]
    assert isinstance(claims, list)
    claim = claims[0]
    assert isinstance(claim, dict)
    claim["citation_ids"] = ["CIT-MISSING"]

    with pytest.raises(ValueError, match="unresolved citation"):
        build_review_view_model(packet, evidence_db)


def test_view_model_hashes_exact_supplied_noncanonical_packet_bytes(
    tmp_path: Path,
) -> None:
    evidence_db = tmp_path / "evidence.sqlite"
    _evidence_db(evidence_db)
    _, packet = _packet("review-packet-v1-ready.json")
    packet_bytes = json.dumps(packet, ensure_ascii=False, indent=2).encode("utf-8")
    assert b"\n  \"run_id\"" in packet_bytes

    model = build_review_view_model(packet_bytes, evidence_db)

    assert model["metadata"]["packet_sha256"] == hashlib.sha256(packet_bytes).hexdigest()
