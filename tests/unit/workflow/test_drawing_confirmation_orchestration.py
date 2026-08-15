from __future__ import annotations

import hashlib

import pytest

from evidence_review.workflow.drawing_confirmation import (
    build_drawing_confirmation_plan,
    confirmation_plan_document,
    persist_drawing_confirmation_plan,
)


def test_drawing_confirmation_plan_blocks_engines_until_inputs_are_verified() -> None:
    plan = build_drawing_confirmation_plan(
        run_id="RUN-001",
        candidate_ids=("CAND-001",),
        source_sha256="a" * 64,
        has_source=True,
        has_validated_inputs=False,
    )

    assert plan.workflow_state == "INPUT_CONFIRMATION_REQUIRED"
    assert plan.engine_allowed is False
    assert plan.candidate_urls == ("/runs/RUN-001/confirmation/CAND-001",)
    assert confirmation_plan_document(plan)["source_sha256"] == "a" * 64


def test_verified_confirmation_plan_allows_engine_entry() -> None:
    plan = build_drawing_confirmation_plan(
        run_id="RUN-001",
        candidate_ids=("CAND-001",),
        source_sha256="a" * 64,
        has_source=True,
        has_validated_inputs=True,
        confirmed_inputs_sha256=hashlib.sha256(b"confirmed").hexdigest(),
    )

    assert plan.workflow_state == "READY_TO_EVALUATE"
    assert plan.engine_allowed is True


def test_source_hash_change_invalidates_existing_confirmation() -> None:
    with pytest.raises(ValueError, match="SOURCE_HASH_MISMATCH"):
        build_drawing_confirmation_plan(
            run_id="RUN-001",
            candidate_ids=("CAND-001",),
            source_sha256="b" * 64,
            previous_source_sha256="a" * 64,
            has_source=True,
            has_validated_inputs=True,
            confirmed_inputs_sha256="c" * 64,
        )


def test_plan_persistence_is_create_only(tmp_path) -> None:
    plan = build_drawing_confirmation_plan(
        run_id="RUN-001",
        candidate_ids=("CAND-001",),
        source_sha256="a" * 64,
        has_source=True,
        has_validated_inputs=False,
    )
    path = persist_drawing_confirmation_plan(tmp_path, plan)
    assert path.read_bytes().endswith(b"\n") is False
    with pytest.raises(FileExistsError):
        persist_drawing_confirmation_plan(tmp_path, plan)
