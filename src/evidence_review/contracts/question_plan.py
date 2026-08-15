"""Fail-closed contract for externally generated question plans."""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Literal, cast

QUESTION_PLAN_FORMAT = "evidence-review/question-plan"
QUESTION_PLAN_VERSION = 2
LEGACY_QUESTION_PLAN_VERSION = 1
MAX_ISSUES = 8
MAX_SEARCH_REQUESTS = 24
MAX_LEGAL_ANCHORS = 20

SearchKind = Literal["phrase", "legal_anchor", "concept_relation", "counterfactual"]
AnchorSource = Literal["user", "planner"]
Polarity = Literal["positive", "negative"]
EvidenceRole = Literal["supporting_fact", "rule"]

_NUMERIC_LITERAL = re.compile(
    r"(?P<number>(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?)"
    r"(?P<unit>제곱미터|퍼센트|킬로미터|밀리미터|센티미터|미터|"
    r"m²|m2|km|mm|cm|㎡|㎥|m|%|종|조|항|호|층|세대|대|명|년|개월|월|일)?"
)
_UNIT_CANONICAL = {
    "제곱미터": "㎡",
    "m²": "㎡",
    "m2": "㎡",
    "퍼센트": "%",
    "킬로미터": "km",
    "밀리미터": "mm",
    "센티미터": "cm",
    "미터": "m",
}
_EXPLICIT_USER_LEGAL_CITATION = re.compile(
    r"제\d+조(?:의\d+)?(?:\s*제\d+항)?(?:\s*제\d+호)?"
    r"|제\d+(?:항|호)"
    r"|별표\s*\d+"
)


@dataclass(frozen=True, slots=True)
class QuestionFact:
    """One fact or assumption preserved from the planning step."""

    id: str
    text: str
    polarity: Polarity


@dataclass(frozen=True, slots=True)
class QuestionIssue:
    """One evidence-bearing issue the deterministic review must address."""

    id: str
    question: str
    depends_on: tuple[str, ...]
    required_evidence_roles: tuple[EvidenceRole, ...]


@dataclass(frozen=True, slots=True)
class LegalAnchor:
    """A legal citation or named authority used only as a retrieval hypothesis."""

    text: str
    source: AnchorSource


@dataclass(frozen=True, slots=True)
class SearchRequest:
    """A bounded evidence search request tied to one or more issues."""

    id: str
    issue_ids: tuple[str, ...]
    text: str
    kind: SearchKind
    source: AnchorSource
    role: EvidenceRole


@dataclass(frozen=True, slots=True)
class QuestionPlan:
    """Validated, immutable interpretation of a natural-language question."""

    original_question: str
    facts: tuple[QuestionFact, ...]
    assumptions: tuple[QuestionFact, ...]
    issues: tuple[QuestionIssue, ...]
    legal_anchors: tuple[LegalAnchor, ...]
    search_requests: tuple[SearchRequest, ...]


def _normalize_text(value: str) -> str:
    """Match the repository's NFC + collapsed-whitespace query normalization."""
    return unicodedata.normalize("NFC", " ".join(value.split()))


