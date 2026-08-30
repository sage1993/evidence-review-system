from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from evidence_review import review_question
from evidence_review.canonical_json import dump_bytes
from evidence_review.evidence.ingest import EvidenceSnapshot, ingest_snapshot
from evidence_review.evidence.store import EvidenceStore
from evidence_review.retrieval.index import build_fts_index
from evidence_review.review_question import (
    _append_event,
    prepare_review_question,
    submit_question_track_a,
    submit_question_track_b,
)
from evidence_review.review_run import TrackBContractError


def _workspace(path: Path) -> Path:
    (path / "evidence").mkdir(parents=True)
    with EvidenceStore(path / "evidence" / "evidence.sqlite", create=True) as store:
        ingest_snapshot(
            store,
            EvidenceSnapshot(
                documents=({"id": "DOC1", "title": "주차장 조례"},),
                revisions=(
                    {
                        "id": "REV1",
                        "document_id": "DOC1",
                        "source_hash": "a" * 64,
                        "byte_size": 10,
                        "page_count": 1,
                    },
                ),
                pages=(
                    {
                        "id": "REV1-P1",
                        "revision_id": "REV1",
                        "page_number": 1,
                        "width": 10.0,
                        "height": 10.0,
                    },
                ),
                elements=(
                    {
                        "id": "E1",
                        "revision_id": "REV1",
                        "page_id": "REV1-P1",
                        "page_number": 1,
                        "element_type": "clause",
                        "raw_json": {"text": "주차장은 별표 2에 따른다."},
                        "raw_text": "주차장은 별표 2에 따른다.",
                        "normalized_text": "주차장은 별표 2에 따른다.",
                        "raw_payload_hash": "b" * 64,
                        "bbox": [0, 0, 10, 10],
                        "parser_order": 0,
                    },
                ),
            ),
        )
        build_fts_index(store.require_connection())
    return path


def _track_a(run_directory: Path) -> Path:
    bundle = json.loads((run_directory / "track-a-bundle.json").read_text(encoding="utf-8"))
    citation_id = bundle["evidence"][0]["citation"]["citation_id"]
    output = run_directory / "track-a-attempt-1.json"
    output.write_bytes(
        dump_bytes(
            {
                "run_id": bundle["run_id"],
                "claims": [
                    {
                        "claim_id": "CL1",
                        "text": "주차장은 별표 2에 따른다.",
                        "citation_ids": [citation_id],
                        "numeric_tokens": ["2"],
                        "calculation_result_ids": [],
                        "rule_references": [],
                    }
                ],
                "citations": [citation_id],
                "missing_inputs": [],
                "exceptions": [],
                "conflicts": [],
                "explanation": "근거를 정리한다.",
            }
        )
    )
    return output


def _track_b(run_directory: Path) -> Path:
    output = run_directory / "track-b-attempt-1.json"
    output.write_bytes(
        dump_bytes(
            {
                "run_id": run_directory.name,
                "claim_audits": [
                    {
                        "claim_id": "CL1",
                        "disposition": "ACCEPT",
                        "finding_codes": [],
                        "notes": "",
                    }
                ],
                "overall_disposition": "ACCEPT",
            }
        )
    )
    return output


def test_ers_review_skill_declares_attempt_ownership_contract() -> None:
    repository_root = Path(__file__).parents[2]
    for relative_path in (
        "skills/ers-review/SKILL.md",
        ".agents/skills/ers-review/SKILL.md",
    ):
        skill = (repository_root / relative_path).read_text(encoding="utf-8")

        assert "track-a-attempt-<N>.json" in skill
        assert "track-b-attempt-<N>.json" in skill
        assert "runtime-owned" in skill
        assert "WAITING_TRACK_B" in skill
        assert "FINALIZING" in skill
        assert "do not regenerate" in skill


def test_track_a_next_action_uses_numbered_external_attempt(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path / "workspace")
    prepared = prepare_review_question(workspace, "주차장은 별표 2에 따른다")
    action = json.loads(prepared.next_action_path.read_text(encoding="utf-8"))

    assert action["expected_output"] == "track-a-attempt-1.json"


def test_track_b_next_action_uses_numbered_external_attempt(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path / "workspace")
    prepared = prepare_review_question(workspace, "주차장은 별표 2에 따른다")
    run_directory = workspace / "runs" / prepared.run_id
    submitted = submit_question_track_a(workspace, prepared.run_id, _track_a(run_directory))
    action = json.loads(submitted.next_action_path.read_text(encoding="utf-8"))

    assert action["expected_output"] == "track-b-attempt-1.json"


def test_track_a_regeneration_is_rejected_after_track_a_validates(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path / "workspace")
    prepared = prepare_review_question(workspace, "주차장은 별표 2에 따른다")
    run_directory = workspace / "runs" / prepared.run_id
    first_attempt = _track_a(run_directory)
    submit_question_track_a(workspace, prepared.run_id, first_attempt)
    regenerated = run_directory / "track-a-attempt-2.json"
    regenerated.write_bytes(first_attempt.read_bytes())

    with pytest.raises(ValueError, match="Track A"):
        submit_question_track_a(workspace, prepared.run_id, regenerated)


def test_track_b_regeneration_is_rejected_after_finalizing(
    monkeypatch,
    tmp_path: Path,
) -> None:
    workspace = _workspace(tmp_path / "workspace")
    prepared = prepare_review_question(workspace, "주차장은 별표 2에 따른다")
    run_directory = workspace / "runs" / prepared.run_id
    submit_question_track_a(workspace, prepared.run_id, _track_a(run_directory))
    original = _track_b(run_directory)
    canonical = run_directory / "track-b-output.json"
    canonical.write_bytes(original.read_bytes())

    _append_event(
        run_directory,
        "FINALIZING",
        hashlib.sha256(canonical.read_bytes()).hexdigest(),
    )
    regenerated = run_directory / "track-b-attempt-2.json"
    regenerated.write_bytes(original.read_bytes())

    def fail_if_called(*_args, **_kwargs):
        raise AssertionError("finalizer must not run for regenerated Track B")

    monkeypatch.setattr(review_question, "submit_track_b", fail_if_called)

    with pytest.raises(TrackBContractError) as caught:
        submit_question_track_b(workspace, prepared.run_id, regenerated)

    assert caught.value.reason_code == "TRACK_B_REGENERATION_FORBIDDEN"
