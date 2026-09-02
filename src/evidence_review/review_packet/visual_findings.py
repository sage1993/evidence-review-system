"""Deterministic semantic grouping for case-specific visual observations."""
from __future__ import annotations

import math
import re
from collections.abc import Mapping, Sequence
from typing import cast

from evidence_review.canonical_json import sha256_json

_SPACE_TERMS = (
    "scenario",
    "침실",
    "거실",
    "주방",
    "식당",
    "욕실",
    "화장실",
    "드레스룸",
    "팬트리",
    "발코니",
    "키즈",
    "수납",
    "현관",
    "세탁",
    "다용도실",
)
_LEVEL_RE = re.compile(
    r"(?:^|[^0-9])\d+\s*f(?:[^a-z]|$)|\b(?:el|gl)\s*[+\-]?\s*\d",
    re.I,
)
_BUILDING_RE = re.compile(r"\b\d{1,4}\s*동\b")
_DISTANCE_RE = re.compile(r"\b\d+(?:\.\d+)?\s*(?:mm|cm|m)\b", re.I)

_CATEGORY_TITLES = {
    "space_program": "공간 구성",
    "area": "면적 구성",
    "dimension": "주요 치수·거리",
    "level": "층수·계획고",
    "building_identity": "동·건축물 식별",
    "visual_observation": "도면 확인사항",
}


def _mapping(value: object, field: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping) or not all(
        isinstance(key, str) for key in value
    ):
        raise ValueError(f"{field} must be an object")
    return cast(Mapping[str, object], value)


def _sequence(value: object, field: str) -> Sequence[object]:
    if isinstance(value, (str, bytes, bytearray)) or not isinstance(
        value, Sequence
    ):
        raise ValueError(f"{field} must be an array")
    return cast(Sequence[object], value)


def _text(value: object) -> str:
    return value.strip() if isinstance(value, str) else ""


def _normalized_phrase(value: object) -> str:
    text = _text(value)
    return re.sub(r"\s+", " ", text).strip().casefold() if text else ""


def _number(value: object, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{field} must be a finite number")
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"{field} must be a finite number")
    return result


def _category(candidate: Mapping[str, object]) -> str:
    candidate_type = _text(candidate.get("candidate_type")).upper()
    value = (
        _text(candidate.get("display_value"))
        or _text(candidate.get("normalized_candidate"))
        or _text(candidate.get("raw_value"))
    )
    folded = value.casefold()
    if _BUILDING_RE.search(value) or "BUILDING" in candidate_type:
        return "building_identity"
    area_terms = ("전용면적", "공용면적", "발코니면적", "생활면적", "확장면적")
    if (
        "㎡" in value
        or "M²" in value.upper()
        or "AREA" in candidate_type
        or any(term in value for term in area_terms)
    ):
        return "area"
    if (
        _LEVEL_RE.search(value)
        or "LEVEL" in candidate_type
        or "ELEVATION" in candidate_type
        or "층수" in value
        or "계획고" in value
    ):
        return "level"
    if any(term in folded for term in _SPACE_TERMS) or any(
        term in candidate_type for term in ("ROOM", "SPACE", "PROGRAM")
    ):
        return "space_program"
    numeric_parts = [
        part.strip() for part in re.split(r"[;,/]", value) if part.strip()
    ]
    has_numeric_series = len(numeric_parts) >= 4 and sum(
        any(ch.isdigit() for ch in item) for item in numeric_parts
    ) >= 4
    if (
        "DIMENSION" in candidate_type
        or "WIDTH" in candidate_type
        or "SETBACK" in candidate_type
        or _DISTANCE_RE.search(value)
        or has_numeric_series
    ):
        return "dimension"
    return "visual_observation"


