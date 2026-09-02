"""Append-only local timing telemetry for review runs.

The event directory is the source of truth. ``run-metrics.json`` is a derived,
non-authoritative snapshot and is deliberately excluded from run/packet hashes.
Once the first browser handoff completes, formal/release metrics are frozen at
that boundary while later operational events remain in the append-only event log.
"""
from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal, cast
from uuid import uuid4

from evidence_review.canonical_json import dump_bytes

StageStatus = Literal["COMPLETED", "FAILED", "SKIPPED"]

_EXTERNAL_WAIT_STAGES = {"track-a-external-wait", "track-b-external-wait"}
_BROWSER_HANDOFF_STAGES = {"protected-server-start", "browser-dispatch"}


@dataclass(frozen=True, slots=True)
class StageTimer:
    started_at: datetime
    started_ns: int


@dataclass(frozen=True, slots=True)
class CompletedStage:
    name: str
    started_at: datetime
    finished_at: datetime
    duration_ms: int
    status: StageStatus = "COMPLETED"
    reason_code: str | None = None
    external_wait: bool = False


def utc_now() -> datetime:
    return datetime.now(UTC)


def start_stage() -> StageTimer:
    return StageTimer(started_at=utc_now(), started_ns=time.perf_counter_ns())


def finish_stage(
    name: str,
    timer: StageTimer,
    *,
    status: StageStatus = "COMPLETED",
    reason_code: str | None = None,
    external_wait: bool = False,
) -> CompletedStage:
    finished_at = utc_now()
    duration_ms = max(0, (time.perf_counter_ns() - timer.started_ns) // 1_000_000)
    return make_stage(
        name,
        timer.started_at,
        finished_at,
        duration_ms=duration_ms,
        status=status,
        reason_code=reason_code,
        external_wait=external_wait,
    )


def make_stage(
    name: str,
    started_at: datetime,
    finished_at: datetime,
    *,
    duration_ms: int,
    status: StageStatus = "COMPLETED",
    reason_code: str | None = None,
    external_wait: bool = False,
) -> CompletedStage:
    if not isinstance(name, str) or not name:
        raise ValueError("stage name must be a non-empty string")
    if started_at.tzinfo is None or started_at.utcoffset() is None:
        raise ValueError("started_at must be offset-aware")
    if finished_at.tzinfo is None or finished_at.utcoffset() is None:
        raise ValueError("finished_at must be offset-aware")
    if finished_at < started_at:
        raise ValueError("finished_at must not precede started_at")
    if isinstance(duration_ms, bool) or not isinstance(duration_ms, int) or duration_ms < 0:
        raise ValueError("duration_ms must be a non-negative integer")
    if status not in {"COMPLETED", "FAILED", "SKIPPED"}:
        raise ValueError("unsupported stage status")
    if reason_code is not None and (
        not isinstance(reason_code, str) or not reason_code
    ):
        raise ValueError("reason_code must be null or a non-empty string")
    return CompletedStage(
        name=name,
        started_at=started_at,
        finished_at=finished_at,
        duration_ms=duration_ms,
        status=status,
        reason_code=reason_code,
        external_wait=external_wait or name in _EXTERNAL_WAIT_STAGES,
    )


def _events_directory(run_directory: Path) -> Path:
    directory = run_directory / "run-metrics-events"
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def _event_documents(run_directory: Path) -> list[dict[str, object]]:
    directory = run_directory / "run-metrics-events"
    if not directory.exists():
        return []
    documents: list[dict[str, object]] = []
    for path in sorted(directory.glob("*.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError(f"invalid run metrics event: {path.name}")
        documents.append(cast(dict[str, object], payload))
    documents.sort(
        key=lambda item: (
            str(item.get("started_at", "")),
            str(item.get("finished_at", "")),
            str(item.get("event_id", "")),
        )
    )
    return documents


def _formal_stages(stages: list[dict[str, object]]) -> list[dict[str, object]]:
    """Return the immutable formal-run prefix ending at first successful handoff."""
    for index, item in enumerate(stages):
        if item.get("name") == "browser-dispatch" and item.get("status") == "COMPLETED":
            return stages[: index + 1]
    return stages


def _duration_ms(item: dict[str, object]) -> int:
    value = item.get("duration_ms")
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError("run metrics duration_ms is invalid")
    return value


def _finished_at(item: dict[str, object]) -> datetime:
    value = item.get("finished_at")
    if not isinstance(value, str):
        raise ValueError("run metrics finished_at is invalid")
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("run metrics finished_at must be offset-aware")
    return parsed


def has_stage(run_directory: Path, name: str) -> bool:
    return any(item.get("name") == name for item in _event_documents(run_directory))


def append_stage(run_directory: Path, stage: CompletedStage) -> Path:
    run_id = run_directory.name
    attempts = sum(
        1 for item in _event_documents(run_directory) if item.get("name") == stage.name
    )
    attempt = attempts + 1
    event_id = f"METRIC-{time.time_ns()}-{os.getpid()}-{uuid4().hex[:12]}"
    document = {
        "event_id": event_id,
        "run_id": run_id,
        "name": stage.name,
        "attempt": attempt,
        "status": stage.status,
        "started_at": stage.started_at.isoformat(),
        "finished_at": stage.finished_at.isoformat(),
        "duration_ms": stage.duration_ms,
        "reason_code": stage.reason_code,
        "external_wait": stage.external_wait,
    }
    path = _events_directory(run_directory) / f"{event_id}.json"
    with path.open("xb") as stream:
        stream.write(dump_bytes(document))
    write_metrics_snapshot(run_directory)
    return path


def record_external_wait(
    run_directory: Path,
    name: str,
    *,
    after_stage: str,
) -> Path:
    """Measure only time outside deterministic work since the latest completed boundary."""
    documents = _event_documents(run_directory)
    if not any(item.get("name") == after_stage for item in documents):
        raise ValueError(f"external wait requires prior stage: {after_stage}")
    deterministic = [
        item for item in documents if not bool(item.get("external_wait", False))
    ]
    finished_at = utc_now()
    started_at = max((_finished_at(item) for item in deterministic), default=finished_at)
    if started_at > finished_at:
        started_at = finished_at
    duration_ms = max(0, int((finished_at - started_at).total_seconds() * 1000))
    return append_stage(
        run_directory,
        make_stage(
            name,
            started_at,
            finished_at,
            duration_ms=duration_ms,
            external_wait=True,
        ),
    )


def _retry_count(stages: list[dict[str, object]]) -> int:
    previous_by_name: dict[str, str] = {}
    retries = 0
    for item in stages:
        name = item.get("name")
        status = item.get("status")
        if not isinstance(name, str) or not isinstance(status, str):
            continue
        if previous_by_name.get(name) == "FAILED":
            retries += 1
        previous_by_name[name] = status
    return retries


def load_run_metrics(run_directory: Path) -> dict[str, object]:
    stages = _formal_stages(_event_documents(run_directory))
    deterministic_total_ms = sum(
        _duration_ms(item)
        for item in stages
        if not bool(item.get("external_wait", False))
    )
    external_wait_total_ms = sum(
        _duration_ms(item)
        for item in stages
        if bool(item.get("external_wait", False))
    )
    public_stages = [
        {
            "name": item.get("name"),
            "attempt": item.get("attempt"),
            "status": item.get("status"),
            "started_at": item.get("started_at"),
            "finished_at": item.get("finished_at"),
            "duration_ms": item.get("duration_ms"),
            "reason_code": item.get("reason_code"),
        }
        for item in stages
    ]
    return {
        "format": "evidence-review/run-metrics",
        "version": 1,
        "run_id": run_directory.name,
        "stages": public_stages,
        "deterministic_total_ms": deterministic_total_ms,
        "external_wait_total_ms": external_wait_total_ms,
        "retry_count": _retry_count(stages),
    }


def write_metrics_snapshot(run_directory: Path) -> Path:
    destination = run_directory / "run-metrics.json"
    temporary = run_directory / f".run-metrics-{os.getpid()}-{uuid4().hex}.tmp"
    temporary.write_bytes(dump_bytes(load_run_metrics(run_directory)))
    os.replace(temporary, destination)
    return destination


def assert_hard_budgets(
    metrics: dict[str, object],
    *,
    deterministic_budget_ms: int = 5000,
    browser_handoff_budget_ms: int = 2000,
) -> None:
    deterministic = metrics.get("deterministic_total_ms")
    if not isinstance(deterministic, int) or isinstance(deterministic, bool):
        raise ValueError("metrics deterministic_total_ms is invalid")
    if deterministic > deterministic_budget_ms:
        raise RuntimeError(
            "deterministic review budget exceeded: "
            f"{deterministic}ms > {deterministic_budget_ms}ms"
        )
    stages = metrics.get("stages")
    if not isinstance(stages, list):
        raise ValueError("metrics stages is invalid")
    handoff = 0
    for item in stages:
        if not isinstance(item, dict):
            raise ValueError("metrics stage is invalid")
        if (
            item.get("name") in _BROWSER_HANDOFF_STAGES
            and item.get("status") == "COMPLETED"
        ):
            duration = item.get("duration_ms")
            if isinstance(duration, bool) or not isinstance(duration, int) or duration < 0:
                raise ValueError("metrics stage duration_ms is invalid")
            handoff += duration
    if handoff > browser_handoff_budget_ms:
        raise RuntimeError(
            f"browser handoff budget exceeded: {handoff}ms > {browser_handoff_budget_ms}ms"
        )


__all__ = [
    "CompletedStage",
    "StageTimer",
    "append_stage",
    "assert_hard_budgets",
    "finish_stage",
    "has_stage",
    "load_run_metrics",
    "make_stage",
    "record_external_wait",
    "start_stage",
    "utc_now",
    "write_metrics_snapshot",
]
