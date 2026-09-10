from __future__ import annotations

import hashlib
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
TOKEN = "H" * 32
RULE_MANIFEST_SHA256 = hashlib.sha256(
    Path("tests/fixtures/ansim/rules/manifests/active.json").read_bytes()
).hexdigest()


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
        candidate_id="CAND-BROWSER",
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


def _accept_payload(*, reviewer: str = "ksh") -> bytes:
    return json.dumps(
        {
            "action": "ACCEPTED",
            "candidate_id": "CAND-BROWSER",
            "reviewer": reviewer,
            "confirmed_at": "2026-08-06T12:00:00+09:00",
            "confirmed_value": None,
            "unit": None,
            "geometry": None,
        }
    ).encode("utf-8")


def test_calibration_form_is_available_after_confirmation(tmp_path: Path) -> None:
    case_dir = tmp_path / "CASE-001"
    case_dir.mkdir()
    candidate = _candidate()
    entry = persist_candidate(case_dir, candidate)

    with serve_annotation_workspace(
        html="<p>annotation</p>",
        case_dir=case_dir,
        page=_page(),
        candidate_entries={candidate.candidate_id: entry},
        token=TOKEN,
        page_image=b"sample-image",
    ) as server:
        with urlopen(server.url, timeout=5) as response:
            annotation_html = response.read().decode("utf-8")
        assert 'data-calibration-link' in annotation_html
        assert 'aria-disabled="true"' in annotation_html
        request = Request(
            server.url + "/actions",
            data=_accept_payload(reviewer="김성현"),
            method="POST",
            headers={"Content-Type": "application/json", "Origin": server.origin},
        )
        with urlopen(request, timeout=5) as response:
            confirmation = json.loads(response.read())["confirmation"]

        calibration_url = (
            f"{server.calibration_url}?candidate_id={candidate.candidate_id}"
            f"&confirmation_id={confirmation['artifact_id']}"
        )
        with urlopen(calibration_url, timeout=5) as response:
            body = response.read().decode("utf-8")
            assert response.status == 200
            assert response.headers["Content-Type"] == "text/html; charset=utf-8"

        assert "Calibration" in body
        assert 'name="confirmed_at"' in body
        assert candidate.candidate_id in body
        assert confirmation["artifact_id"] in body
        assert 'id="calibration-form"' in body
        assert "Content-Type" in body
        assert "packet_url" in body
        assert 'name="reviewer" value="김성현" required readonly' in body
        assert 'name="reviewer" value="ksh"' not in body


def test_annotation_action_rejects_missing_reviewer_without_confirmation_write(
    tmp_path: Path,
) -> None:
    case_dir = tmp_path / "CASE-001"
    case_dir.mkdir()
    candidate = _candidate()
    entry = persist_candidate(case_dir, candidate)
    payload = json.loads(_accept_payload())
    del payload["reviewer"]

    with serve_annotation_workspace(
        html="<p>annotation</p>",
        case_dir=case_dir,
        page=_page(),
        candidate_entries={candidate.candidate_id: entry},
        token=TOKEN,
    ) as server:
        request = Request(
            server.url + "/actions",
            data=json.dumps(payload).encode("utf-8"),
            method="POST",
            headers={"Content-Type": "application/json", "Origin": server.origin},
        )
        with pytest.raises(HTTPError) as captured:
            urlopen(request, timeout=5)

    assert captured.value.code == 400
    assert not (case_dir / "confirmations").exists()


def test_calibration_rejects_client_reviewer_override_without_write(tmp_path: Path) -> None:
    case_dir = tmp_path / "CASE-001"
    case_dir.mkdir()
    candidate = _candidate()
    entry = persist_candidate(case_dir, candidate)

    with serve_annotation_workspace(
        html="<p>annotation</p>",
        case_dir=case_dir,
        page=_page(),
        candidate_entries={candidate.candidate_id: entry},
        token=TOKEN,
    ) as server:
        action_request = Request(
            server.url + "/actions",
            data=_accept_payload(reviewer="김성현"),
            method="POST",
            headers={"Content-Type": "application/json", "Origin": server.origin},
        )
        with urlopen(action_request, timeout=5) as response:
            confirmation = json.loads(response.read())["confirmation"]
        payload = {
            "candidate_id": candidate.candidate_id,
            "confirmation_id": confirmation["artifact_id"],
            "reviewer": "client-override",
            "confirmed_at": "2026-08-06T12:00:00+09:00",
            "axis": "x",
            "pixel_points": [[1200, 900], [8400, 900]],
            "real_length": "35.0",
            "unit": "m",
        }
        request = Request(
            server.calibration_url,
            data=json.dumps(payload).encode("utf-8"),
            method="POST",
            headers={"Content-Type": "application/json", "Origin": server.origin},
        )
        with pytest.raises(HTTPError) as captured:
            urlopen(request, timeout=5)

    assert captured.value.code == 409
    assert json.loads(captured.value.read()) == {"error": "BINDING_MISMATCH"}
    assert not (case_dir / "calibrations").exists()


