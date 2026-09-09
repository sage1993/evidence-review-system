"""Append-only Matter events with atomic projection updates."""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Final

from evidence_review.canonical_json import dumps
from evidence_review.contracts.formats import MATTER_EVENT_FORMAT
from evidence_review.contracts.validation import (
    expect_int,
    expect_literal,
    expect_mapping,
    expect_string,
    reject_unknown,
    require_fields,
)
from evidence_review.review_matter.projection import MatterProjection, project_event
from evidence_review.review_matter.store import (
    MatterRevisionConflict,
    MatterStore,
)

MATTER_EVENT_VERSION: Final[int] = 1
_EVENT_KIND = re.compile(r"^[A-Z][A-Z0-9_]{0,63}$")


@dataclass(frozen=True, slots=True)
class MatterEvent:
    """One append-only, canonical event payload."""

    kind: str
    payload: Mapping[str, object]

    def __post_init__(self) -> None:
        if not isinstance(self.kind, str) or _EVENT_KIND.fullmatch(self.kind) is None:
            raise ValueError("event kind must be an uppercase machine identifier")
        if not isinstance(self.payload, Mapping):
            raise ValueError("event payload must be an object")
        if not all(isinstance(key, str) for key in self.payload):
            raise ValueError("event payload keys must be strings")
        object.__setattr__(self, "payload", dict(self.payload))


def decode_matter_event(value: object) -> MatterEvent:
    """Decode one strict event document."""
    payload = expect_mapping(value, "matter_event")
    required = {"format", "version", "kind", "payload"}
    require_fields(payload, required, "matter_event")
    reject_unknown(payload, required, "matter_event")
    expect_literal(payload.get("format"), "format", (MATTER_EVENT_FORMAT,))
    version = expect_int(payload.get("version"), "version")
    if version != MATTER_EVENT_VERSION:
        raise ValueError("unsupported matter_event version")
    event_payload = expect_mapping(payload.get("payload"), "payload")
    return MatterEvent(kind=expect_string(payload.get("kind"), "kind"), payload=event_payload)


def matter_event_document(event: MatterEvent) -> dict[str, object]:
    """Return the canonical event document."""
    return {
        "format": MATTER_EVENT_FORMAT,
        "version": MATTER_EVENT_VERSION,
        "kind": event.kind,
        "payload": dict(event.payload),
    }


def append_matter_event(
    store: MatterStore,
    matter_id: str,
    expected_revision: int,
    event: MatterEvent,
) -> MatterProjection:
    """Append an event and its projection in one transaction."""
    if isinstance(expected_revision, bool) or not isinstance(expected_revision, int):
        raise ValueError("expected_revision is required")
    with store.transaction():
        current = store.load(matter_id)
        if current.revision != expected_revision:
            raise MatterRevisionConflict("MATTER_REVISION_CONFLICT")
        last = store.connection.execute(
            """
            SELECT sequence, matter_revision
            FROM matter_events
            WHERE matter_id = ?
            ORDER BY sequence DESC
            LIMIT 1
            """,
            (matter_id,),
        ).fetchone()
        if last is None:
            if current.revision != 1:
                raise ValueError("MATTER_EVENT_REVISION_MISMATCH")
            sequence = 1
        else:
            if last["matter_revision"] != current.revision:
                raise ValueError("MATTER_EVENT_REVISION_MISMATCH")
            sequence = int(last["sequence"]) + 1
        projection = project_event(current, event)
        if projection.revision != current.revision + 1:
            raise ValueError("MATTER_EVENT_REVISION_MISMATCH")
        store.connection.execute(
            """
            INSERT INTO matter_events(matter_id, sequence, matter_revision, event_json)
            VALUES (?, ?, ?, ?)
            """,
            (matter_id, sequence, projection.revision, dumps(matter_event_document(event))),
        )
        store.apply_event_side_effects(matter_id, event)
        store.apply_projection(projection.matter)
    return projection


def list_matter_events(store: MatterStore, matter_id: str) -> tuple[MatterEvent, ...]:
    """Return the complete validated event sequence for one Matter."""
    rows = store.connection.execute(
        """
        SELECT sequence, event_json
        FROM matter_events
        WHERE matter_id = ?
        ORDER BY sequence
        """,
        (matter_id,),
    ).fetchall()
    events: list[MatterEvent] = []
    for index, row in enumerate(rows, start=1):
        if row["sequence"] != index:
            raise ValueError("MATTER_EVENT_SEQUENCE_GAP")
        events.append(decode_matter_event(json.loads(str(row["event_json"]))))
    return tuple(events)
