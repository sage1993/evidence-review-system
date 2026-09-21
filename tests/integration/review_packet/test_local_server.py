from __future__ import annotations

import hashlib
import http.client
import json
from pathlib import Path
from threading import Thread

import pytest

from evidence_review.abstention.finalizer import finalize_run
from evidence_review.evidence.finalization import finalize_evidence_database
from evidence_review.evidence.snapshot import finalized_evidence_provenance
from evidence_review.evidence.store import EvidenceStore
from evidence_review.review_packet.local_server import create_review_server
from tests.integration.abstention.test_finalizer import _write_run
from tests.integration.review_packet.test_review_workspace_performance import (
    VALID_MINIMAL_PNG,
)

RUN_ID = "RUN-0123456789ABCDEF0123"
TOKEN = "a" * 43
REVIEWER_ID = "reviewer-01"


def _artifacts(root: Path, *, inputs: dict[str, object] | None = None) -> tuple[Path, bytes]:
    evidence_directory = root / "evidence"
    evidence_directory.mkdir()
    evidence_db = evidence_directory / "evidence.sqlite"
    with EvidenceStore(evidence_db, create=True) as store:
        connection = store.require_connection()
        connection.execute("INSERT INTO documents(id, title) VALUES('DOC1', 'Document')")
        connection.execute(
            "INSERT INTO revisions(id, document_id, source_hash, byte_size, page_count) "
            "VALUES('REV1', 'DOC1', ?, 10, 1)",
            ("a" * 64,),
        )
        connection.execute(
            "INSERT INTO pages(id, revision_id, page_number, width, height) "
            "VALUES('REV1-P1', 'REV1', 1, 100, 100)"
        )
        connection.execute(
            "INSERT INTO elements(id, page_id, element_type, raw_json, raw_text, normalized_text, "
            "raw_payload_hash, bbox_json, parser_order) "
            "VALUES('E1', 'REV1-P1', 'paragraph', '{}', 'verified', 'verified', ?, "
            "'[0,0,10,10]', 0)",
            ("a" * 64,),
        )
        connection.execute(
            "INSERT INTO retrieval_records(evidence_id, evidence_type, document_id, revision_id, "
            "page_id, "
            "page_number, bbox_json, source_hash, title, raw_text, normalized_text) "
            "VALUES('E1', 'clause', 'DOC1', 'REV1', 'REV1-P1', 1, '[0,0,10,10]', ?, "
            "'Document', 'verified', 'verified')",
            ("a" * 64,),
        )
        connection.execute(
            "INSERT INTO snapshot_meta(key, value) VALUES('snapshot_hash', ?)",
            ("a" * 64,),
        )
        connection.execute(
            "INSERT INTO retrieval_meta(key, value) VALUES('snapshot_hash', ?)",
            ("a" * 64,),
        )
        connection.commit()
        finalize_evidence_database(store)
    provenance = finalized_evidence_provenance(evidence_db)
    run_directory = _write_run(root / "runs", snapshot_hash=provenance["evidence_snapshot_hash"])
    manifest_path = run_directory / "run-manifest.json"
    manifest = json.loads(manifest_path.read_bytes())
    for name in manifest["artifacts"]:
        artifact = run_directory / name
        artifact.write_text(artifact.read_text(encoding="utf-8").replace('"C1"', '"CIT-E1"'),
                            encoding="utf-8")
        if name == "track-a-bundle.json":
            bundle = json.loads(artifact.read_bytes())
            bundle["inputs"]["evidence_snapshot_provenance"] = provenance
            bundle["inputs"].update(inputs or {})
            artifact.write_text(json.dumps(bundle), encoding="utf-8")
        manifest["artifacts"][name] = hashlib.sha256(artifact.read_bytes()).hexdigest()
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    finalize_run(run_directory)
    (run_directory / "review-request.json").write_text(
        json.dumps({
            "inputs": {
                "snapshot_hash": provenance["evidence_snapshot_hash"],
                "evidence_snapshot_provenance": provenance,
            }
        }),
        encoding="utf-8",
    )
    packet = (run_directory / "final-review-packet.json").read_bytes()
    image_directory = root / "page-images" / "REV1"
    image_directory.mkdir(parents=True)
    (image_directory / "page-0001.png").write_bytes(VALID_MINIMAL_PNG)
    (image_directory / "page-0001.json").write_text(
        json.dumps({
            "format": "evidence-review/page-image", "version": 1,
            "revision_id": "REV1", "page_number": 1, "source_hash": "a" * 64,
            "pdf_width": 100.0, "pdf_height": 100.0,
            "image_sha256": hashlib.sha256(VALID_MINIMAL_PNG).hexdigest(),
        }),
        encoding="utf-8",
    )
    (run_directory / "review.html").write_text(
        "<html><body>protected review</body></html>", encoding="utf-8"
    )
    return run_directory, packet


