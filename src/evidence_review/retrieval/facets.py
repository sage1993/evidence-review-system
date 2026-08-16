"""Deterministic issue facet compilation and evidence coverage."""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass

from evidence_review.contracts.question_plan import QuestionPlan
from evidence_review.retrieval.conditional import extract_measures
from evidence_review.retrieval.issue_bundle import IssueRetrievalBundle


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


def _required_facet_ids(question: str) -> tuple[str, ...]:
    text = _normalize(question)
    facets: list[str] = []

    def add(value: str) -> None:
        if value not in facets:
            facets.append(value)

    if "최소" in text and "면적" in text:
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
    """Compile stable sub-questions from issue wording without an LLM call."""
    return FacetPlan(
        issues=tuple(
            IssueFacetPlan(
                issue_id=issue.id,
                required_facets=tuple(
                    FacetRequirement(facet_id=value)
                    for value in _required_facet_ids(issue.question)
                ),
            )
            for issue in plan.issues
        )
    )


def _has_measure(text: str, dimension: str, *, conditional: bool | None = None) -> bool:
    for measure in extract_measures(text):
        if measure.dimension != dimension:
            continue
        if conditional is not None and measure.conditional is not conditional:
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
            and ("각각" in normalized or "각 주택" in normalized or "각 주택용도" in normalized)
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
        return "산업부지" in normalized and "확보비율" in normalized
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


def evaluate_facet_coverage(
    plan: QuestionPlan,
    bundle: IssueRetrievalBundle,
) -> FacetCoverageReport:
    """Require direct semantic support for every compiled issue facet."""
    facet_plan = compile_required_facets(plan)
    issues: list[IssueFacetCoverage] = []
    for issue in facet_plan.issues:
        evidence_by_facet: list[tuple[str, tuple[str, ...]]] = []
        covered: list[str] = []
        missing: list[str] = []
        for requirement in issue.required_facets:
            evidence_ids: set[str] = set()
            for candidate in bundle.candidates:
                if not any(match.issue_id == issue.issue_id for match in candidate.matches):
                    continue
                if not _facet_matches(
                    requirement.facet_id,
                    f"{candidate.clause.title} {candidate.clause.text}",
                ):
                    continue
                evidence_ids.update(hit.evidence_id for hit in candidate.evidence)
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
