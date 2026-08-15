from __future__ import annotations

import http.client
import json
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest

from evidence_review.contracts.drawing import DrawingCandidate, Geometry
from evidence_review.drawing_review.local_server import serve_annotation_workspace
from evidence_review.drawing_review.view_model import DrawingPage
from evidence_review.parsing.drawing_candidates import persist_candidate

SOURCE_HASH = "a" * 64
TOKEN = "T" * 32


def _page() -> DrawingPage:
    return DrawingPage(
        source_sha256=SOURCE_HASH,
        page=1,
        coordinate_system="IMAGE_TOP_LEFT_PIXELS",
        width=1000.0,
        height=800.0,
    )


def _candidate() -> DrawingCandidate:
    return DrawingCandidate(
        candidate_id="CAND-EXISTING",
        source_sha256=SOURCE_HASH,
        page=1,
        candidate_type="DIMENSION_TEXT",
        origin="EXTRACTOR",
        status="UNCONFIRMED",
        geometry=Geometry(
            type="BBOX",
            coordinate_system="IMAGE_TOP_LEFT_PIXELS",
            coordinates=(100.0, 120.0, 300.0, 180.0),
        ),
        raw_value="8M",
        normalized_candidate="8 m",
        extractor="fixture",
        extractor_version="1",
        annotation_id=None,
    )


def _action_payload() -> dict[str, object]:
    return {
        "action": "ACCEPTED",
        "candidate_id": "CAND-EXISTING",
        "reviewer": "kim-sh",
        "confirmed_at": "2026-08-03T22:10:00+09:00",
        "confirmed_value": None,
        "unit": None,
        "geometry": None,
    }


def _post(server_url: str, origin: str, payload: bytes) -> tuple[int, bytes]:
    request = Request(
        server_url + "/actions",
        data=payload,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "Origin": origin,
        },
    )
    try:
        with urlopen(request, timeout=5) as response:
            return response.status, response.read()
    except HTTPError as error:
        return error.code, error.read()


def test_serves_tokenized_page_on_loopback(tmp_path: Path) -> None:
    case_dir = tmp_path / "cases" / "CASE-001"
    case_dir.mkdir(parents=True)

    with serve_annotation_workspace(
        html="<!doctype html><p>annotation</p>",
        case_dir=case_dir,
        page=_page(),
        candidate_entries={},
        token=TOKEN,
    ) as server:
        assert server.host == "127.0.0.1"
        assert server.url.startswith("http://127.0.0.1:")
        with urlopen(server.url, timeout=5) as response:
            body = response.read().decode("utf-8")
            assert response.status == 200
            assert response.headers["Access-Control-Allow-Origin"] is None
            assert response.headers["Cache-Control"] == "no-store"
            assert "default-src 'none'" in response.headers["Content-Security-Policy"]
        assert "annotation" in body


def test_rejects_wrong_token(tmp_path: Path) -> None:
    case_dir = tmp_path / "cases" / "CASE-001"
    case_dir.mkdir(parents=True)

    with serve_annotation_workspace(
        html="<p>annotation</p>",
        case_dir=case_dir,
        page=_page(),
        candidate_entries={},
        token=TOKEN,
    ) as server:
        wrong_url = server.url.replace(TOKEN, "W" * 32)
        with pytest.raises(HTTPError) as captured:
            urlopen(wrong_url, timeout=5)
        assert captured.value.code == 403


def test_rejects_wrong_host_header(tmp_path: Path) -> None:
    case_dir = tmp_path / "cases" / "CASE-001"
    case_dir.mkdir(parents=True)

    with serve_annotation_workspace(
        html="<p>annotation</p>",
        case_dir=case_dir,
        page=_page(),
        candidate_entries={},
        token=TOKEN,
    ) as server:
        connection = http.client.HTTPConnection(server.host, server.port, timeout=5)
        connection.putrequest("GET", f"/annotation/{TOKEN}", skip_host=True)
        connection.putheader("Host", "evil.example")
        connection.endheaders()
        response = connection.getresponse()
        assert response.status == 403
        response.read()
        connection.close()


def test_rejects_missing_or_wrong_origin_on_post(tmp_path: Path) -> None:
    case_dir = tmp_path / "cases" / "CASE-001"
    case_dir.mkdir(parents=True)

    with serve_annotation_workspace(
        html="<p>annotation</p>",
        case_dir=case_dir,
        page=_page(),
        candidate_entries={},
        token=TOKEN,
    ) as server:
        body = json.dumps(_action_payload()).encode("utf-8")
        status, _ = _post(server.url, "http://evil.example", body)
        assert status == 403

        request = Request(
            server.url + "/actions",
            data=body,
            method="POST",
            headers={"Content-Type": "application/json"},
        )
        with pytest.raises(HTTPError) as captured:
            urlopen(request, timeout=5)
        assert captured.value.code == 403


def test_valid_post_records_append_only_confirmation(tmp_path: Path) -> None:
    case_dir = tmp_path / "cases" / "CASE-001"
    candidate = _candidate()
    entry = persist_candidate(case_dir, candidate)

    with serve_annotation_workspace(
        html="<p>annotation</p>",
        case_dir=case_dir,
        page=_page(),
        candidate_entries={candidate.candidate_id: entry},
        token=TOKEN,
    ) as server:
        status, body = _post(
            server.url,
            server.origin,
            json.dumps(_action_payload()).encode("utf-8"),
        )

        assert status == 201
        response = json.loads(body)
        confirmation = response["confirmation"]
        assert confirmation["artifact_id"].startswith("CONF-")
        assert confirmation["sha256"]
        assert len(server.results) == 1
        assert (case_dir / confirmation["relative_path"]).is_file()


def test_rejects_large_or_malformed_json_body(tmp_path: Path) -> None:
    case_dir = tmp_path / "cases" / "CASE-001"
    case_dir.mkdir(parents=True)

    with serve_annotation_workspace(
        html="<p>annotation</p>",
        case_dir=case_dir,
        page=_page(),
        candidate_entries={},
        token=TOKEN,
        max_body_bytes=128,
    ) as server:
        large_status, _ = _post(server.url, server.origin, b"{" + b"x" * 256)
        assert large_status == 413

        malformed_status, malformed_body = _post(
            server.url,
            server.origin,
            b"{not-json}",
        )
        assert malformed_status == 400
        assert str(tmp_path).encode("utf-8") not in malformed_body


def test_rejects_non_json_content_type(tmp_path: Path) -> None:
    case_dir = tmp_path / "cases" / "CASE-001"
    case_dir.mkdir(parents=True)

    with serve_annotation_workspace(
        html="<p>annotation</p>",
        case_dir=case_dir,
        page=_page(),
        candidate_entries={},
        token=TOKEN,
    ) as server:
        request = Request(
            server.url + "/actions",
            data=b"{}",
            method="POST",
            headers={
                "Content-Type": "text/plain",
                "Origin": server.origin,
            },
        )
        with pytest.raises(HTTPError) as captured:
            urlopen(request, timeout=5)
        assert captured.value.code == 415


def test_rejects_symlink_case_root(tmp_path: Path) -> None:
    target = tmp_path / "actual-case"
    target.mkdir()
    linked = tmp_path / "CASE-001"
    try:
        linked.symlink_to(target, target_is_directory=True)
    except OSError:
        pytest.skip("directory symlink creation is unavailable")

    with pytest.raises(ValueError, match="case_dir"):
        serve_annotation_workspace(
            html="<p>annotation</p>",
            case_dir=linked,
            page=_page(),
            candidate_entries={},
            token=TOKEN,
        )
