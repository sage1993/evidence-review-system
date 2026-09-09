from __future__ import annotations

import json
from pathlib import Path

import pytest

from evidence_review.canonical_json import dump_bytes
from evidence_review.review_matter.scope import review_scope_document
from evidence_review.review_matter.snapshot import create_formalization_snapshot


def _setup_workspace(tmp_path: Path) -> tuple[Path, object, object]:
    from tests.unit.review_matter.test_formalization_snapshot import (
        _evidence_database,
        _matter_store,
    )

    workspace = tmp_path / "workspace"
    evidence_db = workspace / "evidence" / "evidence.sqlite"
    evidence_db.parent.mkdir(parents=True)
    provenance = _evidence_database(evidence_db)
    provenance["database_path"] = str(evidence_db)
    store = _matter_store(workspace / "matter.sqlite", provenance)
    snapshot = create_formalization_snapshot(store, "MATTER-SNAP-1", 2, evidence_db)
    return workspace, store, snapshot


def _track_a_output(run_directory: Path, *, issue_ids: list[str] | None = None) -> Path:
    bundle = json.loads(
        (run_directory / "track-a-bundle.json").read_text(encoding="utf-8")
    )
    citation_id = bundle["evidence"][0]["citation"]["citation_id"]
    output = run_directory / "track-a-attempt-1.json"
    output.write_bytes(
        dump_bytes(
            {
                "run_id": bundle["run_id"],
                "claims": [
                    {
                        "claim_id": "CL-1",
                        "text": "Exact reference text",
                        "issue_ids": issue_ids or [],
                        "citation_ids": [citation_id],
                        "numeric_tokens": [],
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


def test_persisted_snapshot_adapts_to_existing_strict_formal_core_without_matter_write(
    tmp_path: Path,
) -> None:
    workspace, store, snapshot = _setup_workspace(tmp_path)
    before_matter = store.load("MATTER-SNAP-1")
    before_events = store.list_events("MATTER-SNAP-1")
    before_bindings = before_matter.source_bindings

    from evidence_review.review_matter.formalization import formalize_snapshot

    prepared = formalize_snapshot(workspace, snapshot)

    assert prepared.status == "WAITING_TRACK_A"
    request_path = workspace / "runs" / prepared.run_id / "review-request.json"
    request = json.loads(request_path.read_text(encoding="utf-8"))
    assert request["inputs"]["formalization_snapshot_id"] == snapshot.snapshot_id
    assert request["inputs"]["matter_id"] == snapshot.matter_id
    assert request["inputs"]["matter_revision"] == snapshot.matter_revision
    assert len(request["evidence"]) == len(snapshot.selected_evidence)
    assert store.load("MATTER-SNAP-1") == before_matter
    assert store.list_events("MATTER-SNAP-1") == before_events
    assert store.load("MATTER-SNAP-1").source_bindings == before_bindings


def test_formalization_uses_existing_track_a_handoff(tmp_path: Path) -> None:
    workspace, _store, snapshot = _setup_workspace(tmp_path)
    from evidence_review.review_matter.formalization import formalize_snapshot
    from evidence_review.workflow.events import load_workflow_events

    prepared = formalize_snapshot(workspace, snapshot)
    run_directory = workspace / "runs" / prepared.run_id

    assert prepared.next_action_path == run_directory / "next-action-track-a.json"
    assert prepared.next_action_path.is_file()
    assert load_workflow_events(run_directory / "events")[-1].next_state == (
        "WAITING_TRACK_A"
    )


def test_formalization_handoff_can_submit_track_a(tmp_path: Path) -> None:
    workspace, _store, snapshot = _setup_workspace(tmp_path)
    from evidence_review.review_matter.formalization import formalize_snapshot
    from evidence_review.review_question import submit_question_track_a

    prepared = formalize_snapshot(workspace, snapshot)
    run_directory = workspace / "runs" / prepared.run_id
    bundle = json.loads(
        (run_directory / "track-a-bundle.json").read_text(encoding="utf-8")
    )
    issue_id = bundle["inputs"]["question_plan"]["issues"][0]["id"]

    submitted = submit_question_track_a(
        workspace,
        prepared.run_id,
        _track_a_output(run_directory, issue_ids=[issue_id]),
    )

    assert submitted.next_action_path == run_directory / "next-action-track-b.json"


def test_formalization_review_scope_requires_track_a_issue_relevance(
    tmp_path: Path,
) -> None:
    workspace, _store, snapshot = _setup_workspace(tmp_path)
    from evidence_review.review_matter.formalization import formalize_snapshot
    from evidence_review.review_question import submit_question_track_a

    prepared = formalize_snapshot(workspace, snapshot)
    run_directory = workspace / "runs" / prepared.run_id

    with pytest.raises(ValueError, match="UNRELATED_CLAIM"):
        submit_question_track_a(
            workspace,
            prepared.run_id,
            _track_a_output(run_directory),
        )


def test_same_snapshot_has_same_formal_request_identity(tmp_path: Path) -> None:
    workspace, _store, snapshot = _setup_workspace(tmp_path)
    from evidence_review.review_matter.formalization import formalize_snapshot

    first = formalize_snapshot(workspace, snapshot)
    second = formalize_snapshot(workspace, snapshot)

    assert second.run_id == first.run_id
    assert second.status == first.status == "WAITING_TRACK_A"


def test_formalization_rejects_caller_supplied_authority_inputs(tmp_path: Path) -> None:
    workspace, _store, snapshot = _setup_workspace(tmp_path)
    from evidence_review.review_matter.formalization import formalize_snapshot

    with pytest.raises(TypeError):
        formalize_snapshot(
            workspace,
            snapshot,
            calculations=[{"calculation_result_id": "CALC-DRAFT"}],
            rules=[{"rule_result_id": "RULE-DRAFT"}],
            approved_rule_result_ids=["RULE-DRAFT"],
        )


def test_prepared_request_preserves_canonical_review_scope_bytes(tmp_path: Path) -> None:
    workspace, _store, snapshot = _setup_workspace(tmp_path)
    from evidence_review.review_matter.formalization import formalize_snapshot

    prepared = formalize_snapshot(workspace, snapshot)
    request = json.loads(
        (workspace / "runs" / prepared.run_id / "review-request.json").read_text(
            encoding="utf-8"
        )
    )
    expected_scope = review_scope_document(snapshot.review_scope)

    assert dump_bytes(request["inputs"]["review_scope"]) == dump_bytes(expected_scope)


def test_malformed_review_scope_is_rejected_before_preparation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    workspace, _store, snapshot = _setup_workspace(tmp_path)
    from evidence_review.review_matter import formalization

    original_scope_document = formalization.review_scope_document

    def malformed_scope(scope: object) -> dict[str, object]:
        document = original_scope_document(scope)
        document["issues"] = [dict(document["issues"][0])]
        document["issues"][0].pop("question")
        return document

    monkeypatch.setattr(formalization, "review_scope_document", malformed_scope)

    with pytest.raises(ValueError, match="FORMALIZATION_REVIEW_SCOPE"):
        formalization.formalize_snapshot(workspace, snapshot)

    assert not (workspace / "runs").exists()


def test_track_a_bundle_preserves_canonical_review_scope_bytes(tmp_path: Path) -> None:
    workspace, _store, snapshot = _setup_workspace(tmp_path)
    from evidence_review.review_matter.formalization import formalize_snapshot

    prepared = formalize_snapshot(workspace, snapshot)
    bundle = json.loads(
        (workspace / "runs" / prepared.run_id / "track-a-bundle.json").read_text(
            encoding="utf-8"
        )
    )
    expected_scope = review_scope_document(snapshot.review_scope)

    assert dump_bytes(bundle["inputs"]["review_scope"]) == dump_bytes(expected_scope)


def test_tampered_prepared_track_a_scope_fails_before_resume(tmp_path: Path) -> None:
    workspace, _store, snapshot = _setup_workspace(tmp_path)
    from evidence_review.review_matter.formalization import formalize_snapshot

    prepared = formalize_snapshot(workspace, snapshot)
    bundle_path = workspace / "runs" / prepared.run_id / "track-a-bundle.json"
    bundle = json.loads(bundle_path.read_text(encoding="utf-8"))
    bundle["inputs"]["review_scope"] = {"tampered": True}
    bundle_path.write_bytes(dump_bytes(bundle))

    with pytest.raises(ValueError, match="FORMALIZATION_REVIEW_SCOPE"):
        formalize_snapshot(workspace, snapshot)


def test_tampered_prepared_track_a_content_fails_before_resume(tmp_path: Path) -> None:
    workspace, _store, snapshot = _setup_workspace(tmp_path)
    from evidence_review.review_matter.formalization import formalize_snapshot

    prepared = formalize_snapshot(workspace, snapshot)
    bundle_path = workspace / "runs" / prepared.run_id / "track-a-bundle.json"
    bundle = json.loads(bundle_path.read_text(encoding="utf-8"))
    bundle["question"] = "tampered question"
    bundle_path.write_bytes(dump_bytes(bundle))

    with pytest.raises(ValueError, match="FORMALIZATION_PREPARED_TRACK_A"):
        formalize_snapshot(workspace, snapshot)


@pytest.mark.parametrize(
    ("artifact_name", "replacement"),
    [
        ("next-action-track-a.json", b'{"tampered":true}'),
        ("TRACK_A_INSTRUCTIONS.md", b"tampered"),
        ("TRACK_B_INSTRUCTIONS.md", b"tampered"),
        ("prepare-status.json", b'{"tampered":true}'),
    ],
)
def test_tampered_prepared_contract_artifact_fails_before_resume(
    tmp_path: Path, artifact_name: str, replacement: bytes
) -> None:
    """Catch a resume check that validates only Track A input artifacts."""
    workspace, _store, snapshot = _setup_workspace(tmp_path)
    from evidence_review.review_matter.formalization import formalize_snapshot

    prepared = formalize_snapshot(workspace, snapshot)
    artifact_path = workspace / "runs" / prepared.run_id / artifact_name
    artifact_path.write_bytes(replacement)

    with pytest.raises(ValueError, match="FORMALIZATION_PREPARED_"):
        formalize_snapshot(workspace, snapshot)


def test_matter_revision_change_before_preparation_cannot_create_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    workspace, store, snapshot = _setup_workspace(tmp_path)
    from evidence_review.review_matter import formalization

    original_request = formalization._request_document

    def change_matter_before_boundary(*args: object, **kwargs: object) -> dict[str, object]:
        store.rename("MATTER-SNAP-1", expected_revision=2, title="Concurrent change")
        return original_request(*args, **kwargs)

    monkeypatch.setattr(formalization, "_request_document", change_matter_before_boundary)

    with pytest.raises(ValueError, match="MATTER_CHANGED_DURING_FORMALIZATION"):
        formalization.formalize_snapshot(workspace, snapshot)

    assert not (workspace / "runs").exists()


def test_evidence_provenance_drift_after_selection_fails_before_run_creation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    workspace, _store, snapshot = _setup_workspace(tmp_path)
    from evidence_review.review_matter import formalization

    original_provenance = formalization.finalized_evidence_provenance
    calls = 0

    def drift_after_selection(path: Path) -> dict[str, object]:
        nonlocal calls
        calls += 1
        provenance = dict(original_provenance(path))
        if calls == 2:
            provenance["evidence_db_sha256"] = "f" * 64
        return provenance

    monkeypatch.setattr(
        formalization, "finalized_evidence_provenance", drift_after_selection
    )

    with pytest.raises(ValueError, match="FORMALIZATION_EVIDENCE_PROVENANCE_MISMATCH"):
        formalization.formalize_snapshot(workspace, snapshot)

    assert calls == 2
    assert not (workspace / "runs").exists()


def test_evidence_provenance_drift_after_preparation_removes_new_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    workspace, _store, snapshot = _setup_workspace(tmp_path)
    from evidence_review.review_matter import formalization

    original_provenance = formalization.finalized_evidence_provenance
    calls = 0

    def drift_after_preparation(evidence_db: Path) -> dict[str, object]:
        nonlocal calls
        calls += 1
        provenance = dict(original_provenance(evidence_db))
        if calls == 4:
            provenance["evidence_db_sha256"] = "f" * 64
        return provenance

    monkeypatch.setattr(
        formalization,
        "finalized_evidence_provenance",
        drift_after_preparation,
    )

    with pytest.raises(ValueError, match="FORMALIZATION_EVIDENCE_PROVENANCE_MISMATCH"):
        formalization.formalize_snapshot(workspace, snapshot)

    assert calls == 4
    assert not (workspace / "runs").exists()


def test_missing_or_tampered_persisted_snapshot_fails_closed(tmp_path: Path) -> None:
    workspace, store, snapshot = _setup_workspace(tmp_path)
    from evidence_review.review_matter.formalization import formalize_snapshot

    store.connection.execute(
        "UPDATE formalization_snapshots SET canonical_document = ? WHERE snapshot_id = ?",
        (b"{}", snapshot.snapshot_id),
    )
    store.connection.commit()

    with pytest.raises(ValueError, match="SNAPSHOT|snapshot"):
        formalize_snapshot(workspace, snapshot)