def test_calibration_post_is_create_only_and_returns_bound_packet_url(tmp_path: Path) -> None:
    case_dir = tmp_path / "CASE-001"
    case_dir.mkdir()
    candidate = _candidate()
    entry = persist_candidate(case_dir, candidate)

    with serve_annotation_workspace(
        html="<p>annotation</p>",
        case_dir=case_dir,
        page=_page(),
        candidate_entries={candidate.candidate_id: entry},
        token=TOKEN,
        page_image=b"sample-image",
        rule_manifest_sha256=RULE_MANIFEST_SHA256,
    ) as server:
        action_request = Request(
            server.url + "/actions",
            data=_accept_payload(),
            method="POST",
            headers={"Content-Type": "application/json", "Origin": server.origin},
        )
        with urlopen(action_request, timeout=5) as response:
            confirmation = json.loads(response.read())["confirmation"]

        payload = {
            "candidate_id": candidate.candidate_id,
            "confirmation_id": confirmation["artifact_id"],
            "reviewer": "ksh",
            "confirmed_at": "2026-08-06T12:00:00+09:00",
            "axis": "x",
            "pixel_points": [[1200, 900], [8400, 900]],
            "real_length": "35.0",
            "unit": "m",
        }
        body = json.dumps(payload).encode("utf-8")

        def post() -> tuple[int, dict[str, object]]:
            request = Request(
                server.calibration_url,
                data=body,
                method="POST",
                headers={
                    "Content-Type": "application/json",
                    "Origin": server.origin,
                },
            )
            try:
                with urlopen(request, timeout=5) as response:
                    return response.status, json.loads(response.read())
            except Exception as error:
                return error.code, json.loads(error.read())  # type: ignore[attr-defined]

        status, result = post()
        assert status == 201
        calibration = result["calibration"]
        assert isinstance(calibration, dict)
        assert calibration["artifact_id"].startswith("CAL-")
        packet_url = result["packet_url"]
        assert isinstance(packet_url, str)
        assert candidate.candidate_id in packet_url
        assert confirmation["artifact_id"] in packet_url
        assert calibration["artifact_id"] in packet_url

        replay_status, replay = post()
        assert replay_status == 409
        assert replay == {"error": "ALREADY_EXISTS"}
        assert len(list((case_dir / "calibrations").glob("*.json"))) == 1

        with urlopen(result["packet_url"], timeout=5) as response:  # type: ignore[arg-type]
            packet_html = response.read().decode("utf-8")
            assert response.status == 200
        assert "Review Packet v2" in packet_html
        assert "human_decision: null" in packet_html
        assert "data:image/png;base64" in packet_html
        assert candidate.candidate_id in packet_html


def test_calibration_rejects_unsafe_query_and_wrong_origin(tmp_path: Path) -> None:
    case_dir = tmp_path / "CASE-001"
    case_dir.mkdir()
    with serve_annotation_workspace(
        html="<p>annotation</p>",
        case_dir=case_dir,
        page=_page(),
        candidate_entries={},
        token=TOKEN,
    ) as server:
        for suffix in ("?candidate_id=A+1", "?candidate_id=A&candidate_id=B", "?unknown=A"):
            request = Request(server.calibration_url + suffix, method="GET")
            try:
                urlopen(request, timeout=5)
            except Exception as error:
                assert error.code == 400  # type: ignore[attr-defined]
        request = Request(
            server.calibration_url,
            data=b"{}",
            method="POST",
            headers={"Content-Type": "application/json", "Origin": "http://evil.example"},
        )
        try:
            urlopen(request, timeout=5)
        except Exception as error:
            assert error.code == 403  # type: ignore[attr-defined]


def test_calibration_rejects_unsupported_method_with_allow_header(tmp_path: Path) -> None:
    case_dir = tmp_path / "CASE-001"
    case_dir.mkdir()
    with serve_annotation_workspace(
        html="<p>annotation</p>",
        case_dir=case_dir,
        page=_page(),
        candidate_entries={},
        token=TOKEN,
    ) as server:
        connection = http.client.HTTPConnection(server.host, server.port, timeout=5)
        connection.request(
            "PUT",
            f"/calibration/{TOKEN}",
            headers={"Host": server.origin.split("//", 1)[1]},
        )
        response = connection.getresponse()
        assert response.status == 405
        assert response.getheader("Allow") == "GET, POST"
        response.read()
        connection.close()
