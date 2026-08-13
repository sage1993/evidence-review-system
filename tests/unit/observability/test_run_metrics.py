from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from ansim_review.observability.run_metrics import (
    append_stage,
    assert_hard_budgets,
    load_run_metrics,
    make_stage,
    record_external_wait,
)


def _at(seconds: int) -> datetime:
    return datetime(2026, 8, 13, 0, 0, tzinfo=UTC) + timedelta(seconds=seconds)


def test_stage_events_are_append_only_and_retry_counts_follow_failures(tmp_path: Path) -> None:
    run = tmp_path / "runs" / "RUN-0123456789ABCDEF0123"
    run.mkdir(parents=True)

    append_stage(
        run,
        make_stage(
            "retrieval", _at(0), _at(1), duration_ms=1000,
            status="FAILED", reason_code="SQLITE_BUSY"
        ),
    )
    append_stage(
        run,
        make_stage(
            "retrieval", _at(2), _at(3), duration_ms=1000,
            status="FAILED", reason_code="SQLITE_BUSY"
        ),
    )
    append_stage(run, make_stage("retrieval", _at(4), _at(5), duration_ms=1000))

    event_files = sorted((run / "run-metrics-events").glob("*.json"))
    assert len(event_files) == 3
    assert [json.loads(path.read_text(encoding="utf-8"))["attempt"] for path in event_files] == [
        1, 2, 3
    ]
    metrics = load_run_metrics(run)
    assert metrics["format"] == "evidence-review/run-metrics"
    assert metrics["version"] == 1
    assert metrics["retry_count"] == 2
    assert metrics["deterministic_total_ms"] == 3000
    assert metrics["external_wait_total_ms"] == 0
    assert metrics["stages"][0]["reason_code"] == "SQLITE_BUSY"


def test_normal_resume_is_not_counted_as_retry(tmp_path: Path) -> None:
    run = tmp_path / "runs" / "RUN-0123456789ABCDEF0123"
    run.mkdir(parents=True)
    append_stage(run, make_stage("prepare", _at(0), _at(1), duration_ms=1000))
    append_stage(run, make_stage("prepare", _at(2), _at(3), duration_ms=1000, status="SKIPPED"))

    assert load_run_metrics(run)["retry_count"] == 0


def test_external_wait_restarts_after_latest_failed_validation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run = tmp_path / "runs" / "RUN-0123456789ABCDEF0123"
    run.mkdir(parents=True)
    append_stage(run, make_stage("prepare", _at(0), _at(1), duration_ms=1000))
    append_stage(
        run,
        make_stage(
            "track-a-validation", _at(2), _at(3), duration_ms=1000,
            status="FAILED", reason_code="VALUEERROR"
        ),
    )
    monkeypatch.setattr(
        "ansim_review.observability.run_metrics.utc_now",
        lambda: _at(8),
    )

    record_external_wait(run, "track-a-external-wait", after_stage="prepare")

    metrics = load_run_metrics(run)
    wait = metrics["stages"][-1]
    assert wait["started_at"] == _at(3).isoformat()
    assert wait["duration_ms"] == 5000
    assert metrics["external_wait_total_ms"] == 5000


def test_external_wait_is_excluded_from_deterministic_total(tmp_path: Path) -> None:
    run = tmp_path / "runs" / "RUN-0123456789ABCDEF0123"
    run.mkdir(parents=True)
    append_stage(run, make_stage("prepare", _at(0), _at(1), duration_ms=900))
    append_stage(
        run,
        make_stage(
            "track-a-external-wait", _at(1), _at(11),
            duration_ms=10_000, external_wait=True
        ),
    )
    metrics = load_run_metrics(run)
    assert metrics["deterministic_total_ms"] == 900
    assert metrics["external_wait_total_ms"] == 10_000


def test_metrics_resume_from_create_only_events(tmp_path: Path) -> None:
    run = tmp_path / "runs" / "RUN-0123456789ABCDEF0123"
    run.mkdir(parents=True)
    append_stage(run, make_stage("prepare", _at(0), _at(1), duration_ms=1000))
    first = load_run_metrics(run)
    append_stage(run, make_stage("track-a-validation", _at(2), _at(3), duration_ms=1000))
    second = load_run_metrics(run)
    assert len(first["stages"]) == 1
    assert [stage["name"] for stage in second["stages"]] == ["prepare", "track-a-validation"]
    assert (run / "run-metrics.json").is_file()


def test_hard_budget_checks_deterministic_and_browser_handoff(tmp_path: Path) -> None:
    run = tmp_path / "runs" / "RUN-0123456789ABCDEF0123"
    run.mkdir(parents=True)
    append_stage(run, make_stage("finalizer", _at(0), _at(2), duration_ms=2000))
    append_stage(run, make_stage("protected-server-start", _at(2), _at(3), duration_ms=1000))
    append_stage(run, make_stage("browser-dispatch", _at(3), _at(4), duration_ms=1000))
    assert_hard_budgets(load_run_metrics(run))

    append_stage(run, make_stage("view-model-build", _at(4), _at(7), duration_ms=3001))
    with pytest.raises(RuntimeError, match="deterministic review budget exceeded"):
        assert_hard_budgets(load_run_metrics(run))
