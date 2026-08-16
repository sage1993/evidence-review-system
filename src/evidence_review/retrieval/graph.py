"""Bounded deterministic relation traversal for evidence records."""
from __future__ import annotations

import sqlite3
from collections import deque
from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal

from evidence_review.retrieval.index import load_indexed_hit, require_fresh_index
from evidence_review.retrieval.models import ChannelScore, RetrievalHit

_RELATION_PRIORITY = {
    "exception": 0,
    "parent": 1,
    "next_sibling": 2,
    "previous_sibling": 2,
    "cited_clause": 3,
    "rule_source": 4,
    "source_not_ingested": 5,
    "reference_target_missing": 6,
    "table": 7,
    "visual": 8,
}


@dataclass(frozen=True, slots=True)
class ReferenceStep:
    source_id: str
    target_id: str
    relation_type: str
    depth: int


@dataclass(frozen=True, slots=True)
class ReferencePath:
    target_id: str
    steps: tuple[ReferenceStep, ...]


@dataclass(frozen=True, slots=True)
class MissingReference:
    source_id: str
    target_id: str
    relation_type: str
    depth: int
    reason_code: str


@dataclass(frozen=True, slots=True)
class ReferenceTraversalResult:
    hits: tuple[RetrievalHit, ...]
    paths: tuple[ReferencePath, ...]
    missing: tuple[MissingReference, ...]


def _channel(relation_type: str, evidence_type: str) -> str:
    if relation_type == "rule_source":
        return "rule_source"
    if relation_type in {"next_sibling", "previous_sibling"}:
        return "structural_context"
    if relation_type in {"table", "visual"} or evidence_type in {
        "table",
        "visual",
    }:
        return "linked_visual_table"
    return "clause_id"


def _missing_reason(relation_type: str) -> str:
    if relation_type == "source_not_ingested":
        return "SOURCE_NOT_INGESTED"
    return "REFERENCE_TARGET_MISSING"


def _same_document_stale_revision(
    source: RetrievalHit | None,
    target: RetrievalHit,
) -> bool:
    if source is None:
        return False
    return (
        source.document_id == target.document_id
        and source.revision_id != target.revision_id
    )


def traverse_relations_with_provenance(
    connection: sqlite3.Connection,
    seed_ids: Sequence[str],
    *,
    depth: int = 1,
    max_nodes: int = 12,
    max_fanout: int = 6,
) -> ReferenceTraversalResult:
    """Traverse outgoing evidence links with hard budgets and provenance.

    The traversal is deterministic breadth-first search. It retains the first
    deterministic path to each target, records typed missing/stale targets,
    rejects stale revisions only within the same document, and allows bounded
    structural sibling and cross-document legal traversal.
    """
    require_fresh_index(connection)
    if depth < 0 or depth > 3:
        raise ValueError("depth must be between 0 and 3")
    if max_nodes < 1:
        raise ValueError("max_nodes must be at least 1")
    if max_fanout < 1:
        raise ValueError("max_fanout must be at least 1")
    if depth == 0:
        return ReferenceTraversalResult(hits=(), paths=(), missing=())

    seeds = tuple(sorted(set(seed_ids)))
    visited = set(seeds)
    queue: deque[tuple[str, int, tuple[ReferenceStep, ...]]] = deque(
        (seed, 0, ()) for seed in seeds
    )
    collected: list[tuple[int, int, str, RetrievalHit, ReferencePath]] = []
    missing: list[MissingReference] = []

    while queue and len(collected) < max_nodes:
        source_id, current_depth, source_path = queue.popleft()
        if current_depth >= depth:
            continue

        source_hit = load_indexed_hit(
            connection,
            source_id,
            ChannelScore("clause_id", Decimal(1)),
        )
        rows = connection.execute(
            """
            SELECT target_id, relation_type
            FROM links
            WHERE source_id = ?
            ORDER BY
                CASE relation_type
                    WHEN 'exception' THEN 0
                    WHEN 'parent' THEN 1
                    WHEN 'next_sibling' THEN 2
                    WHEN 'previous_sibling' THEN 2
                    WHEN 'cited_clause' THEN 3
                    WHEN 'rule_source' THEN 4
                    WHEN 'source_not_ingested' THEN 5
                    WHEN 'reference_target_missing' THEN 6
                    WHEN 'table' THEN 7
                    WHEN 'visual' THEN 8
                    ELSE 99
                END,
                target_id
            LIMIT ?
            """,
            (source_id, max_fanout),
        ).fetchall()
        next_depth = current_depth + 1

        for row in rows:
            if len(collected) >= max_nodes:
                break
            target_id = str(row["target_id"])
            relation_type = str(row["relation_type"])
            if target_id in visited:
                continue
            visited.add(target_id)

            step = ReferenceStep(
                source_id=source_id,
                target_id=target_id,
                relation_type=relation_type,
                depth=next_depth,
            )
            path_steps = source_path + (step,)

            provisional = load_indexed_hit(
                connection,
                target_id,
                ChannelScore(
                    "clause_id",
                    Decimal(1) / Decimal(next_depth),
                ),
            )
            if provisional is None:
                missing.append(
                    MissingReference(
                        source_id=source_id,
                        target_id=target_id,
                        relation_type=relation_type,
                        depth=next_depth,
                        reason_code=_missing_reason(relation_type),
                    )
                )
                continue
            if _same_document_stale_revision(source_hit, provisional):
                missing.append(
                    MissingReference(
                        source_id=source_id,
                        target_id=target_id,
                        relation_type=relation_type,
                        depth=next_depth,
                        reason_code="STALE_SAME_DOCUMENT_REVISION",
                    )
                )
                continue

            channel = _channel(relation_type, provisional.evidence_type)
            hit = load_indexed_hit(
                connection,
                target_id,
                ChannelScore(
                    channel,
                    Decimal(1) / Decimal(next_depth),
                    f"{relation_type}:{source_id}:depth={next_depth}",
                ),
            )
            if hit is None:
                missing.append(
                    MissingReference(
                        source_id=source_id,
                        target_id=target_id,
                        relation_type=relation_type,
                        depth=next_depth,
                        reason_code=_missing_reason(relation_type),
                    )
                )
                continue

            priority = _RELATION_PRIORITY.get(relation_type, 99)
            path = ReferencePath(target_id=target_id, steps=path_steps)
            collected.append((next_depth, priority, target_id, hit, path))
            queue.append((target_id, next_depth, path_steps))

    collected.sort(key=lambda item: (item[0], item[1], item[2]))
    missing.sort(
        key=lambda item: (
            item.depth,
            _RELATION_PRIORITY.get(item.relation_type, 99),
            item.source_id,
            item.target_id,
            item.reason_code,
        )
    )
    return ReferenceTraversalResult(
        hits=tuple(item[3] for item in collected),
        paths=tuple(item[4] for item in collected),
        missing=tuple(missing),
    )


def traverse_relations(
    connection: sqlite3.Connection,
    seed_ids: Sequence[str],
    depth: int = 1,
) -> tuple[RetrievalHit, ...]:
    """Compatibility wrapper for bounded breadth-first relation traversal."""
    return traverse_relations_with_provenance(
        connection,
        seed_ids,
        depth=depth,
    ).hits