def _geometry_bounds(
    candidate: Mapping[str, object],
) -> tuple[float, float, float, float]:
    geometry = _mapping(candidate.get("geometry"), "candidate.geometry")
    coordinates = _sequence(
        geometry.get("coordinates"), "candidate.geometry.coordinates"
    )
    geometry_type = str(geometry.get("type", ""))
    points: list[tuple[float, float]] = []
    if geometry_type == "POINT":
        if len(coordinates) != 2:
            raise ValueError("visual POINT coordinates are invalid")
        points.append(
            (
                _number(coordinates[0], "candidate.geometry.x"),
                _number(coordinates[1], "candidate.geometry.y"),
            )
        )
    elif geometry_type == "BBOX":
        if len(coordinates) != 4:
            raise ValueError("visual BBOX coordinates are invalid")
        left, top, right, bottom = (
            _number(item, "candidate.geometry.coordinate") for item in coordinates
        )
        points.extend(((left, top), (right, bottom)))
    else:
        for raw_point in coordinates:
            point = _sequence(raw_point, "candidate.geometry.point")
            if len(point) != 2:
                raise ValueError("visual path coordinates are invalid")
            points.append(
                (
                    _number(point[0], "candidate.geometry.point.x"),
                    _number(point[1], "candidate.geometry.point.y"),
                )
            )
    if not points:
        raise ValueError("visual geometry has no bounds")
    xs = [item[0] for item in points]
    ys = [item[1] for item in points]
    return min(xs), min(ys), max(xs), max(ys)


def _axis_gap(
    first_start: float,
    first_end: float,
    second_start: float,
    second_end: float,
) -> float:
    return max(0.0, max(first_start, second_start) - min(first_end, second_end))


def _spatially_related(
    first: tuple[float, float, float, float],
    second: tuple[float, float, float, float],
) -> bool:
    first_left, first_top, first_right, first_bottom = first
    second_left, second_top, second_right, second_bottom = second
    horizontal_gap = _axis_gap(first_left, first_right, second_left, second_right)
    vertical_gap = _axis_gap(first_top, first_bottom, second_top, second_bottom)

    first_height = max(first_bottom - first_top, 1.0)
    second_height = max(second_bottom - second_top, 1.0)
    first_width = max(first_right - first_left, 1.0)
    second_width = max(second_right - second_left, 1.0)
    text_height = min(first_height, second_height)
    text_width = min(first_width, second_width)

    same_row = (
        vertical_gap <= max(16.0, text_height * 0.75)
        and horizontal_gap <= max(32.0, text_height * 4.0)
    )
    same_column = (
        horizontal_gap <= max(16.0, text_width * 0.25)
        and vertical_gap <= max(32.0, text_height * 2.0)
    )
    return same_row or same_column


def _spatial_components(
    candidates: Sequence[Mapping[str, object]],
) -> list[list[Mapping[str, object]]]:
    if len(candidates) < 2:
        return [list(candidates)]

    bounds = [_geometry_bounds(candidate) for candidate in candidates]
    order = sorted(
        range(len(candidates)),
        key=lambda index: (
            bounds[index][1],
            bounds[index][0],
            _text(candidates[index].get("candidate_id")),
        ),
    )
    visited: set[int] = set()
    components: list[list[Mapping[str, object]]] = []
    for start in order:
        if start in visited:
            continue
        visited.add(start)
        pending = [start]
        component_indexes: list[int] = []
        while pending:
            current = pending.pop()
            component_indexes.append(current)
            for other in order:
                if other in visited:
                    continue
                if _spatially_related(bounds[current], bounds[other]):
                    visited.add(other)
                    pending.append(other)
        component_indexes.sort(
            key=lambda index: (
                bounds[index][1],
                bounds[index][0],
                _text(candidates[index].get("candidate_id")),
            )
        )
        components.append([candidates[index] for index in component_indexes])
    return components


def _claim_ids(
    candidate: Mapping[str, object], relation: str
) -> tuple[str, ...]:
    result: list[str] = []
    claims = _sequence(candidate.get("claims", []), "candidate.claims")
    for index, item in enumerate(claims):
        claim = _mapping(item, f"candidate.claims[{index}]")
        if claim.get("relation") != relation:
            continue
        claim_id = _text(claim.get("claim_id"))
        if claim_id and claim_id not in result:
            result.append(claim_id)
    return tuple(result)


def _status(candidates: Sequence[Mapping[str, object]]) -> str:
    direct = any(_claim_ids(candidate, "direct") for candidate in candidates)
    if not direct:
        return "not_comparable"
    statuses = {
        str(status).upper()
        for candidate in candidates
        for status in _sequence(
            candidate.get("review_statuses", []), "candidate.review_statuses"
        )
    }
    if statuses & {"NOT_SATISFIED", "FAILED", "FAIL", "REJECTED"}:
        return "mismatch"
    if statuses & {
        "INDETERMINATE",
        "REVIEW_REQUIRED",
        "PARTIALLY_RESOLVED",
        "ABSTAIN",
        "CONDITIONAL",
        "ADDITIONAL_REVIEW_REQUIRED",
    }:
        return "needs_check"
    if statuses & {"SATISFIED", "PASS", "PASSED"}:
        return "match"
    return "needs_check"


