from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path

import pytest

from evidence_review.review_packet.formal_response import (
    build_formal_response,
    validate_formal_response,
)
from evidence_review.review_run import finalize_review_run, prepare_review_run
from tests.integration.review_run.test_review_run import (
    _workspace,
    _write_request,
    _write_tracks,
)


@pytest.fixture
def finalized(tmp_path: Path):
    workspace = _workspace(tmp_path / "workspace")
    prepared = prepare_review_run(workspace, _write_request(tmp_path / "request.json"))
    track_a, track_b = _write_tracks(tmp_path, prepared.run_id)
    result = finalize_review_run(workspace, prepared.run_id, track_a, track_b)
    return workspace, result


def test_formal_response_has_exact_claim_and_evidence_lineage(finalized) -> None:
    workspace, result = finalized
    before = result.packet_path.read_bytes()
    response = build_formal_response(workspace, result.run_id)
    assert response["packet_sha256"] == hashlib.sha256(before).hexdigest()
    assert response["status"] == result.packet.status
    statement = response["statements"][0]
    assert statement["classification"] == "FORMAL_FINDING"
    assert statement["text"] == result.packet.claims[0].text
    assert statement["claim_id"] == result.packet.claims[0].claim_id
    assert statement["citations"][0]["evidence_id"] == "E1"
    assert validate_formal_response(response, workspace, result.run_id) == response
    assert result.packet_path.read_bytes() == before


@pytest.mark.parametrize("mutation", [
    "text", "claim_id", "citation", "packet_hash", "run_id",
    "SUPPLEMENTARY_EXTERNAL_CHECK", "UNBOUND_ANALYSIS", "extra_field",
    "boolean_version",
])
def test_unbound_formal_response_is_rejected(finalized, mutation: str) -> None:
    workspace, result = finalized
    response = copy.deepcopy(build_formal_response(workspace, result.run_id))
    statement = response["statements"][0]
    if mutation in {"text", "claim_id"}:
        statement[mutation] += " unbound assertion"
    elif mutation == "citation":
        statement["citations"][0]["evidence_id"] = "UNBOUND"
    elif mutation == "packet_hash":
        response["packet_sha256"] = "0" * 64
    elif mutation == "run_id":
        response["run_id"] = "RUN-OTHER"
    elif mutation == "extra_field":
        response["conclusion"] = "법적 적합성이 확정됨"
    elif mutation == "boolean_version":
        response["version"] = True
    else:
        statement["classification"] = mutation
    with pytest.raises(ValueError, match="packet|formal|bound"):
        validate_formal_response(response, workspace, result.run_id)


def test_response_cli_emits_bound_claims_without_mutating_run(finalized, capsys) -> None:
    from evidence_review.cli import main

    workspace, result = finalized
    before = {path.name: path.read_bytes() for path in result.run_directory.iterdir()
              if path.is_file()}
    assert main([
        "review-run", "response", "--workspace", str(workspace),
        "--run-id", result.run_id,
    ]) == 0
    response = json.loads(capsys.readouterr().out)
    assert response == build_formal_response(workspace, result.run_id)
    assert before == {path.name: path.read_bytes() for path in result.run_directory.iterdir()
                      if path.is_file()}
