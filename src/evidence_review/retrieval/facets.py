"""Deterministic issue facet compilation and evidence coverage."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, replace

from evidence_review.contracts.question_plan import (
    MAX_SEARCH_REQUESTS,
    QuestionPlan,
    SearchRequest,
)
from evidence_review.retrieval.conditional import extract_measures
from evidence_review.retrieval.issue_bundle import IssueRetrievalBundle

_RATIO_FRACTION_RE = re.compile(r"\d+\s*분의\s*\d+")
_RATIO_PERCENT_RE = re.compile(r"\d+(?:\.\d+)?\s*(?:%|퍼센트)")
_RATIO_LABEL_RE = re.compile(r"[0-9A-Za-z가-힣]+비율")
_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?。！？])\s+|\n+")
_INDUSTRIAL_RATIO_MARKER = "산업부지 확보비율"
_FACET_SEARCH_TEXT: dict[str, str] = {
    "minimum-area-threshold": "사업대상지 최소 면적",
    "distance-normal-threshold": "역세권 승강장 경계 거리 기준",
    "distance-conditional-threshold": "역세권 승강장 경계 거리 기준",
    "private-rental-parking-standard": "공공지원민간임대주택 주차장 설치기준",
    "dormitory-parking-standard": "임대형기숙사 주차장 설치기준",
    "mixed-use-parking-application": "복합 주차장 설치기준 각각 적용",
    "semi-industrial-far-threshold": "준공업지역 공동주택 기본용적률",
    "industrial-site-ratio": "준공업지역 산업부지 확보비율",
    "industrial-site-relaxation-procedure": "산업부지 확보비율 심의 완화 절차",
    "district-plan-parking-relaxation": "지구단위계획 주차장 설치기준 완화",
}


@dataclass(frozen=True, slots=True)
class FacetRequirement:
    facet_id: str


@dataclass(frozen=True, slots=True)
class IssueFacetPlan:
    issue_id: str
    required_facets: tuple[FacetRequirement, ...]


@dataclass(frozen=True, slots=True)
class FacetPlan:
    issues: tuple[IssueFacetPlan, ...]

    def by_issue_id(self, issue_id: str) -> IssueFacetPlan:
        for issue in self.issues:
            if issue.issue_id == issue_id:
                return issue
        raise KeyError(issue_id)


@dataclass(frozen=True, slots=True)
class IssueFacetCoverage:
    issue_id: str
    covered_facet_ids: tuple[str, ...]
    missing_facet_ids: tuple[str, ...]
    evidence_by_facet: tuple[tuple[str, tuple[str, ...]], ...]


@dataclass(frozen=True, slots=True)
class FacetCoverageReport:
    issues: tuple[IssueFacetCoverage, ...]

    def by_issue_id(self, issue_id: str) -> IssueFacetCoverage:
        for issue in self.issues:
            if issue.issue_id == issue_id:
                return issue
        raise KeyError(issue_id)


def _normalize(value: str) -> str:
    return unicodedata.normalize("NFKC", " ".join(value.split())).casefold()


def _measure_keys(text: str) -> frozenset[tuple[str, object]]:
    return frozenset(
        (measure.dimension, measure.value) for measure in extract_measures(text)
    )


def issue_context_text(plan: QuestionPlan, issue_question: str) -> str:
    """Recover original-question context sharing a numeric anchor with one issue.

    QuestionPlan validation guarantees that user numerics are preserved somewhere,
    but an external planner can still place a co-occurring fact only in ``facts``
    while shortening the issue question. A numeric anchor already present in the
    issue (for example 300m) is therefore used to recover only the original
    sentence(s) that contained that exact value. This avoids global fact leakage
    while retaining compound facts such as a 1,500㎡ site stated in the same
    sentence as the 300m distance condition.
    """
    issue_keys = _measure_keys(issue_question)
    if not issue_keys:
        return issue_question
    related: list[str] = []
    for sentence in _SENTENCE_SPLIT_RE.split(plan.original_question):
        candidate = sentence.strip()
        if not candidate:
            continue
        if issue_keys.intersection(_measure_keys(candidate)):
            related.append(candidate)
    return " ".join(dict.fromkeys((issue_question, *related)))


def _has_area_fact_in_issue(text: str) -> bool:
    normalized = _normalize(text)
    has_area = any(
        measure.dimension == "area_m2" for measure in extract_measures(text)
    )
    return (
        has_area
        and "부지" in normalized
        and any(token in normalized for token in ("사업", "추진", "가능", "충족"))
    )


def _required_facet_ids(question: str) -> tuple[str, ...]:
    text = _normalize(question)
    facets: list[str] = []

    def add(value: str) -> None:
        if value not in facets:
            facets.append(value)

    if ("최소" in text and "면적" in text) or _has_area_fact_in_issue(question):
        add("minimum-area-threshold")
    if "승강장" in text and ("역세권" in text or "거리" in text):
        add("distance-normal-threshold")
        if any(token in text for token in ("조건", "완화", "검토 대상")):
            add("distance-conditional-threshold")
    if "공공지원민간임대주택" in text and "주차" in text:
        add("private-rental-parking-standard")
    if "임대형기숙사" in text and "주차" in text:
        add("dormitory-parking-standard")
        if "복합" in text:
            add("mixed-use-parking-application")
    if "준공업" in text and "용적률" in text:
        add("semi-industrial-far-threshold")
    if "산업부지" in text and "확보비율" in text:
        add("industrial-site-ratio")
        if any(token in text for token in ("완화", "절차", "심의")):
            add("industrial-site-relaxation-procedure")
    if "지구단위계획" in text and "주차" in text:
        add("district-plan-parking-relaxation")
    return tuple(facets)


def compile_required_facets(plan: QuestionPlan) -> FacetPlan:
    """Compile stable sub-questions from issue wording and numeric original context."""
    return FacetPlan(
        issues=tuple(
            IssueFacetPlan(
                issue_id=issue.id,
                required_facets=tuple(
                    FacetRequirement(facet_id=value)
                    for value in _required_facet_ids(
                        issue_context_text(plan, issue.question)
                    )
                ),
            )
            for issue in plan.issues
        )
    )


def _request_covers_facet(facet_id: str, text: str) -> bool:
    normalized = _normalize(text)
    if facet_id == "minimum-area-threshold":
        return "면적" in normalized and ("최소" in normalized or "대지" in normalized)
    if facet_id in {"distance-normal-threshold", "distance-conditional-threshold"}:
        return "승강장" in normalized and (
            "거리" in normalized or "역세권" in normalized
        )
    if facet_id == "private-rental-parking-standard":
        return "공공지원민간임대주택" in normalized and "주차" in normalized
    if facet_id == "dormitory-parking-standard":
        return "임대형기숙사" in normalized and "주차" in normalized
    if facet_id == "mixed-use-parking-application":
        return "복합" in normalized and "주차" in normalized
    if facet_id == "semi-industrial-far-threshold":
        return "준공업" in normalized and "용적률" in normalized
    if facet_id == "industrial-site-ratio":
        return "산업부지" in normalized and "확보비율" in normalized
    if facet_id == "industrial-site-relaxation-procedure":
        return (
            "산업부지" in normalized
            and "확보비율" in normalized
            and any(token in normalized for token in ("심의", "완화", "절차"))
        )
    if facet_id == "district-plan-parking-relaxation":
        return "지구단위계획" in normalized and "주차" in normalized
    return False


def augment_plan_with_facet_search_requests(plan: QuestionPlan) -> QuestionPlan:
    """Add bounded deterministic rule queries for uncovered compound issue facets."""
    facet_plan = compile_required_facets(plan)
    generated: list[SearchRequest] = []
    for issue in facet_plan.issues:
        issue_requests = [
            request
            for request in plan.search_requests
            if issue.issue_id in request.issue_ids
        ]
        generated_texts: set[str] = set()
        for requirement in issue.required_facets:
            if any(
                request.role == "rule"
                and _request_covers_facet(requirement.facet_id, request.text)
                for request in (*issue_requests, *generated)
                if issue.issue_id in request.issue_ids
            ):
                continue
            search_text = _FACET_SEARCH_TEXT.get(requirement.facet_id)
            if search_text is None or search_text in generated_texts:
                continue
            generated.append(
                SearchRequest(
                    id=f"FACET-{issue.issue_id}-{requirement.facet_id}",
                    issue_ids=(issue.issue_id,),
                    text=search_text,
                    kind="concept_relation",
                    source="planner",
                    role="rule",
                )
            )
            generated_texts.add(search_text)
    if not generated:
        return plan
    search_requests = (*plan.search_requests, *generated)
    if len(search_requests) > MAX_SEARCH_REQUESTS:
        raise ValueError(
            "facet compiler exceeds question plan search request maximum: "
            f"{len(search_requests)} > {MAX_SEARCH_REQUESTS}"
        )
    return replace(plan, search_requests=tuple(search_requests))


def _has_measure(
    text: str,
    dimension: str,
    *,
    conditional: bool | None = None,
) -> bool:
    for measure in extract_measures(text):
        if measure.dimension != dimension:
            continue
        if conditional is not None and measure.conditional is not conditional:
            continue
        return True
    return False


def _has_industrial_ratio_value(text: str) -> bool:
    """Require a ratio whose nearest relevant label is the industrial-site ratio."""
    normalized = _normalize(text)
    ratio_matches = sorted(
        (*_RATIO_FRACTION_RE.finditer(normalized), *_RATIO_PERCENT_RE.finditer(normalized)),
        key=lambda item: item.start(),
    )
    for ratio_match in ratio_matches:
        marker_index = normalized.rfind(
            _INDUSTRIAL_RATIO_MARKER,
            0,
            ratio_match.start(),
        )
        if marker_index < 0:
            continue
        marker_end = marker_index + len(_INDUSTRIAL_RATIO_MARKER)
        if any(
            label.start() >= marker_end
            for label in _RATIO_LABEL_RE.finditer(
                normalized,
                marker_end,
                ratio_match.start(),
            )
        ):
            continue
        return True
    return False


def _facet_matches(facet_id: str, text: str) -> bool:
    normalized = _normalize(text)
    if facet_id == "minimum-area-threshold":
        return (
            ("면적" in normalized or "대지면적" in normalized)
            and _has_measure(text, "area_m2")
        )
    if facet_id == "distance-normal-threshold":
        return "승강장" in normalized and _has_measure(
            text,
            "length_m",
            conditional=False,
        )
    if facet_id == "distance-conditional-threshold":
        return "승강장" in normalized and _has_measure(
            text,
            "length_m",
            conditional=True,
        )
    if facet_id == "private-rental-parking-standard":
        return "주차" in normalized and (
            "공공지원민간임대주택" in normalized
            or "임대형기숙사를 제외" in normalized
        )
    if facet_id == "dormitory-parking-standard":
        return "임대형기숙사" in normalized and "주차" in normalized
    if facet_id == "mixed-use-parking-application":
        return (
            "복합" in normalized
            and "적용" in normalized
            and (
                "각각" in normalized
                or "각 주택" in normalized
                or "각 주택용도" in normalized
            )
        )
    if facet_id == "semi-industrial-far-threshold":
        measures = extract_measures(text)
        return (
            "준공업" in normalized
            and "용적률" in normalized
            and any(
                measure.dimension == "percent" and measure.value >= 400
                for measure in measures
            )
        )
    if facet_id == "industrial-site-ratio":
        return (
            "산업부지" in normalized
            and "확보비율" in normalized
            and _has_industrial_ratio_value(text)
        )
    if facet_id == "industrial-site-relaxation-procedure":
        return (
            "산업부지" in normalized
            and "확보비율" in normalized
            and any(token in normalized for token in ("심의", "위원회", "절차"))
        )
    if facet_id == "district-plan-parking-relaxation":
        return (
            "지구단위계획" in normalized
            and "주차" in normalized
            and "완화" in normalized
        )
    return False


def _direct_facet_evidence_ids(
    facet_id: str,
    candidate: object,
) -> tuple[str, ...]:
    from evidence_review.retrieval.issue_bundle import IssueClauseCandidate

    if not isinstance(candidate, IssueClauseCandidate):
        raise TypeError("candidate must be IssueClauseCandidate")
    matched = [
        hit.evidence_id
        for hit in candidate.evidence
        if _facet_matches(facet_id, f"{hit.title} {hit.text}")
    ]
    return tuple(sorted(set(matched)))


def evaluate_facet_coverage(
    plan: QuestionPlan,
    bundle: IssueRetrievalBundle,
) -> FacetCoverageReport:
    """Require clause semantics and a direct citation element for every facet."""
    facet_plan = compile_required_facets(plan)
    issues: list[IssueFacetCoverage] = []
    for issue in facet_plan.issues:
        evidence_by_facet: list[tuple[str, tuple[str, ...]]] = []
        covered: list[str] = []
        missing: list[str] = []
        for requirement in issue.required_facets:
            evidence_ids: set[str] = set()
            for candidate in bundle.candidates:
                if not any(
                    match.issue_id == issue.issue_id for match in candidate.matches
                ):
                    continue
                if not _facet_matches(
                    requirement.facet_id,
                    f"{candidate.clause.title} {candidate.clause.text}",
                ):
                    continue
                evidence_ids.update(
                    _direct_facet_evidence_ids(requirement.facet_id, candidate)
                )
            evidence_tuple = tuple(sorted(evidence_ids))
            evidence_by_facet.append((requirement.facet_id, evidence_tuple))
            if evidence_tuple:
                covered.append(requirement.facet_id)
            else:
                missing.append(requirement.facet_id)
        issues.append(
            IssueFacetCoverage(
                issue_id=issue.issue_id,
                covered_facet_ids=tuple(covered),
                missing_facet_ids=tuple(missing),
                evidence_by_facet=tuple(evidence_by_facet),
            )
        )
    return FacetCoverageReport(issues=tuple(issues))


def facet_coverage_document(report: FacetCoverageReport) -> list[dict[str, object]]:
    return [
        {
            "issue_id": issue.issue_id,
            "covered_facet_ids": list(issue.covered_facet_ids),
            "missing_facet_ids": list(issue.missing_facet_ids),
            "evidence_by_facet": [
                {"facet_id": facet_id, "evidence_ids": list(evidence_ids)}
                for facet_id, evidence_ids in issue.evidence_by_facet
            ],
        }
        for issue in report.issues
    ]


def bind_facet_coverage_to_review_request(
    request: dict[str, object],
    report: FacetCoverageReport,
) -> dict[str, object]:
    inputs_value = request.get("inputs")
    if not isinstance(inputs_value, dict) or not all(
        isinstance(key, str) for key in inputs_value
    ):
        raise ValueError("review request inputs must be an object")
    bound = dict(request)
    inputs = dict(inputs_value)
    inputs["facet_coverage"] = facet_coverage_document(report)
    bound["inputs"] = inputs
    return bound