def _issue_questions(candidates: Sequence[Mapping[str, object]]) -> set[str]:
    questions: set[str] = set()
    for candidate in candidates:
        for raw_question in _sequence(
            candidate.get("issue_questions", []), "candidate.issue_questions"
        ):
            normalized = _normalized_phrase(raw_question)
            if normalized:
                questions.add(normalized)
    return questions


def _display_values(candidates: Sequence[Mapping[str, object]]) -> str:
    values: list[str] = []
    questions = _issue_questions(candidates)
    for candidate in candidates:
        value = (
            _text(candidate.get("display_value"))
            or _text(candidate.get("normalized_candidate"))
            or _text(candidate.get("raw_value"))
        )
        normalized = _normalized_phrase(value)
        if normalized and any(question in normalized for question in questions):
            continue
        if value and value not in values:
            values.append(value)
    return " · ".join(values) if values else "도면에서 확인된 시각 요소"


def _finding(
    asset_key: str,
    issue_ids: tuple[str, ...],
    category: str,
    candidates: Sequence[Mapping[str, object]],
) -> dict[str, object]:
    candidate_ids = sorted(
        {
            _text(item.get("candidate_id"))
            for item in candidates
            if _text(item.get("candidate_id"))
        }
    )
    bounds = [_geometry_bounds(item) for item in candidates]
    focus_bbox = [
        min(item[0] for item in bounds),
        min(item[1] for item in bounds),
        max(item[2] for item in bounds),
        max(item[3] for item in bounds),
    ]
    direct_claim_ids = sorted(
        {
            claim_id
            for candidate in candidates
            for claim_id in _claim_ids(candidate, "direct")
        }
    )
    related_claim_ids = sorted(
        {
            claim_id
            for candidate in candidates
            for claim_id in _claim_ids(candidate, "related")
        }
    )
    identity = {
        "asset_key": asset_key,
        "issue_ids": list(issue_ids),
        "category": category,
        "candidate_ids": candidate_ids,
    }
    return {
        "finding_id": f"VF-{sha256_json(identity)[:20].upper()}",
        "title": _CATEGORY_TITLES[category],
        "category": category,
        "status": _status(candidates),
        "page_asset_key": asset_key,
        "candidate_ids": candidate_ids,
        "issue_ids": list(issue_ids),
        "subject_value": _display_values(candidates),
        "focus_bbox": focus_bbox,
        "direct_claim_ids": direct_claim_ids,
        "related_claim_ids": related_claim_ids,
    }


def build_semantic_visual_findings(
    pages: Sequence[Mapping[str, object]],
) -> list[dict[str, object]]:
    """Group raw OCR/visual candidates into stable reviewer-facing findings."""
    grouped: dict[
        tuple[str, tuple[str, ...], str], list[Mapping[str, object]]
    ] = {}
    for page_index, raw_page in enumerate(pages):
        page = _mapping(raw_page, f"pages[{page_index}]")
        asset_key = _text(page.get("asset_key"))
        if not asset_key:
            raise ValueError("visual page asset_key is required")
        raw_candidates = _sequence(page.get("candidates", []), "page.candidates")
        for candidate_index, raw_candidate in enumerate(raw_candidates):
            candidate = _mapping(
                raw_candidate, f"page.candidates[{candidate_index}]"
            )
            issue_ids = tuple(
                sorted(
                    {
                        str(item)
                        for item in _sequence(
                            candidate.get("issue_ids", []), "candidate.issue_ids"
                        )
                        if str(item)
                    }
                )
            )
            key = (asset_key, issue_ids, _category(candidate))
            grouped.setdefault(key, []).append(candidate)

    findings: list[dict[str, object]] = []
    for (asset_key, issue_ids, category), candidates in sorted(grouped.items()):
        candidate_groups = (
            _spatial_components(candidates)
            if category == "visual_observation"
            else [candidates]
        )
        findings.extend(
            _finding(asset_key, issue_ids, category, component)
            for component in candidate_groups
        )
    return findings


__all__ = ["build_semantic_visual_findings"]