def _expect_mapping(value: object, field: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{field} must be an object")
    if not all(isinstance(key, str) for key in value):
        raise ValueError(f"{field} keys must be strings")
    return cast(Mapping[str, object], value)


def _expect_sequence(value: object, field: str) -> Sequence[object]:
    if isinstance(value, (str, bytes, bytearray)) or not isinstance(value, Sequence):
        raise ValueError(f"{field} must be an array")
    return cast(Sequence[object], value)


def _expect_string(value: object, field: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{field} must be a string")
    normalized = _normalize_text(value)
    if not normalized:
        raise ValueError(f"{field} must not be empty")
    return normalized


def _expect_int(value: object, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{field} must be an integer")
    return value


def _expect_literal[T: str](value: object, field: str, allowed: tuple[T, ...]) -> T:
    candidate = _expect_string(value, field)
    if candidate not in allowed:
        raise ValueError(f"unsupported {field}: {candidate}")
    return candidate


def _reject_unknown(payload: Mapping[str, object], allowed: set[str], field: str) -> None:
    unknown = sorted(set(payload) - allowed)
    if unknown:
        raise ValueError(f"{field} has unknown fields: {', '.join(unknown)}")


def _decode_fact(value: object, field: str) -> QuestionFact:
    payload = _expect_mapping(value, field)
    _reject_unknown(payload, {"id", "text", "polarity"}, field)
    return QuestionFact(
        id=_expect_string(payload.get("id"), f"{field}.id"),
        text=_expect_string(payload.get("text"), f"{field}.text"),
        polarity=cast(
            Polarity,
            _expect_literal(
                payload.get("polarity"), f"{field}.polarity", ("positive", "negative")
            ),
        ),
    )


def _decode_evidence_roles(value: object, field: str) -> tuple[EvidenceRole, ...]:
    role_values = _expect_sequence(value, field)
    if not role_values:
        raise ValueError(f"{field} must not be empty")
    roles = tuple(
        cast(
            EvidenceRole,
            _expect_literal(
                item,
                f"{field}[{index}]",
                ("supporting_fact", "rule"),
            ),
        )
        for index, item in enumerate(role_values)
    )
    if len(set(roles)) != len(roles):
        raise ValueError(f"{field} contains duplicates")
    return roles


def _decode_issue(value: object, field: str, *, version: int) -> QuestionIssue:
    payload = _expect_mapping(value, field)
    if version == LEGACY_QUESTION_PLAN_VERSION:
        _reject_unknown(payload, {"id", "question", "depends_on"}, field)
        required_evidence_roles: tuple[EvidenceRole, ...] = ("rule",)
    else:
        _reject_unknown(
            payload,
            {"id", "question", "depends_on", "required_evidence_roles"},
            field,
        )
        required_evidence_roles = _decode_evidence_roles(
            payload.get("required_evidence_roles"),
            f"{field}.required_evidence_roles",
        )
    dependency_values = _expect_sequence(payload.get("depends_on"), f"{field}.depends_on")
    dependencies = tuple(
        _expect_string(item, f"{field}.depends_on[{index}]")
        for index, item in enumerate(dependency_values)
    )
    if len(set(dependencies)) != len(dependencies):
        raise ValueError(f"{field}.depends_on contains duplicates")
    return QuestionIssue(
        id=_expect_string(payload.get("id"), f"{field}.id"),
        question=_expect_string(payload.get("question"), f"{field}.question"),
        depends_on=dependencies,
        required_evidence_roles=required_evidence_roles,
    )


def _decode_legal_anchor(value: object, field: str) -> LegalAnchor:
    payload = _expect_mapping(value, field)
    _reject_unknown(payload, {"text", "source"}, field)
    return LegalAnchor(
        text=_expect_string(payload.get("text"), f"{field}.text"),
        source=cast(
            AnchorSource,
            _expect_literal(payload.get("source"), f"{field}.source", ("user", "planner")),
        ),
    )


def _decode_search_request(value: object, field: str, *, version: int) -> SearchRequest:
    payload = _expect_mapping(value, field)
    if version == LEGACY_QUESTION_PLAN_VERSION:
        _reject_unknown(payload, {"id", "issue_ids", "text", "kind", "source"}, field)
        role: EvidenceRole = "rule"
    else:
        _reject_unknown(
            payload,
            {"id", "issue_ids", "text", "kind", "source", "role"},
            field,
        )
        role = cast(
            EvidenceRole,
            _expect_literal(
                payload.get("role"),
                f"{field}.role",
                ("supporting_fact", "rule"),
            ),
        )
    issue_values = _expect_sequence(payload.get("issue_ids"), f"{field}.issue_ids")
    issue_ids = tuple(
        _expect_string(item, f"{field}.issue_ids[{index}]")
        for index, item in enumerate(issue_values)
    )
    if not issue_ids:
        raise ValueError(f"{field}.issue_ids must not be empty")
    if len(set(issue_ids)) != len(issue_ids):
        raise ValueError(f"{field}.issue_ids contains duplicates")
    return SearchRequest(
        id=_expect_string(payload.get("id"), f"{field}.id"),
        issue_ids=issue_ids,
        text=_expect_string(payload.get("text"), f"{field}.text"),
        kind=cast(
            SearchKind,
            _expect_literal(
                payload.get("kind"),
                f"{field}.kind",
                ("phrase", "legal_anchor", "concept_relation", "counterfactual"),
            ),
        ),
        source=cast(
            AnchorSource,
            _expect_literal(payload.get("source"), f"{field}.source", ("user", "planner")),
        ),
        role=role,
    )


def _require_unique_ids(
    items: Sequence[QuestionFact | QuestionIssue | SearchRequest], *, field: str
) -> None:
    seen: set[str] = set()
    for item in items:
        item_id = item.id
        if item_id in seen:
            raise ValueError(f"{field} contains duplicate id: {item_id}")
        seen.add(item_id)


def _validate_issue_graph(issues: tuple[QuestionIssue, ...]) -> None:
    issue_ids = {issue.id for issue in issues}
    by_id = {issue.id: issue for issue in issues}
    for issue in issues:
        for dependency in issue.depends_on:
            if dependency == issue.id:
                raise ValueError(f"issue {issue.id} must not depend on itself")
            if dependency not in issue_ids:
                raise ValueError(f"issue {issue.id} references unknown dependency: {dependency}")

    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(issue_id: str) -> None:
        if issue_id in visited:
            return
        if issue_id in visiting:
            raise ValueError("issues contain a dependency cycle")
        visiting.add(issue_id)
        for dependency in by_id[issue_id].depends_on:
            visit(dependency)
        visiting.remove(issue_id)
        visited.add(issue_id)

    for issue in issues:
        visit(issue.id)


def _numeric_literals(text: str) -> set[str]:
    """Extract normalized numeric literals while preserving explicit unit semantics."""
    result: set[str] = set()
    for match in _NUMERIC_LITERAL.finditer(text):
        number = match.group("number").replace(",", "")
        unit = match.group("unit") or ""
        result.add(number + _UNIT_CANONICAL.get(unit, unit))
    return result


def _legal_citation_key(value: str) -> str:
    return re.sub(r"\s+", "", _normalize_text(value))


def _explicit_user_legal_citations(text: str) -> set[str]:
    return {
        _legal_citation_key(match.group(0))
        for match in _EXPLICIT_USER_LEGAL_CITATION.finditer(text)
    }


def _validate_user_legal_citations(
    original_question: str,
    legal_anchors: tuple[LegalAnchor, ...],
) -> None:
    required = _explicit_user_legal_citations(original_question)
    if not required:
        return
    user_anchor_keys = {
        _legal_citation_key(anchor.text)
        for anchor in legal_anchors
        if anchor.source == "user"
    }
    missing = sorted(
        citation
        for citation in required
        if not any(citation in anchor for anchor in user_anchor_keys)
    )
    if missing:
        raise ValueError(
            "question_plan drops explicit user legal citation: " + ", ".join(missing)
        )


def _validate_numeric_preservation(
    original_question: str,
    facts: tuple[QuestionFact, ...],
    assumptions: tuple[QuestionFact, ...],
    issues: tuple[QuestionIssue, ...],
    legal_anchors: tuple[LegalAnchor, ...],
    search_requests: tuple[SearchRequest, ...],
) -> None:
    required = _numeric_literals(original_question)
    if not required:
        return
    structured_text = " ".join(
        [
            *(item.text for item in facts),
            *(item.text for item in assumptions),
            *(item.question for item in issues),
            *(item.text for item in legal_anchors),
            *(item.text for item in search_requests),
        ]
    )
    present = _numeric_literals(structured_text)
    missing = sorted(required - present)
    if missing:
        raise ValueError(
            "question_plan drops user numeric literal: " + ", ".join(missing)
        )


def decode_question_plan(value: object, expected_question: str) -> QuestionPlan:
    """Decode v1/v2 planner JSON into the current immutable v2 contract."""
    payload = _expect_mapping(value, "question_plan")
    allowed = {
        "format",
        "version",
        "original_question",
        "facts",
        "assumptions",
        "issues",
        "legal_anchors",
        "search_requests",
    }
    _reject_unknown(payload, allowed, "question_plan")

    if _expect_string(payload.get("format"), "format") != QUESTION_PLAN_FORMAT:
        raise ValueError("unsupported question plan format")
    version = _expect_int(payload.get("version"), "version")
    if version not in (LEGACY_QUESTION_PLAN_VERSION, QUESTION_PLAN_VERSION):
        raise ValueError("unsupported question plan version")

    normalized_expected = _normalize_text(expected_question)
    if not normalized_expected:
        raise ValueError("expected_question must not be empty")
    normalized_original = _expect_string(payload.get("original_question"), "original_question")
    if normalized_original != normalized_expected:
        raise ValueError("original_question does not match expected question")

    fact_values = _expect_sequence(payload.get("facts"), "facts")
    assumption_values = _expect_sequence(payload.get("assumptions"), "assumptions")
    issue_values = _expect_sequence(payload.get("issues"), "issues")
    anchor_values = _expect_sequence(payload.get("legal_anchors"), "legal_anchors")
    search_values = _expect_sequence(payload.get("search_requests"), "search_requests")

    if not issue_values:
        raise ValueError("issues must not be empty")
    if not search_values:
        raise ValueError("search_requests must not be empty")
    if len(issue_values) > MAX_ISSUES:
        raise ValueError(f"issues exceeds maximum of {MAX_ISSUES}")
    if len(anchor_values) > MAX_LEGAL_ANCHORS:
        raise ValueError(f"legal_anchors exceeds maximum of {MAX_LEGAL_ANCHORS}")
    if len(search_values) > MAX_SEARCH_REQUESTS:
        raise ValueError(f"search_requests exceeds maximum of {MAX_SEARCH_REQUESTS}")

    facts = tuple(_decode_fact(item, f"facts[{index}]") for index, item in enumerate(fact_values))
    assumptions = tuple(
        _decode_fact(item, f"assumptions[{index}]")
        for index, item in enumerate(assumption_values)
    )
    issues = tuple(
        _decode_issue(item, f"issues[{index}]", version=version)
        for index, item in enumerate(issue_values)
    )
    legal_anchors = tuple(
        _decode_legal_anchor(item, f"legal_anchors[{index}]")
        for index, item in enumerate(anchor_values)
    )
    search_requests = tuple(
        _decode_search_request(item, f"search_requests[{index}]", version=version)
        for index, item in enumerate(search_values)
    )

    _require_unique_ids(facts, field="facts")
    _require_unique_ids(assumptions, field="assumptions")
    _require_unique_ids(issues, field="issues")
    _require_unique_ids(search_requests, field="search_requests")
    fact_ids = {fact.id for fact in facts}
    overlapping_fact_ids = fact_ids.intersection(item.id for item in assumptions)
    if overlapping_fact_ids:
        duplicate = sorted(overlapping_fact_ids)[0]
        raise ValueError(f"facts and assumptions contain duplicate id: {duplicate}")

    _validate_issue_graph(issues)
    issue_ids = {issue.id for issue in issues}
    issues_by_id = {issue.id: issue for issue in issues}
    for request in search_requests:
        unknown = sorted(set(request.issue_ids) - issue_ids)
        if unknown:
            raise ValueError(
                f"search request {request.id} references unknown issue: {unknown[0]}"
            )
        for issue_id in request.issue_ids:
            issue = issues_by_id[issue_id]
            if request.role not in issue.required_evidence_roles:
                raise ValueError(
                    f"search request {request.id} role {request.role} "
                    f"is not required by issue {issue_id}"
                )

    normalized_requests: set[tuple[str, SearchKind]] = set()
    for request in search_requests:
        key = (_normalize_text(request.text), request.kind)
        if key in normalized_requests:
            raise ValueError("search_requests contains duplicate normalized request")
        normalized_requests.add(key)

    for anchor in legal_anchors:
        if anchor.source == "user" and _normalize_text(anchor.text) not in normalized_expected:
            raise ValueError("user legal anchor is not present in original_question")

    _validate_user_legal_citations(normalized_expected, legal_anchors)
    _validate_numeric_preservation(
        normalized_expected,
        facts,
        assumptions,
        issues,
        legal_anchors,
        search_requests,
    )

    return QuestionPlan(
        original_question=normalized_expected,
        facts=facts,
        assumptions=assumptions,
        issues=issues,
        legal_anchors=legal_anchors,
        search_requests=search_requests,
    )


def question_plan_document(plan: QuestionPlan) -> dict[str, object]:
    """Encode a validated plan as its canonical JSON-compatible v2 document."""
    return {
        "format": QUESTION_PLAN_FORMAT,
        "version": QUESTION_PLAN_VERSION,
        "original_question": plan.original_question,
        "facts": [
            {"id": item.id, "text": item.text, "polarity": item.polarity} for item in plan.facts
        ],
        "assumptions": [
            {"id": item.id, "text": item.text, "polarity": item.polarity}
            for item in plan.assumptions
        ],
        "issues": [
            {
                "id": item.id,
                "question": item.question,
                "depends_on": list(item.depends_on),
                "required_evidence_roles": list(item.required_evidence_roles),
            }
            for item in plan.issues
        ],
        "legal_anchors": [
            {"text": item.text, "source": item.source} for item in plan.legal_anchors
        ],
        "search_requests": [
            {
                "id": item.id,
                "issue_ids": list(item.issue_ids),
                "text": item.text,
                "kind": item.kind,
                "source": item.source,
                "role": item.role,
            }
            for item in plan.search_requests
        ],
    }
