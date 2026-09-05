"""Runtime artifact ownership groups used by recovery paths."""

from __future__ import annotations

IMMUTABLE_INPUTS = frozenset(
    {
        "track-a-output.json",
        "track-b-output.json",
    }
)

TRACK_A_DERIVED = frozenset(
    {
        "track-b-bundle.json",
        "next-action-track-b.json",
        "track-a-validation.json",
    }
)

FINALIZATION_DERIVED = frozenset(
    {
        "run-manifest.json",
        "final-review-packet.json",
        "review.html",
    }
)


__all__ = [
    "FINALIZATION_DERIVED",
    "IMMUTABLE_INPUTS",
    "TRACK_A_DERIVED",
]
