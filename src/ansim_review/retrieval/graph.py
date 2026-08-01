"""Bounded deterministic relation traversal for evidence records."""
from __future__ import annotations

import sqlite3
from collections import deque
from collections.abc import Sequence
from decimal import Decimal

from ansim_review.retrieval.index import load_indexed_hit, require_fresh_index
from ansim_review.retrieval.models import ChannelScore, RetrievalHit

_RELATION_PRIORITY = {
    "exception": 0,
    "parent": 1,
    "cited_clause": 2,
    "rule_source": 3,
    "table": 4,
    "visual": 5,
}


def _channel(relation_type: str, evidence_type: str) -> str:
    if relation_type == "rule_source":
        return "rule_source"
    if relation_type in {"table", "visual"} or evidence_type in {
        "table",
        "visual",
    }:
        return "linked_visual_table"
    return "clause_id"


def traverse_relations(
    connection: sqlite3.Connection,
    seed_ids: Sequence[str],
    depth: int = 1,
) -> tuple[RetrievalHit, ...]:
    """Traverse outgoing evidence links using a bounded breadth-first search."""
    require_fresh_index(connection)
    if depth < 0 or depth > 3:
        raise ValueError("depth must be between 0 and 3")
    if depth == 0:
        return ()

    seeds = tuple(sorted(set(seed_ids)))
    visited = set(seeds)
    queue: deque[tuple[str, int]] = deque((seed, 0) for seed in seeds)
    collected: list[tuple[int, int, str, RetrievalHit]] = []

    while queue:
        source_id, current_depth = queue.popleft()
        if current_depth >= depth:
            continue
        rows = connection.execute(
            """
            SELECT target_id, relation_type
            FROM links
            WHERE source_id = ?
            ORDER BY
                CASE relation_type
                    WHEN 'exception' THEN 0
                    WHEN 'parent' THEN 1
                    WHEN 'cited_clause' THEN 2
                    WHEN 'rule_source' THEN 3
                    WHEN 'table' THEN 4
                    WHEN 'visual' THEN 5
                    ELSE 99
                END,
                target_id
            """,
            (source_id,),
        ).fetchall()
        next_depth = current_depth + 1
        for row in rows:
            target_id = str(row["target_id"])
            relation_type = str(row["relation_type"])
            if target_id in visited:
                continue
            visited.add(target_id)
            provisional = load_indexed_hit(
                connection,
                target_id,
                ChannelScore(
                    "clause_id",
                    Decimal(1) / Decimal(next_depth),
                ),
            )
            if provisional is None:
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
                continue
            priority = _RELATION_PRIORITY.get(relation_type, 99)
            collected.append((next_depth, priority, target_id, hit))
            queue.append((target_id, next_depth))

    collected.sort(key=lambda item: (item[0], item[1], item[2]))
    return tuple(item[3] for item in collected)
