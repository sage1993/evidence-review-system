"""Strict browser action contracts for the drawing annotation workspace."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, TypeAlias

from ansim_review.contracts.drawing import Geometry

ExistingActionType = Literal["ACCEPTED", "REJECTED", "EDITED"]
ManualActionType = Literal["CREATED"]


@dataclass(frozen=True, slots=True)
class ExistingCandidateAction:
    action: ExistingActionType
    candidate_id: str
    reviewer: str
    confirmed_at: str
    confirmed_value: str | None
    unit: str | None
    geometry: Geometry | None


@dataclass(frozen=True, slots=True)
class ManualCreateAction:
    action: ManualActionType
    annotation_id: str
    candidate_type: str
    reviewer: str
    confirmed_at: str
    confirmed_value: str | None
    unit: str | None
    geometry: Geometry


AnnotationAction: TypeAlias = ExistingCandidateAction | ManualCreateAction
