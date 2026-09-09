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


def test_same_snapshot_has_same_formal_request_identity(tmp_path: Path) -> None:
    workspace, _store, snapshot = _setup_workspace(tmp_path)
    from evidence_review.review_matter.formalization import formalize_snapshot

    first = formalize_snapshot(workspace, snapshot)
    second = formalize_snapshot(workspace, snapshot)

    assert second.run_id == first.run_id
    assert second.status == first.status == "WAITING_TRACK_A"


def _rule(rule_result_id: str) -> dict[str, object]:
    return {
        "rule_result_id": rule_result_id,
        "rule_id": f"RULE-{rule_result_id}",
        "rule_version": "1.0.0",
        "status": "SATISFIED",
        "citations": [],
        "missing_inputs": [],
        "calculation_result_ids": [],
        "reason_codes": [],
        "result_hash": "b" * 64,
    }


def test_unsorted_approved_rule_ids_use_strict_decoder_identity(tmp_path: Path) -> None:
    workspace, _store, snapshot = _setup_workspace(tmp_path)
    from evidence_review.review_matter.formalization import formalize_snapshot

    rules = [_rule("RULE-B"), _rule("RULE-A")]
    first = formalize_snapshot(
        workspace,
        snapshot,
        rules=rules,
        approved_rule_result_ids=["RULE-B", "RULE-A"],
    )
    second = formalize_snapshot(
        workspace,
        snapshot,
        rules=rules,
        approved_rule_result_ids=["RULE-B", "RULE-A"],
    )

    assert first.run_id == second.run_id
    request = json.loads(
        (workspace / "runs" / first.run_id / "review-request.json").read_text(
            encoding="utf-8"
        )
    )
    assert request["approved_rule_result_ids"] == ["RULE-A", "RULE-B"]


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
