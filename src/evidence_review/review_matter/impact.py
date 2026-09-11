"""Deterministic, conservative source-revision impact evaluation."""

from __future__ import annotations

from collections.abc import Mapping, Sequence, Set
from dataclasses import dataclass
from typing import Literal

from evidence_review.contracts.identifiers import validate_identifier
from evidence_review.contracts.validation import (
    expect_mapping,
    expect_sha256,
    reject_unknown,
    require_fields,
)

ImpactStatus = Literal["UNCHANGED", "STALE", "RECHECK_REQUIRED"]


@dataclass(frozen=True, slots=True)
class ImpactReport:
    """A deterministic impact decision for one proposed source replacement."""

    status: ImpactStatus
    stale_issue_ids: tuple[str, ...]
    retained_issue_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class _SourceIdentity:
    source_id: str
    sha256: str
    revision_id: str | None


def _source_identity(value: object) -> _SourceIdentity | None:
    try:
        payload = expect_mapping(value, "source")
        allowed = {"source_id", "sha256", "revision_id"}
        require_fields(payload, {"source_id", "sha256"}, "source")
        reject_unknown(payload, allowed, "source")
        revision = payload.get("revision_id")
        return _SourceIdentity(
            source_id=validate_identifier(payload.get("source_id"), "source.source_id"),
            sha256=expect_sha256(payload.get("sha256"), "source.sha256"),
            revision_id=(
                validate_identifier(revision, "source.revision_id")
                if revision is not None
                else None
            ),
        )
    except ValueError:
        return None


def _dependency_graph(value: object) -> dict[str, frozenset[str]] | None:
    try:
        payload = expect_mapping(value, "dependencies")
        graph: dict[str, frozenset[str]] = {}
        for raw_issue_id, raw_source_ids in payload.items():
            issue_id = validate_identifier(raw_issue_id, "dependencies.issue_id")
            if isinstance(raw_source_ids, (str, bytes, bytearray, Mapping)) or not isinstance(
                raw_source_ids, (Sequence, Set)
            ):
                raise ValueError("dependencies source identities must be a collection")
            graph[issue_id] = frozenset(
                validate_identifier(
                    source_id, f"dependencies.{issue_id}.source_id"
                )
                for source_id in raw_source_ids
            )
        return graph
    except ValueError:
        return None


def _dependency_issue_ids(value: object) -> tuple[str, ...]:
    try:
        payload = expect_mapping(value, "dependencies")
        return tuple(
            sorted(
                validate_identifier(raw_issue_id, "dependencies.issue_id")
                for raw_issue_id in payload
            )
        )
    except ValueError:
        return ()


def evaluate_source_change_impact(
    before: object,
    after: object,
    dependencies: object,
) -> ImpactReport:
    """Fail closed unless exact source and dependency identities prove retention."""
    source_before = _source_identity(before)
    source_after = _source_identity(after)
    graph = _dependency_graph(dependencies)
    issue_ids = tuple(sorted(graph)) if graph is not None else _dependency_issue_ids(dependencies)

    if source_before is None or source_after is None or graph is None:
        return ImpactReport(
            status="RECHECK_REQUIRED",
            stale_issue_ids=issue_ids,
            retained_issue_ids=(),
        )
    if source_before == source_after:
        return ImpactReport(
            status="UNCHANGED",
            stale_issue_ids=(),
            retained_issue_ids=issue_ids,
        )

    stale_issue_ids = tuple(
        issue_id
        for issue_id in issue_ids
        if source_before.source_id in graph[issue_id]
    )
    retained_issue_ids = tuple(
        issue_id for issue_id in issue_ids if issue_id not in stale_issue_ids
    )
    return ImpactReport(
        status="STALE",
        stale_issue_ids=stale_issue_ids,
        retained_issue_ids=retained_issue_ids,
    )


__all__ = ["ImpactReport", "ImpactStatus", "evaluate_source_change_impact"]