def _request(
    server: object,
    method: str,
    path: str,
    *,
    body: dict[str, str] | None = None,
) -> tuple[int, dict[str, object]]:
    address = server.server_address
    host, port = address[0], address[1]
    connection = http.client.HTTPConnection(host, port, timeout=5)
    headers = {"Host": f"{host}:{port}"}
    payload: bytes | None = None
    if body is not None:
        payload = json.dumps(body).encode("utf-8")
        headers.update(
            {
                "Origin": f"http://{host}:{port}",
                "Content-Type": "application/json",
                "Content-Length": str(len(payload)),
            }
        )
    connection.request(method, path, body=payload, headers=headers)
    response = connection.getresponse()
    document = json.loads(response.read().decode("utf-8"))
    connection.close()
    return response.status, document


def test_server_supplies_reviewer_hash_and_server_controlled_timestamp(tmp_path: Path) -> None:
    run_directory, packet = _artifacts(tmp_path)
    server = create_review_server(
        tmp_path,
        run_tokens={RUN_ID: TOKEN},
        reviewer_ids={RUN_ID: REVIEWER_ID},
    )
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        base = f"/runs/{RUN_ID}/{TOKEN}"
        status_code, status = _request(server, "GET", base + "/decision/status")
        packet_hash = hashlib.sha256(packet).hexdigest()
        assert status_code == 200
        assert status["reviewer_id"] == REVIEWER_ID
        assert status["packet_hash"] == packet_hash
        assert status["decision_record"] is None

        post_code, result = _request(
            server,
            "POST",
            base + "/decision",
            body={
                "reviewer_id": REVIEWER_ID,
                "decision": "SATISFIED",
                "notes": "근거 확인 완료",
            },
        )
        assert post_code == 201
        assert result["display_status"] == "REVIEW_COMPLETED"
        reviewed_at = result["reviewed_at"]
        assert isinstance(reviewed_at, str)
        assert reviewed_at.endswith("+00:00")
        decisions = tuple((run_directory / "human-decisions").glob("*.json"))
        assert len(decisions) == 1
        saved = json.loads(decisions[0].read_text(encoding="utf-8"))
        assert saved["reviewed_at"] == reviewed_at
        assert saved["packet_hash"] == packet_hash

        status_code, status = _request(server, "GET", base + "/decision/status")
        assert status_code == 200
        assert status["display_status"] == "REVIEW_COMPLETED"
        assert status["decision_record"] == {
            "reviewer_id": REVIEWER_ID,
            "reviewed_at": reviewed_at,
            "decision": "SATISFIED",
            "notes": "근거 확인 완료",
        }
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_server_rejects_client_timestamp_extra_field_and_packet_mismatch(tmp_path: Path) -> None:
    _, packet = _artifacts(tmp_path)
    server = create_review_server(tmp_path, run_tokens={RUN_ID: TOKEN})
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        base = f"/runs/{RUN_ID}/{TOKEN}/decision"
        valid = {
            "reviewer_id": REVIEWER_ID,
            "decision": "SATISFIED",
            "notes": "확인",
        }
        invalid_extra = {**valid, "reviewed_at": "2026-08-13T12:00:00+09:00"}
        code, document = _request(server, "POST", base, body=invalid_extra)
        assert code == 400 and document["error"] == "INVALID_DECISION"

        code, document = _request(
            server,
            "POST",
            base,
            body={**valid, "packet_hash": "0" * 64},
        )
        assert code == 400 and document["error"] == "INVALID_DECISION"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_configured_reviewer_id_is_readonly_for_post(tmp_path: Path) -> None:
    _, packet = _artifacts(tmp_path)
    server = create_review_server(
        tmp_path,
        run_tokens={RUN_ID: TOKEN},
        reviewer_ids={RUN_ID: REVIEWER_ID},
    )
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        code, document = _request(
            server,
            "POST",
            f"/runs/{RUN_ID}/{TOKEN}/decision",
            body={
                "reviewer_id": "different-reviewer",
                "decision": "SATISFIED",
                "notes": "확인",
            },
        )
        assert code == 400
        assert document["error"] == "INVALID_DECISION"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_server_rejects_unknown_reviewer_run_binding(tmp_path: Path) -> None:
    _artifacts(tmp_path)
    with pytest.raises(ValueError, match="unknown run"):
        create_review_server(
            tmp_path,
            run_tokens={RUN_ID: TOKEN},
            reviewer_ids={"RUN-AAAAAAAAAAAAAAAAAAAA": REVIEWER_ID},
        )
